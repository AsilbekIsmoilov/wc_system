"""Middleware для логирования необработанных исключений (причин 500).

Оборачивает всю внутреннюю цепочку (middleware + вьюха + этап ответа) в
try/except и пишет ПОЛНЫЙ traceback в лог (консоль + файл logs/errors.log),
даже при DEBUG=False. Ставится ПЕРВЫМ в MIDDLEWARE, чтобы поймать всё.
"""
import logging

logger = logging.getLogger("app.errors")


class ExceptionLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            return self.get_response(request)
        except Exception:
            # Ловит исключения, всплывшие выше штатной обработки Django
            # (например, на этапе ответа/в другом middleware).
            logger.exception(
                "Необработанное исключение (call): %s %s",
                request.method,
                request.get_full_path(),
            )
            raise

    def process_exception(self, request, exception):
        # Вызывается Django для исключений, поднятых во вьюхе, — тут
        # traceback самый точный.
        logger.exception(
            "Необработанное исключение (view): %s %s",
            request.method,
            request.get_full_path(),
        )
        # Возвращаем None -> Django продолжает штатную обработку (500).
        return None
