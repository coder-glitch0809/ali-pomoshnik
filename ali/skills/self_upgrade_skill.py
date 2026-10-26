"""Ali o'zini kuchaytiradi: Dasturchi agent kod yozadi, testlar o'tsa - main'ga qo'shiladi va GitHub'ga push qilinadi.

Ruxsatlar -> "ali_kuchaytirish": "auto" - so'ramasdan qo'llaydi va push qiladi; "ask" - har safar tasdiq.
"""
from .. import self_upgrade
from . import skill


@skill(
    description=(
        "Ali'ning O'Z kodiga yangi imkoniyat qo'shadi yoki xatosini tuzatadi (Dasturchi agent + Claude Code, alohida nusxada). "
        "Testlar o'tsa - qo'llanadi, GitHub'ga push qilinadi va Ali qayta ishga tushadi. 10-40 daqiqa davom etadi."
    ),
    params={"task": {"type": "string", "description": "Nima qo'shish yoki tuzatish kerak (egasining so'zlari bilan, batafsil)"}},
    dangerous=True,
)
def ali_kuchaytirish(task: str) -> str:
    res = self_upgrade.run(task, lambda note: None)
    if not res["ok"]:
        return f"Testlar o'tmadi - o'zgarish bekor qilindi.\n{res['tests']}\n\n{res['report'][-1500:]}"
    pushed = self_upgrade.apply(res["id"])
    self_upgrade.restart_later(5)
    return f"Qo'llandi ({pushed}), {res['tests']}. Ali 5 soniyada qayta ishga tushadi.\n\n{res['report'][-2000:]}"
