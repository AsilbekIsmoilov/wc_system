# from datetime import date
# from hourly_locks.models import OperatorSchedule
#
# ALLOWED_GROUPS = [
#     "1000",
#     "1009",
#     "1093",
#     "1170",
#     "1242",
#     "BKM",
#     "INT",
#     "Группа ДОП",
#     "ДОП",
#     "Саралаш",
#     "РФ",
#     "Продажа",
#     "Нукус 1000",
#     "229 (1000)",
#     "БКМ",
#     "БКМ/09",
#     "ДОП 1",
#     "ДОП 2",
# ]
#
#
# def get_today_scheduled_operators():
#     today = date.today()
#     day = str(today.day)
#
#     qs = (
#         OperatorSchedule.objects
#         .filter(
#             year=today.year,
#             month=today.month,
#             operator__group__name__in=ALLOWED_GROUPS,
#         )
#         .select_related("operator", "operator__group")
#     )
#
#     result = []
#
#     for sch in qs:
#         raw = (sch.days or {}).get(day)
#
#         if raw:
#             op = sch.operator
#             op._schedule_value = raw
#             result.append(op)
#
#     return result