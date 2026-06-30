"""
Фаза 2 — расчёт заявок отработки (Compensation, тип «otrabotka») по факту.

Каждый день заявки проверяется отдельно:
  база (по shift на этот день) + параллельные заявки (excuse) дают
  эффективную норму, факт берётся из WorkLogDaily/WFM API.

  eff_work  = max(0, base_work − wh_excuse)
  eff_lock  = base_lock + lock_excuse
  overtime  = fact_full − eff_work
  over_lock = max(0, fact_lock − eff_lock)
  credit    = clamp(overtime − over_lock, 0, allocated_duration)
  tolerance (только для scheduled shift): недоработка ≤ tolerance → зачёт

Статусы дня: approved / partial / declined.
Итог заявки: все approved → approved; все declined → declined; иначе partial.

Параллельные excuse-типы (Transfer, пересекающие день):
  lgota*      → весь requested_duration в wh
  hoz_raboty  → весь requested_duration в lock
  isklyuchenie/obuchenie → wh_part в wh, lock_part в lock (функция
                складывает оба); если части не заданы — весь в wh
  ucheba_rabochee → ПОКА placeholder (окно проверки не реализовано)

Идемпотентно: повторный verify сначала откатывает прошлый результат.
"""

import logging
from datetime import timedelta

from django.db import transaction
from django.db.models import Max
from django.utils.timezone import localdate, now

from ..models import (
    Compensation,
    CompensationDebtLink,
    OperatorScheduleDay,
    RequestTypeRule,
    Transfer,
    WorkDebtDetail,
)
from .compensation_verifier import _fetch_fact_for_day
from .work_debt import recompute_for_operator

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = ["pending", "in_progress", "approved", "partial", "completed"]


def _fmt(delta) -> str:
    """Длительность в виде H:MM:SS (с минусом для отрицательных)."""
    if delta is None:
        delta = timedelta(0)
    total = int(delta.total_seconds())
    sign = "-" if total < 0 else ""
    total = abs(total)
    return f"{sign}{total // 3600}:{(total % 3600) // 60:02d}:{total % 60:02d}"

WH_EXCUSE_CODES = [
    "lgota", "lgota_brak", "lgota_rojdenie", "lgota_utrata",
    "lgota_pereezd", "lgota_prochie",
]
LOCK_EXCUSE_CODES = ["hoz_raboty"]
SPLIT_EXCUSE_CODES = ["isklyuchenie", "obuchenie"]
WINDOW_CODES = ["ucheba_rabochee"]  # placeholder — окно пока не реализовано


# --------------------------------------------------------------------------- #
# Норма дня и excuse
# --------------------------------------------------------------------------- #

def _shift_norms(operator, day):
    """
    Нормы дня по shift (work_hours-логика, как в debt_calculator):
      work_norm = norm_full − lock_norm   (7:30 / 6:30 / 9:40)
      9h/8h: lock_norm = norm_lock_warn_at (1:30), soft_cap = norm_lock_soft_cap (1:45)
      12h:   lock_norm = norm_lock_soft_cap (2:20), grace = 0
    Дам олиш / нет shift → всё 0, has_shift=False.
    """
    Z = timedelta(0)
    schedule = (
        OperatorScheduleDay.objects.filter(operator=operator, day=day)
        .select_related("shift").first()
    )
    if schedule and schedule.shift and not schedule.is_day_off:
        s = schedule.shift
        if s.norm_lock_warn_at and s.norm_lock_warn_at > Z:   # 9h/8h
            lock_norm = s.norm_lock_warn_at
            soft_cap = s.norm_lock_soft_cap or lock_norm
        else:                                                  # 12h
            lock_norm = s.norm_lock_soft_cap or Z
            soft_cap = lock_norm
        return {
            "work_norm": max((s.norm_full or Z) - lock_norm, Z),
            "lock_norm": lock_norm,
            "soft_cap": soft_cap,
            "grace": max(soft_cap - lock_norm, Z),
            "tolerance": s.tolerance_undertime or Z,
            "has_shift": True,
        }
    return {
        "work_norm": Z, "lock_norm": Z, "soft_cap": Z,
        "grace": Z, "tolerance": Z, "has_shift": False,
    }


