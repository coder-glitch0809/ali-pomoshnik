"""Agentlarni boshqarish: yangi agent yaratish, tahrirlash, o'chirish (chat va Telegram orqali ham)."""
from .. import agents
from . import REGISTRY, skill


@skill(
    description=(
        "Barcha agentlar va ularning sozlamalari (vositalar, o'rganish mavzulari). key berilsa - shu agentning to'liq "
        "ko'rsatmasi ham."
    ),
    params={"key": {"type": "string", "description": "Agent kaliti (ixtiyoriy)"}},
    required=[],
)
def list_agents(key: str = "") -> str:
    team = agents.load()
    if key:
        a = team.get(key.lower())
        return a.to_markdown() if a else "Bunday agent yo'q."
    return "\n".join(f"- {a.key}: {a.icon} {a.name} | vositalar: {', '.join(a.tools) or '-'} | o'rganish: "
                     f"{'; '.join(a.learn) or '-'}" for a in team.values()) or "Agent yo'q."


@skill(description="Agentlarga berish mumkin bo'lgan barcha vositalar (skills) nomi va qisqa tavsifi.")
def list_available_tools() -> str:
    lines = [f"- {s.name}{' (tasdiq bilan)' if s.dangerous else ''}: {s.description[:110]}" for s in REGISTRY.values()]
    return "\n".join(["- web_search: internetdan qidirish", *lines])


@skill(
    description=(
        "Yangi agent yaratadi yoki mavjudini yangilaydi (o'sha key bilan). Yaratishdan oldin: soha bo'yicha web_search bilan "
        "o'rgan, list_available_tools dan kerakli vositalarni tanla, va prompt'ni batafsil yoz: rol, ish tartibi, javob "
        "formati, qoidalar, til. learn - agent avtomatik o'rganib boradigan mavzular. Muhim bilimlarni save_knowledge bilan "
        "'[key] mavzu' ko'rinishida saqla - agent ularni ishlatadi."
    ),
    params={
        "key": {"type": "string", "description": "Lotin harflarida qisqa kalit, masalan: huquqshunos"},
        "name": {"type": "string", "description": "Ko'rinadigan nom"},
        "icon": {"type": "string", "description": "Bitta emoji"},
        "description": {"type": "string", "description": "1-2 gapda nima qilishi (Ali vazifa topshirishda shunga qaraydi)"},
        "tools": {"type": "array", "items": {"type": "string"}, "description": "Vositalar nomlari"},
        "prompt": {"type": "string", "description": "Agentning to'liq ko'rsatmasi"},
        "learn": {"type": "array", "items": {"type": "string"}, "description": "Avtomatik o'rganish mavzulari"},
    },
    required=["key", "name", "icon", "description", "tools", "prompt"],
)
def create_agent(key: str, name: str, icon: str, description: str, tools: list, prompt: str,
                 learn: list | None = None) -> str:
    unknown = [t for t in tools if t != "web_search" and t not in REGISTRY]
    if unknown:
        return f"Noma'lum vositalar: {', '.join(unknown)}. list_available_tools bilan tekshir."
    existed = key.strip().lower() in agents.load()
    a = agents.save(key, name, icon, description, [str(t) for t in tools], prompt, [str(t) for t in learn or []])
    return f"Agent {'yangilandi' if existed else 'yaratildi'}: {a.icon} {a.name} ({a.key}). Saytda va Telegramda darhol paydo bo'ldi."


@skill(
    description="Agentni o'chiradi. Foydalanuvchi tasdiqlaydi.",
    params={"key": {"type": "string", "description": "Agent kaliti"}},
    dangerous=True,
)
def delete_agent(key: str) -> str:
    return "Agent o'chirildi." if agents.delete(key) else "Bunday agent yo'q."
