"""ChatPlace (MCP): Instagram/Telegram avtomatlashtirish, chatlar, xabar tarqatish, AI agent, izohlar, botlar.

O'qish - erkin; o'zgartirish (avtojavob, tarqatma, xabar, bot sozlamasi) - har safar egasining tasdig'i bilan.
"""
import json

from .. import mcp_client
from . import skill


@skill(description="ChatPlace'dagi barcha vositalar ro'yxati (nomi va nima qilishi) - qaysi birini chaqirishni bilish uchun.")
def chatplace_tools() -> str:
    tools = mcp_client.list_tools("chatplace")
    return "\n".join(f"- {t['name']}: {(t.get('description') or '')[:160]}" for t in tools) or "Vosita yo'q."


@skill(
    description=(
        "ChatPlace'dan MA'LUMOT o'qiydi (faqat o'qish vositalari: list/get/search/stats...): avtomatlashtirishlar, "
        "chatlar va xabarlar, tarqatmalar statistikasi, izohlar, botlar, teglar. Avval chatplace_tools bilan nomni top."
    ),
    params={"tool": {"type": "string", "description": "Vosita nomi (chatplace_tools ro'yxatidan)"},
            "arguments": {"type": "object", "description": "Vosita argumentlari (JSON)"}},
    required=["tool"],
)
def chatplace_read(tool: str, arguments: dict | None = None) -> str:
    if is_write(tool):
        return "Bu vosita ma'lumotni o'zgartiradi - chatplace_action dan foydalan (tasdiq so'raladi)."
    return mcp_client.call_tool("chatplace", tool, arguments or {})


WRITE_WORDS = ("create", "update", "delete", "send", "set", "change", "apply", "register", "open", "close", "connect",
               "attach", "detach", "start", "stop", "cancel", "add", "remove", "upload", "assign", "unassign", "edit",
               "publish", "reply", "hide", "copy", "duplicate", "move", "enable", "disable", "pause", "resume", "test")


READ_WORDS = ("list", "get", "analytics", "report", "status", "clients", "messages", "dashboard", "recommendations",
              "balance", "estimate", "examples", "reference", "predict", "questions", "stats")
WRITE_WORDS += ("setup", "unpublish", "generate", "quick", "build", "import", "sync", "subscribe", "unsubscribe")


def is_write(tool: str) -> bool:
    """Xavfsiz tomonga: nomida aniq o'qish so'zi bo'lib, hech qanday o'zgartirish so'zi bo'lmasa - o'qish.
    Qolgan hammasi (yaratish, yuborish, sozlash, AI generatsiya - balans sarflaydi) tasdiq bilan."""
    words = set(tool.lower().replace("-", "_").split("_"))
    return bool(words & set(WRITE_WORDS)) or not (words & set(READ_WORDS))


@skill(
    description=(
        "ChatPlace'da O'ZGARISH qiladi: avtojavob/avtomatlashtirish yaratish yoki tahrirlash, xabar yoki tarqatma yuborish, "
        "teg qo'yish, bot va AI agent sozlamasi. Egasiga nima qilinishini aniq ko'rsatib, tasdiq olinadi."
    ),
    params={"tool": {"type": "string", "description": "Vosita nomi"},
            "arguments": {"type": "object", "description": "Vosita argumentlari (JSON)"}},
    required=["tool"],
    dangerous=True,
)
def chatplace_action(tool: str, arguments: dict | None = None) -> str:
    return mcp_client.call_tool("chatplace", tool, arguments or {})