def _excuses_for_day(operator, day):
    """
    (wh_excuse, lock_excuse, details) — суммарные excuse параллельных заявок,
    пересекающих day. otprashivanie/perenos сюда НЕ входят (они конфликтуют).
    """
    wh = timedelta(0)
    lock = timedelta(0)
    details = []

    transfers = (
        Transfer.objects.filter(
            operator=operator,
            status__in=ACTIVE_STATUSES,
            date_from__lte=day,
            date_to__gte=day,
        )
        .select_related("type_rule")
    )
    exc = {
        "lgota": timedelta(0),   # → с рабочих часов (определённо)
        "xoz": timedelta(0),     # → с перерыва (определённо)
        "flex": timedelta(0),    # искл/обуч — сторона определяется по API-разнице
        "flex_by": [],           # [(name, dur)] для разбивки
    }
    for t in transfers:
        code = t.type_rule.code
        name = t.type_rule.display_name
        dur = t.requested_duration or timedelta(0)
        if code in WH_EXCUSE_CODES:
            exc["lgota"] += dur
            details.append({"name": name, "side": "раб. часы", "dur": str(dur)})
        elif code in LOCK_EXCUSE_CODES:
            exc["xoz"] += dur
            details.append({"name": name, "side": "перерыв", "dur": str(dur)})
        elif code in SPLIT_EXCUSE_CODES:
            # сторона определяется по API-разнице; берём общую длительность
            fdur = dur or ((t.wh_part or timedelta(0)) + (t.lock_part or timedelta(0)))
            exc["flex"] += fdur
            exc["flex_by"].append((name, fdur))
            details.append({"name": name, "side": "раб./перерыв (по API)", "dur": str(fdur)})
        elif code in WINDOW_CODES:
            details.append({"name": name, "side": "окно (пропуск)", "dur": str(dur)})
        # otprashivanie/perenos и прочие — игнор
    return exc, details


# --------------------------------------------------------------------------- #
# Расчёт одного дня
# --------------------------------------------------------------------------- #

