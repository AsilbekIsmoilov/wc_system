"""
ЕДИНАЯ симметричная матрица конфликтов между типами заявок (источник истины).

Если два типа конфликтуют — их нельзя принять на пересекающиеся дни (в любом
порядке). Матрица симметрична (2026-06-30, обновлено):

  Отработка     ↔ Отпрашивание, Перенос
  Отпрашивание  ↔ Отработка, Учёба, Перенос
  Учёба         ↔ Отпрашивание, Перенос, Льготы
  Перенос       ↔ Отработка, Отпрашивание, Учёба, Льготы, Хоз
  Льготы        ↔ Учёба, Перенос
  Хоз.работы    ↔ Перенос
  Исключение    — параллельно со ВСЕМ
  Обучение      — параллельно со ВСЕМ
"""

from datetime import date as _date

LGOTA_CODES = ["lgota", "lgota_brak", "lgota_rojdenie", "lgota_utrata",
               "lgota_pereezd", "lgota_prochie"]
BENEFIT_CODES = ["isklyuchenie", "obuchenie"] + LGOTA_CODES + ["hoz_raboty"]
ALL_CODES = ["otrabotka", "otprashivanie", "ucheba_rabochee",
             "perenos_dnya"] + BENEFIT_CODES

ACTIVE = ["pending", "in_progress", "approved", "partial", "completed"]

# code → множество конфликтующих codes (СИММЕТРИЧНО)
CONFLICTS = {
    "otrabotka": {"otprashivanie", "perenos_dnya"},
    "otprashivanie": {"otrabotka", "ucheba_rabochee", "perenos_dnya"},
    "ucheba_rabochee": {"otprashivanie", "perenos_dnya"} | set(LGOTA_CODES),
    "perenos_dnya": {"otrabotka", "otprashivanie", "ucheba_rabochee",
                     "hoz_raboty"} | set(LGOTA_CODES),
    "isklyuchenie": set(),          # параллельно со всем
    "obuchenie": set(),             # параллельно со всем
    "hoz_raboty": {"perenos_dnya"},
}
for _l in LGOTA_CODES:
    CONFLICTS[_l] = {"ucheba_rabochee", "perenos_dnya"}

DISPLAY = {
    "otrabotka": "Отработка", "otprashivanie": "Отпрашивание",
    "ucheba_rabochee": "Учёба в рабочее время", "perenos_dnya": "Перенос рабочего дня",
    "isklyuchenie": "Исключение", "obuchenie": "Обучение",
    "lgota": "Льгота", "lgota_brak": "Льгота по бракосочетанию",
    "lgota_rojdenie": "Льгота по рождению ребёнка",
    "lgota_utrata": "Льгота по утрате родственника",
    "lgota_pereezd": "Льгота по переезду", "lgota_prochie": "Прочие льготы",
    "hoz_raboty": "Хозяйственные работы",
}


def _occupied_days(operator, code, day_set):
    """Какие из day_set заняты АКТИВНОЙ заявкой типа `code` у оператора."""
    res = []
    if not day_set:
        return res

    if code == "otrabotka":
        from ..models import CompensationDay
        qs = (CompensationDay.objects.filter(
                day__in=day_set, compensation__operator=operator,
                compensation__type_rule__code="otrabotka")
              .exclude(status="declined").exclude(compensation__status="declined"))
        for c in qs:
            res.append({"code": code, "day": str(c.day), "id": c.compensation_id})

    elif code == "otprashivanie":
        from ..models import OtprashivanieDay
        for o in OtprashivanieDay.objects.filter(
                day__in=day_set, transfer__operator=operator,
                transfer__type_rule__code="otprashivanie",
                transfer__status__in=ACTIVE):
            res.append({"code": code, "day": str(o.day), "id": o.transfer_id})

    elif code == "ucheba_rabochee":
        from ..models import UchebaDay
        for u in UchebaDay.objects.filter(
                day__in=day_set, transfer__operator=operator,
                transfer__type_rule__code="ucheba_rabochee",
                transfer__status__in=ACTIVE):
            res.append({"code": code, "day": str(u.day), "id": u.transfer_id})

    elif code in BENEFIT_CODES:
        from ..models import BenefitDay, Transfer
        seen = set()
        for b in BenefitDay.objects.filter(
                day__in=day_set, transfer__operator=operator,
                transfer__type_rule__code=code, transfer__status__in=ACTIVE):
            res.append({"code": code, "day": str(b.day), "id": b.transfer_id})
            seen.add((b.transfer_id, b.day))
        for t in Transfer.objects.filter(
                operator=operator, type_rule__code=code, status__in=ACTIVE,
                benefit_days__isnull=True).distinct():
            df, dt = t.date_from, (t.date_to or t.date_from)
            if not df:
                continue
            for d in day_set:
                if df <= d <= dt and (t.id, d) not in seen:
                    res.append({"code": code, "day": str(d), "id": t.id})

    elif code == "perenos_dnya":
        from ..models import Transfer
        for t in Transfer.objects.filter(
                operator=operator, type_rule__code="perenos_dnya",
                status__in=ACTIVE):
            df, dt = t.date_from, (t.date_to or t.date_from)
            if not df:
                continue
            for d in day_set:
                if df <= d <= dt:
                    res.append({"code": code, "day": str(d), "id": t.id})

    for r in res:
        r["display_name"] = DISPLAY.get(code, code)
    return res


def find_conflicts(operator, new_code, days, exclude_transfer_id=None) -> list:
    """Конфликтующие заявки для НОВОЙ заявки `new_code` на `days`.
    Возвращает [{"code","display_name","day","id"}]."""
    day_set = {d if isinstance(d, _date) else _date.fromisoformat(str(d)) for d in days}
    out = []
    for ccode in sorted(CONFLICTS.get(new_code, set())):
        for c in _occupied_days(operator, ccode, day_set):
            if exclude_transfer_id and c["id"] == exclude_transfer_id:
                continue
            out.append(c)
    return out
