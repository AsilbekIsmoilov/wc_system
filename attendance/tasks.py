from celery import shared_task
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from .services.attendance import build_attendance, process_attendance

@shared_task
def attendance_worker():
    now = timezone.localtime()

    print("[CELERY] update:", now)

    process_attendance(now)
    data = build_attendance(now)

    print("[CELERY] data count:", len(data))
    print("[CELERY] data sample:", data[:1])

    channel_layer = get_channel_layer()
    print("[CELERY] channel layer:", channel_layer)

    async_to_sync(channel_layer.group_send)(
        "attendance_group",
        {
            "type": "send_attendance",
            "data": data
        }
    )

    print("[CELERY] group_send done")