def verify_day(cday):
    """
    Посчитать один CompensationDay (модель раздельных сторон, БЕЗ двойного счёта).

    Отклонения от нормы (по факту API):
      presence_deficit = max(0, (work_norm+отработка+lock_norm) − full)  # неявка/опоздание
      lock_over        = max(0, lock − lock_norm) − grace − доделал       # перерыв сверх нормы
    Покрытие оправданиями:
      льгота → presence (рабочая сторона); хоз → lock; искл/обуч (flex) → авто
      (сначала presence, остаток на lock — т.к. flex логировался как перерыв).
    ВАЖНО: lock уже вычтен в (full−lock); искл/хоз ОБЪЯСНЯЮТ превышение перерыва,
           а НЕ добавляются повторно к работе (иначе двойной счёт).
    Неиспользованный запас оправданий — НЕ долг (оператор работал вместо отгула).
    """
    Z = timedelta(0)
    operator = cday.compensation.operator
    day = cday.day
    allocated = cday.allocated_duration or Z

    n = _shift_norms(operator, day)
    exc, excuse_details = _excuses_for_day(operator, day)
    fact_full, fact_lock = _fetch_fact_for_day(operator, day)

    lgota, xoz, flex = exc["lgota"], exc["xoz"], exc["flex"]

    api_full = max(fact_full, Z)
    api_lock = max(fact_lock, Z)
    api_work = max(api_full - api_lock, Z)

    # === ВЫХОДНОЙ (нет смены): разрешена ТОЛЬКО отработка (без параллельных
    # заявок). Перерыв НЕ учитывается вообще — зачёт = только отработанные
    # часы (work_hours). Новый долг НЕ создаётся: невыполненная часть остаётся
    # прежним долгом. ===
    if not n["has_shift"]:
        credit = min(max(api_work, Z), allocated)
        deficit = max(allocated - credit, Z)
        if allocated > Z and credit >= allocated:
            status = "approved"
        elif credit > Z:
            status = "partial"
        else:
            status = "declined"
        cday.fact_full = api_full
        cday.fact_lock = api_lock
        cday.credited_duration = credit
        cday.status = status
        cday.verified_at = now()
        st = [
            "1) График: выходной (только отработка, норма р/в нет).",
            f"2) Отработка за день: +{_fmt(allocated)}.",
            f"3) Факт API: присутствие {_fmt(api_full)} "
            f"(работа {_fmt(api_work)}, перерыв {_fmt(api_lock)} — не учитывается).",
            f"4) Зачёт отработки = отработанные часы {_fmt(api_work)}: "
            f"{_fmt(credit)} из {_fmt(allocated)} → {status}.",
        ]
        if deficit > Z:
            st.append(
                f"Отработка не выполнена на {_fmt(deficit)} "
                "(остаётся прежним долгом, новый долг НЕ создаётся)."
            )
        cday.note = "\n".join(st)
        cday.save(update_fields=[
            "fact_full", "fact_lock", "credited_duration",
            "status", "verified_at", "note", "updated_at",
        ])
        return {"status": status, "credit": credit, "deficit": deficit,
                "dayoff": True, "shift_code": None}

    full_required = n["work_norm"] + allocated + n["lock_norm"]
    presence_deficit = max(full_required - api_full, Z)
    # доделал = только реальная ПЕРЕРАБОТКА (факт.работа сверх нормы+отработки),
    # НЕ лишнее присутствие (лишнее присутствие может быть перерывом).
    work_surplus = max(api_work - (n["work_norm"] + allocated), Z)
    lock_over = max(api_lock - n["lock_norm"], Z)
    if n["has_shift"] and n["grace"] > Z and api_lock <= n["soft_cap"]:
        lock_over = max(lock_over - n["grace"], Z)        # послабление 15м (9h/8h)
    lock_over = max(lock_over - work_surplus, Z)          # доделал (переработка) компенсирует

    # --- Покрытие отклонений оправданиями ---
    cov_lgota = min(lgota, presence_deficit)              # льгота → рабочая сторона
    pres_rem = presence_deficit - cov_lgota
    cov_xoz = min(xoz, lock_over)                         # хоз → перерыв
    lock_rem = lock_over - cov_xoz
    # искл/обуч (flex): СНАЧАЛА снимают превышение перерыва (они логируются как
    # перерыв); если перерыв уже в норме — остаток идёт в работу.
    flex_to_lock = min(flex, lock_rem)
    flex_to_work = min(flex - flex_to_lock, pres_rem)
    flex_used = flex_to_work + flex_to_lock

    pres_unc = pres_rem - flex_to_work                    # необъяснённая недоработка
    lock_unc = lock_rem - flex_to_lock                    # необъяснённое превышение перерыва
    deficit = pres_unc + lock_unc

    if n["has_shift"] and n["tolerance"] > Z and Z < deficit <= n["tolerance"]:
        deficit = Z
        pres_unc = Z
        lock_unc = Z

    credit = min(max(allocated - deficit, Z), allocated)

    if allocated > Z and credit >= allocated:
        status = "approved"
    elif credit > Z:
        status = "partial"
    else:
        status = "declined"

    # --- Атрибуция: непокрытое сначала «съедает» отработку, остаток → дневной долг ---
    otra_from_pres = min(allocated, pres_unc)
    otra_from_lock = min(max(allocated - otra_from_pres, Z), lock_unc)
    otrabotka_viol = otra_from_pres + otra_from_lock
    norma_viol = pres_unc - otra_from_pres                # insufficient_wh (сверх отработки)
    pereryv_viol = lock_unc - otra_from_lock              # exceeding_break (сверх отработки)
    lgota_over = lgota - cov_lgota                        # не использован запас (НЕ долг)
    xoz_over = xoz - cov_xoz
    flex_over = flex - flex_used

    cday.fact_full = api_full
    cday.fact_lock = api_lock
    cday.credited_duration = credit
    cday.status = status
    cday.verified_at = now()

    # ---- Пошаговый аудит ----
    steps = []
    if n["has_shift"]:
        steps.append(
            f"1) График: норма р/в {_fmt(n['work_norm'])}, "
            f"перерыв {_fmt(n['lock_norm'])} (порог {_fmt(n['soft_cap'])})."
        )
    else:
        steps.append("1) График: нет смены (нормы 0).")
    steps.append(
        f"2) Отработка за день: +{_fmt(allocated)}. "
        f"Требуется присутствие: {_fmt(full_required)}."
    )
    steps.append(
        f"3) Факт API: смена {_fmt(api_full)} (работа {_fmt(api_work)}, "
        f"перерыв {_fmt(api_lock)})."
    )
    dev = []
    if presence_deficit > Z:
        dev.append(f"недоработка {_fmt(presence_deficit)}")
    if lock_over > Z:
        dev.append(f"перерыв сверх нормы {_fmt(lock_over)}")
    steps.append("4) Отклонения: " + (", ".join(dev) if dev else "нет") + ".")
    just = []
    if lgota > Z:
        just.append(f"льгота {_fmt(cov_lgota)}/{_fmt(lgota)} → работа")
    if xoz > Z:
        just.append(f"хоз {_fmt(cov_xoz)}/{_fmt(xoz)} → перерыв")
    if flex > Z:
        just.append(
            f"искл/обуч {_fmt(flex)}: сначала перерыв {_fmt(flex_to_lock)}, "
            f"затем работа {_fmt(flex_to_work)}"
        )
    steps.append("5) Оправдания: " + ("; ".join(just) if just else "нет") + ".")
    decision = f"6) Итог: зачтено отработки {_fmt(credit)} из {_fmt(allocated)} → {status}."
    if deficit > Z:
        d = []
        if pres_unc > Z:
            d.append(f"недоработка {_fmt(pres_unc)}")
        if lock_unc > Z:
            d.append(f"перерыв {_fmt(lock_unc)}")
        decision += " Не покрыто (долг): " + ", ".join(d) + "."
    unused = []
    if lgota_over > Z:
        unused.append(f"льгота {_fmt(lgota_over)}")
    if xoz_over > Z:
        unused.append(f"хоз {_fmt(xoz_over)}")
    if flex_over > Z:
        unused.append(f"искл/обуч {_fmt(flex_over)}")
    if unused:
        decision += (
            " Не использован запас оправданий (работал вместо этого, не долг): "
            + ", ".join(unused) + "."
        )
    steps.append(decision)

    cday.note = "\n".join(steps)
    cday.save(update_fields=[
        "fact_full", "fact_lock", "credited_duration",
        "status", "verified_at", "note", "updated_at",
    ])
    return {
        "status": status,
        "credit": credit,
        "deficit": deficit,
        "otrabotka_viol": otrabotka_viol,
        "pres_unc": pres_unc,
        "lock_unc": lock_unc,
        "norma_viol": norma_viol,
        "pereryv_viol": pereryv_viol,
        "shift_code": getattr(_day_shift(operator, day), "code", None),
    }


