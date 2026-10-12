"""O'rganish: Ali yangi mavzularni o'rganib, bilimlar bazasiga yozadi va keyin sizga o'rgatadi."""
from ..memory import memory
from . import skill


@skill(
    description=(
        "O'rganilgan bilimni doimiy bilimlar bazasiga saqlaydi. Yangi mavzuni web_search bilan o'rganganingdan keyin "
        "asosiy xulosalarni, manbalarni va amaliy maslahatlarni shu yerga yoz - keyingi safar qayta qidirish shart bo'lmaydi."
    ),
    params={
        "topic": {"type": "string", "description": "Mavzu nomi"},
        "content": {"type": "string", "description": "Tuzilgan xulosa: asosiy tushunchalar, faktlar, manbalar"},
    },
)
def save_knowledge(topic: str, content: str) -> str:
    kid = memory.add_knowledge(topic, content)
    return f"Bilim #{kid} saqlandi: {topic}"


@skill(
    description="Bilimlar bazasidan avval o'rganilgan ma'lumotni qidiradi. Internetdan qidirishdan oldin shu yerni tekshir.",
    params={"query": {"type": "string", "description": "Qidiruv so'zlari"}},
)
def search_knowledge(query: str) -> str:
    rows = memory.search_knowledge(query)
    if not rows:
        return "Topilmadi."
    return "\n\n".join(f"#{r['id']} [{r['topic']}] ({r['created_at'][:10]})\n{r['content']}" for r in rows)


@skill(description="Bilimlar bazasidagi barcha o'rganilgan mavzular ro'yxati.")
def list_knowledge_topics() -> str:
    return "\n".join(memory.knowledge_topics()) or "Hali hech narsa o'rganilmagan."
