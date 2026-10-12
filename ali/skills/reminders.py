"""Eslatmalar. Vaqti kelganda scheduler.py ularni e'lon qiladi."""
from datetime import datetime, timedelta

from ..memory import memory
from . import skill


@skill(
    description="Belgilangan daqiqadan keyin eslatma qo'yadi. Aniq vaqt aytilsa, hozirgi vaqtdan farqini hisoblang.",
    params={
        "minutes": {"type": "number", "description": "Necha daqiqadan keyin"},
        "text": {"type": "string", "description": "Eslatma matni"},
    },
)
def set_reminder(minutes: float, text: str) -> str:
    due = datetime.now() + timedelta(minutes=minutes)
    rid = memory.add_reminder(text, due)
    return f"Eslatma #{rid} qo'yildi: {due:%H:%M} da - {text}"


@skill(description="Kutilayotgan eslatmalar ro'yxati.")
def list_reminders() -> str:
    rows = memory.pending_reminders()
    return "\n".join(f"#{r['id']} {r['due_at']}: {r['text']}" for r in rows) or "Eslatmalar yo'q"


@skill(
    description="Eslatmani bekor qiladi.",
    params={"reminder_id": {"type": "integer", "description": "Eslatma raqami"}},
)
def cancel_reminder(reminder_id: int) -> str:
    memory.mark_done(reminder_id)
    return f"Eslatma #{reminder_id} bekor qilindi"