def _day_shift(operator, day):
    sched = (
        OperatorScheduleDay.objects.filter(operator=operator, day=day)
        .select_related("shift").first()
    )
    return sched.shift if sched else None


# --------------------------------------------------------------------------- #
# Применение/откат долга
# --------------------------------------------------------------------------- #

def _apply_credit_partial(compensation, credit):
    """
    Применить ровно `credit` к связанным долгам (FIFO) — для выходного.
    Остаток долга остаётся в исходных WDD (новый долг НЕ создаётся):
    полностью покрытые WDD — locked; недопокрытые — возвращаются в открытый список.
    """
    Z = timedelta(0)
    remaining = credit
    links = (
        CompensationDebtLink.objects
        .filter(compensation=compensation)
        .select_related("debt_detail")
    )
    for link in links:
        wdd = link.debt_detail
        if not wdd:
            continue
        wdd_total = (wdd.debt_full or Z) + (wdd.debt_lock or Z)
        applied = min(wdd_total, remaining) if remaining > Z else Z
        link.applied = applied > Z
        link.applied_amount = applied if applied > Z else None
        link.save(update_fields=["applied", "applied_amount", "updated_at"])
        wdd.locked_for_compensation = (applied >= wdd_total and applied > Z)
        wdd.save(update_fields=["locked_for_compensation", "updated_at"])
        remaining = max(remaining - applied, Z)
    compensation.deducted = True
    compensation.save(update_fields=["deducted", "updated_at"])
    recompute_for_operator(compensation.operator, compensation.cycle)


