"""Uzoq muddatli xotira bilan ishlash."""
from ..memory import memory
from . import skill


@skill(
    description=(
        "Foydalanuvchi haqidagi muhim faktni doimiy xotiraga yozadi (ism, tug'ilgan kun, afzalliklar va h.k.). "
        "Foydalanuvchi 'eslab qol' desa yoki muhim shaxsiy ma'lumot aytsa ishlating."
    ),
    params={
        "key": {"type": "string", "description": "Qisqa kalit, masalan 'sevimli_rang'"},
        "value": {"type": "string", "description": "Qiymat"},
    },
)
def remember_fact(key: str, value: str) -> str:
    memory.set_fact(key, value)
    return f"Eslab qolindi: {key} = {value}"


@skill(
    description="Xotiradagi faktni o'chiradi.",
    params={"key": {"type": "string", "description": "O'chiriladigan fakt kaliti"}},
)
def forget_fact(key: str) -> str:
    return "O'chirildi" if memory.delete_fact(key) else "Bunday fakt topilmadi"


@skill(description="Xotiradagi barcha faktlarni ko'rsatadi.")
def list_facts() -> str:
    facts = memory.all_facts()
    return "\n".join(f"{k}: {v}" for k, v in facts.items()) or "Xotira bo'sh"
