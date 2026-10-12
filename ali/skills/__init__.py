"""Ko'nikmalar (skills) reyestri.

Yangi ko'nikma qo'shish uchun shu papkaga yangi .py fayl yarating va funksiyani
@skill bilan belgilang - u avtomatik topiladi va Claude'ga vosita (tool) sifatida beriladi:

    from . import skill

    @skill(
        description="Ob-havoni aytadi",
        params={"city": {"type": "string", "description": "Shahar nomi"}},
    )
    def get_weather(city: str) -> str:
        return "..."

dangerous=True bo'lsa, bajarishdan oldin foydalanuvchidan tasdiq so'raladi.
"""
import importlib
import pkgutil
from dataclasses import dataclass
from typing import Any, Callable

_TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "array": list, "object": dict}


@dataclass
class Skill:
    name: str
    description: str
    params: dict[str, dict]
    required: list[str]
    func: Callable[..., Any]
    dangerous: bool = False

    def to_tool(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": self.params,
                "required": self.required,
                "additionalProperties": False,
            },
            # Oqimda (stream) argumentlar darhol keladi; shuning uchun validate() o'zimiz tekshiradi
            "eager_input_streaming": True,
        }

    def validate(self, args: Any) -> str | None:
        """Xato bo'lsa matn qaytaradi, to'g'ri bo'lsa None."""
        if not isinstance(args, dict):
            return "Argumentlar obyekt bo'lishi kerak"
        for name in self.required:
            if name not in args:
                return f"Majburiy argument yo'q: {name}"
        for name, value in args.items():
            spec = self.params.get(name)
            if spec is None:
                return f"Noma'lum argument: {name}"
            expected = _TYPES.get(spec.get("type", ""))
            if expected and not isinstance(value, expected):
                return f"'{name}' turi noto'g'ri, kutilgan: {spec['type']}"
        return None


REGISTRY: dict[str, Skill] = {}


def skill(description: str, params: dict | None = None, required: list[str] | None = None,
          dangerous: bool = False, name: str | None = None):
    params = params or {}

    def wrap(func):
        s = Skill(
            name=name or func.__name__,
            description=description,
            params=params,
            required=list(params) if required is None else required,
            func=func,
            dangerous=dangerous,
        )
        REGISTRY[s.name] = s
        return func

    return wrap


def load_all() -> dict[str, Skill]:
    """Papkadagi barcha modullarni import qiladi (har biri o'z ko'nikmalarini ro'yxatdan o'tkazadi)."""
    for mod in pkgutil.iter_modules(__path__):
        if not mod.name.startswith("_"):
            importlib.import_module(f"{__name__}.{mod.name}")
    return REGISTRY