def _consume_all_links(compensation):
    """Полностью «съесть» связанные WDD в заявку (approved/partial)."""
    links = (
        CompensationDebtLink.objects
        .filter(compensation=compensation)
        .select_related("debt_detail")
    )
    for link in links:
        wdd = link.debt_detail
        amount = timedelta(0)
        if wdd:
            amount = (wdd.debt_full or timedelta(0)) + (wdd.debt_lock or timedelta(0))
            wdd.locked_for_compensation = True
            wdd.save(update_fields=["locked_for_compensation", "updated_at"])
        link.applied = True
        link.applied_amount = amount
        link.save(update_fields=["applied", "applied_amount", "updated_at"])


def _release_all_links(compensation):
    """Вернуть WDD в открытый список (declined): unlock, links не применены."""
    links = (
        CompensationDebtLink.objects
        .filter(compensation=compensation)
        .select_related("debt_detail")
    )
    for link in links:
        if link.debt_detail:
            link.debt_detail.locked_for_compensation = False
            link.debt_detail.save(update_fields=["locked_for_compensation", "updated_at"])
        link.applied = False
        link.applied_amount = None
        link.save(update_fields=["applied", "applied_amount", "updated_at"])


def _rollback(compensation):
    """Откатить прошлый результат verify (для идемпотентности)."""
    # удалить все WDD, созданные проверкой этой заявки (остаток + нарушения)
    WorkDebtDetail.objects.filter(
        source__in=["otrabotka_partial", "otrabotka_violation"],
        source_object_id=compensation.id,
    ).delete()
    # вернуть исходные связанные WDD в locked-состояние (как после accept)
    for link in CompensationDebtLink.objects.filter(compensation=compensation).select_related("debt_detail"):
        if link.debt_detail:
            link.debt_detail.locked_for_compensation = True
            link.debt_detail.save(update_fields=["locked_for_compensation", "updated_at"])
        link.applied = False
        link.applied_amount = None
        link.save(update_fields=["applied", "applied_amount", "updated_at"])
    # сбросить дни
    for cday in compensation.days.all():
        cday.status = "pending"
        cday.credited_duration = None
        cday.fact_full = None
        cday.fact_lock = None
        cday.verified_at = None
        cday.save(update_fields=[
            "status", "credited_duration", "fact_full",
            "fact_lock", "verified_at", "updated_at",
        ])


def _create_violation_wdds(compensation, cday, r, cycle, overall):
    """
    ОДИН WorkDebtDetail на день — суммарный камомат (долг) за день.
    Источники долга (если есть): отработка не выполнена + норма (недоработка)
    + перерыв + переборы льготы/хоз/искл-обуч. В note — что именно нарушено.
    """
    Z = timedelta(0)
    op = compensation.operator
    day = cday.day
    sc = r.get("shift_code")

    # Долг = только реальный непокрытый дефицит (перебор оправданий НЕ долг).
    if r.get("dayoff"):
        # выходной (смешанный план отработки): перерыв НЕ учитывается, новый
        # долг = невыполненная часть отработки (work_hours-база), без перерыва.
        debt_full = r.get("deficit", Z)
        debt_lock = Z
    elif overall == "declined":
        # отработка вернулась в открытый список через links →
        # в новый долг идёт только превышение сверх отработки
        debt_full = r["norma_viol"]
        debt_lock = r["pereryv_viol"]
    else:
        debt_full = r["pres_unc"]
        debt_lock = r["lock_unc"]

    if debt_full <= Z and debt_lock <= Z:
        return  # нарушений нет

    parts = []
    if debt_full > Z:
        parts.append(f"недоработка {_fmt(debt_full)}")
    if debt_lock > Z:
        parts.append(f"перерыв {_fmt(debt_lock)}")

    if debt_full > Z and debt_lock > Z:
        vtype = "both_violations"
    elif debt_lock > Z:
        vtype = "exceeding_break"
    else:
        vtype = "insufficient_wh"

    WorkDebtDetail.objects.create(
        operator=op, day=day, cycle=cycle,
        source="otrabotka_violation", source_object_id=compensation.id,
        violation_type=vtype,
        debt_full=debt_full, debt_lock=debt_lock,
        locked_for_compensation=False, shift_code_snapshot=sc,
        note=(
            f"Долг за {day} (заявка отработки #{compensation.id}):\n"
            + "\n".join(parts) + "."
        ),
    )


