from datetime import timedelta
from django.db.models import Sum
from django.db.models import Q
from hourly_locks.models import WorkCompensation, WorkDebt, Operator


def format_timedelta(td):
    if not td:
        return "00:00:00"

    total_seconds = int(td.total_seconds())

    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def calculate_deduction_preview():
    TYPES = [
        "exception",
        "partial_exception",
        "sl",
        "wc",
        "study",
        "vacation",
    ]

    ALLOWED_GROUPS = ["1000", "1093", "1170", "ДОП", "1242"]

    operators_qs = (
        Operator.objects
        .select_related("group")
        .filter(
            role="operator",
            group__name__in=ALLOWED_GROUPS
        )
    )
    operator_ids = list(operators_qs.values_list("id", flat=True))

    qs = WorkCompensation.objects.filter(
        operator_id__in=operator_ids,
        type__in=TYPES,
        deducted=True
    ).exclude(
        status__in=["pending", "declined"]
    )

    grouped = list(
        qs.values("operator").annotate(total_duration=Sum("duration"))
    )

    grouped_map = {
        item["operator"]: item["total_duration"]
        for item in grouped
    }

    debts = {
        wd.operator_id: wd
        for wd in WorkDebt.objects.filter(operator_id__in=operator_ids)
    }

    comp_qs = WorkCompensation.objects.filter(
        operator_id__in=operator_ids,
        type__in=["compensation", "nb_compensation"]
    )

    comp_data = {}
    for comp in comp_qs:
        op_id = comp.operator_id

        if op_id not in comp_data:
            comp_data[op_id] = timedelta(0)

        if comp.status == "approved":
            comp_data[op_id] += comp.duration or timedelta(0)
        elif comp.status == "partial":
            comp_data[op_id] += comp.fact_duration or timedelta(0)

    comp_declined_qs = WorkCompensation.objects.filter(
        operator_id__in=operator_ids,
        type__in=["compensation", "nb_compensation"],
        status="declined"
    )

    comp_declined_data = {}

    for comp in comp_declined_qs:
        op_id = comp.operator_id

        if op_id not in comp_declined_data:
            comp_declined_data[op_id] = timedelta(0)

        comp_declined_data[op_id] += comp.duration or timedelta(0)

    no_comp_qs = WorkCompensation.objects.filter(
        operator_id__in=operator_ids,
        type="no_compensation",
        status="approved"
    )

    no_comp_data = {}

    for comp in no_comp_qs:
        op_id = comp.operator_id

        if op_id not in no_comp_data:
            no_comp_data[op_id] = timedelta(0)

        no_comp_data[op_id] += comp.duration or timedelta(0)

    result = []

    for operator in operators_qs:
        operator_id = operator.id

        total_duration = grouped_map.get(operator_id, timedelta(0))
        wd = debts.get(operator_id)

        total_accumulated = wd.total_debt_accumulated if wd else timedelta(0)

        calculated = max(total_accumulated - total_duration, timedelta(0))

        compensation_total = comp_data.get(operator_id, timedelta(0))
        comp_declined_total = comp_declined_data.get(operator_id, timedelta(0))
        no_comp_total = no_comp_data.get(operator_id, timedelta(0))

        result.append({
            "operator": {
                "id": operator_id,
                "surname": operator.surname,
                "name": operator.name,
                "middle_name": operator.middle_name,
                "full_name": f"{operator.surname} {operator.name} {operator.middle_name or ''}",
                "login_id": operator.login_id,
                "group": operator.group.name if operator.group else None,
            },
            "total_debt_accumulated": format_timedelta(total_accumulated),
            "system_error_duration": format_timedelta(total_duration),
            "after_deduction": format_timedelta(calculated),
            "compensation_total": format_timedelta(compensation_total),
            "compensation_declined_total": format_timedelta(comp_declined_total),
            "no_compensation_total": format_timedelta(no_comp_total),
        })

    return {
        "count": len(result),
        "data": result
    }