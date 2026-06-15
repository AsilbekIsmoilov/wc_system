"""
Архивирование при закрытии цикла.

Модули:
  - cycle.py        — главный архиватор (запускается из close_cycle)
  - compensation.py — архивация Compensation
  - transfer.py     — архивация Transfer
  - debt.py         — архивация WorkDebt и WorkDebtDetail
"""


"""
Сервисный слой hourly_locks.

Здесь сосредоточена вся бизнес-логика:
  - cycle.py         — управление циклами
  - shift.py         — работа со сменами
  - external_api.py  — клиент внешнего API (почасовые логи)
  - event_log.py     — журнал событий
  - sheets_sync.py   — синхронизация с Google Sheets
  - log_loader.py    — загрузка ежедневных логов
  - debt_calculator.py        — расчёт долгов
  - compensation_verifier.py  — проверка компенсаций
  - transfer_verifier.py      — проверка переносов
  - night_pipeline.py         — ночной конвейер 20-08
  - retroactive_check.py      — ретроактивная проверка
  - manual_adjustment.py      — ручные правки с аудитом
  - automation_override.py    — переопределения автоматики
  - archive/         — архивирование при закрытии цикла
"""