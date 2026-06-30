"""
Лёгкий хелпер для push-уведомлений через Django Channels.

Доставка best-effort: если channel layer не настроен или потребитель
(consumer) для группы не подписан — уведомление просто не доставится,
исключение не пробрасывается. Бизнес-логика на это не завязана:
те же данные возвращаются в HTTP-ответе вызывающего эндпоинта.

Группы:
  - "user_<user_id>"      — личные уведомления пользователю
  - "operator_<op_id>"    — уведомления по оператору (для супервайзеров)
"""

import logging

logging.getLogger(__name__)
logger = logging.getLogger(__name__)


def _push(group: str, event_type: str, data: dict) -> None:
    """Отправить событие в группу channels. Никогда не бросает исключение."""
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        layer = get_channel_layer()
        if layer is None:
            return
        async_to_sync(layer.group_send)(
            group,
            {"type": "notify", "event": event_type, "data": data},
        )
    except Exception as exc:  # noqa: BLE001 — доставка best-effort
        logger.debug("notify push failed (group=%s): %s", group, exc)


def notify_user(user_id: int, event_type: str, data: dict) -> None:
    if user_id:
        _push(f"user_{user_id}", event_type, data)


def notify_operator(operator, event_type: str, data: dict) -> None:
    """
    Уведомить оператора (по привязанному User) и группу оператора.
    operator — экземпляр Operator.
    """
    if operator is None:
        return
    _push(f"operator_{operator.id}", event_type, data)

    user_account = getattr(operator, "user_account", None)
    if user_account is not None:
        notify_user(user_account.id, event_type, data)
