"""
Классы пагинации для DRF.
"""

from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """Стандартная пагинация — по 25 на страницу."""
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


class TransferPagination(PageNumberPagination):
    """Пагинация для списка заявок (Transfer/Compensation)."""
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100


class LargePagination(PageNumberPagination):
    """Пагинация для больших списков (например, EventLog)."""
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 500