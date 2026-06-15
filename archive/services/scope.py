"""
Opredelenie vidimosti operatorov dlya polzovatelya v arkhive.

  - operator vidit tolko svoi zapisi
  - supervisor vidit operatorov iz svoikh grupp
  - manager / admin vidit vsekh
"""

from typing import List, Optional


def get_visible_operator_ids(user, year: int, month: int) -> Optional[List[int]]:
    """
    Vozvrashchaet spisok operator_id, kotorye polzovatel vidit v arkhive za year/month.

    Vozvrashchaet None — esli prav net (operator s otsutstvuyushchim Operator-zapis'yu).
    Vozvrashchaet [] — esli prav est', no nikogo ne vidno.
    Vozvrashchaet None tozhe esli supervisor bez grupp.
    """
    if not user or not user.is_authenticated:
        return None

    role = getattr(user, "role", None)
    operator = getattr(user, "operator", None)

    if role in ("manager", "admin"):
        # Vidit vsekh — vse operator_id iz snapshot
        from archive.models import ArchiveOperatorSnapshot
        return list(
            ArchiveOperatorSnapshot.objects
            .using("archive")
            .filter(archive_year=year, archive_month=month)
            .values_list("operator_id", flat=True)
        )

    if role == "supervisor":
        if not operator:
            return None

        # Gruppy, kotorye supervayzer kuriruet
        group_ids = list(user.supervised_groups.values_list("id", flat=True))
        if not group_ids:
            return []

        from archive.models import ArchiveOperatorSnapshot
        return list(
            ArchiveOperatorSnapshot.objects
            .using("archive")
            .filter(
                archive_year=year, archive_month=month,
                group_id__in=group_ids,
            )
            .values_list("operator_id", flat=True)
        )

    if role == "operator":
        if not operator:
            return []
        return [operator.id]

    return []
