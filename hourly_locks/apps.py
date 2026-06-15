from django.apps import AppConfig


class HourlyLocksConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "hourly_locks"
    verbose_name = "Учёт рабочего времени"

    def ready(self):
        import hourly_locks.signals