# --------------------------------------------------------------------------- #
# Главная функция
# --------------------------------------------------------------------------- #

@transaction.atomic
def verify_otrabotka(compensation) -> dict:
    """
    Проверить заявку отработки по дням, проставить итоговый статус и
    применить/вернуть долги. Идемпотентно.
    """
    if not compensation.type_rule or compensation.type_rule.code != "otrabotka":
        return {"error": "not_otrabotka"}

    operator = compensation.operator
    cycle = compensation.cycle

    _rollback(compensation)

    days = list(compensation.days.all())
    if not days:
        return {"error": "no_days"}

    day_results = [(d, verify_day(d)) for d in days]
    statuses = [r["status"] for _, r in day_results]
    total_credit = sum((d.credited_duration or timedelta(0) for d in days), timedelta(0))
    requested = compensation.requested_duration or timedelta(0)

    if all(s == "approved" for s in statuses):
        overall = "approved"
    elif all(s == "declined" for s in statuses):
        overall = "declined"
    else:
        overall = "partial"

    remaining = max(requested - total_credit, timedelta(0))

    # Выходной (все дни без смены): зачёт = work_hours, долг НЕ создаётся,
    # к долгам применяется ровно total_credit (остаток остаётся прежним долгом).
    is_dayoff = bool(day_results) and all(r.get("dayoff") for _, r in day_results)

    if overall == "declined":
        _release_all_links(compensation)
        compensation.deducted = False
    elif is_dayoff:
        _apply_credit_partial(compensation, total_credit)
    else:
        _consume_all_links(compensation)
        compensation.deducted = True
        # Отдельные WorkDebtDetail по дню (только рабочий день)
        for cday, r in day_results:
            _create_violation_wdds(compensation, cday, r, cycle, overall)

    compensation.verified_duration = total_credit
    compensation.remaining_debt = remaining
    compensation.status = overall
    compensation.verified_at = now()
    compensation.save(update_fields=[
        "verified_duration", "remaining_debt", "status",
        "verified_at", "deducted", "updated_at",
    ])

    recompute_for_operator(operator, cycle)

    return {
        "compensation_id": compensation.id,
        "overall": overall,
        "total_credit": str(total_credit),
        "requested": str(requested),
        "remaining": str(remaining),
        "days": [
            {"day": str(d.day), "status": d.status,
             "credited": str(d.credited_duration), "allocated": str(d.allocated_duration)}
            for d in days
        ],
    }


def verify_due_otrabotka(target_date=None) -> dict:
    """
    Авто-проверка: заявки отработки, у которых ВСЕ дни уже прошли
    (max(day) <= target_date), статус ещё не финальный — пересчитать.
    Идемпотентно; вызывается из daily_pipeline.
    """
    if target_date is None:
        target_date = localdate() - timedelta(days=1)

    due = (
        Compensation.objects.filter(
            type_rule__code="otrabotka",
            status__in=["pending", "partial"],
        )
        .annotate(last_day=Max("days__day"))
        .filter(last_day__isnull=False, last_day__lte=target_date)
    )

    stats = {"checked": 0, "approved": 0, "partial": 0, "declined": 0, "errors": 0}
    for comp in due:
        try:
            res = verify_otrabotka(comp)
            stats["checked"] += 1
            overall = res.get("overall")
            if overall in stats:
                stats[overall] += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("[verify_due_otrabotka] comp#%s: %s", comp.id, exc)
            stats["errors"] += 1
    return stats
