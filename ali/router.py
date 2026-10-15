"""So'rovni avtomatik yo'naltirish: til va Office fayli turini aniqlab, Ali'ga qaysi agentni ishlatishni aytadi.

- Rus tilidagi xabar -> 💻 Учитель информатики (javob ruscha).
- Taqdimot / Excel / Word so'ralsa -> 📊 Office ekspert haqiqiy faylni yaratadi va u avtomatik yuboriladi.
O'zbek tili kirillda ham yoziladi, shuning uchun til harfga emas, so'z va qo'shimchalarga qarab aniqlanadi.
"""
import re

INFORMATIKA, OFFICE = "informatika", "office"

_WORD = re.compile(r"[a-zа-яёўқғҳ']+", re.I)
_UZ_LETTERS = set("ўқғҳЎҚҒҲ")
# Rus tiliga xos so'zlar (o'zbek kirillida uchramaydi)
_RU = {
    "и", "в", "не", "на", "что", "как", "это", "мне", "меня", "для", "по", "с", "я", "ты", "вы", "мы", "он", "она",
    "сделай", "сделайте", "сделать", "создай", "создайте", "напиши", "напишите", "нужно", "нужна", "нужен", "надо",
    "пожалуйста", "можно", "можешь", "помоги", "помогите", "объясни", "объясните", "расскажи", "покажи", "почему",
    "какой", "какая", "какие", "который", "где", "когда", "или", "но", "так", "еще", "ещё", "уже", "очень", "есть",
    "тема", "теме", "урок", "урока", "ученик", "ученики", "учитель", "класс", "класса", "задача", "задачу", "тест",
    "презентацию", "презентация", "таблицу", "таблица", "документ", "про", "о", "об", "из", "от", "до", "за", "к",
    "у", "же", "бы", "ли", "весь", "все", "всё", "этот", "эта", "эти", "его", "её", "их", "привет", "здравствуйте",
    "спасибо", "хорошо", "давай", "дай", "дайте", "сколько", "зачем", "чтобы", "если", "только", "также", "кто",
}
# O'zbek kirilli so'zlari va qo'shimchalari
_UZ = {
    "ва", "учун", "билан", "керак", "менга", "мен", "сен", "сиз", "нима", "бу", "шу", "ҳам", "хам", "йоки", "ёки",
    "қилиб", "килиб", "қил", "кил", "бер", "бериб", "ташлаб", "қандай", "кандай", "лозим", "бўйича", "бойича",
    "ҳақида", "хакида", "тайёрла", "тайерла", "ёз", "йоз", "яхши", "чиройли", "катта", "кичик", "бир", "икки",
    "агар", "лекин", "энди", "ҳозир", "хозир", "салом", "раҳмат", "рахмат", "мумкин", "қачонки", "качонки", "борми",
}
_UZ_SUFFIX = re.compile(r"(лар|ларни|ларга|ни|га|да|дан|нинг|ган|ди|миз|сиз|ман|сан|моқда|мокда|япти|йапти|иб|ишни)$")
_RU_SUFFIX = re.compile(r"(ться|тся|ешь|ете|ого|ему|ыми|ими|ость|ения|ание|ировать|ующий|ая|ое|ые|ий|ый)$")

# Office: (fayl turi, kalit so'z ildizlari) - ruscha, o'zbekcha (lotin va kirill), inglizcha va tez-tez xatolar
OFFICE_KINDS = {
    "pptx": ("презентац", "презинтац", "презентатц", "презинтатц", "слайд", "powerpoint", "power point", "пауэрпоинт",
             "повер поинт", "поверпоинт", "pptx", "taqdimot", "тақдимот", "такдимот", "prezentatsiya", "prezentatsiy",
             "presentation", "slide"),
    "xlsx": ("excel", "эксель", "ексель", "эхзел", "эхсел", "exel", "xlsx", "электронн таблиц", "spreadsheet"),
    "docx": ("word", "ворд", "docx", "реферат", "доклад", "referat", "doklad", "конспект", "заявлени"),
}
# Ko'p ma'noli so'zlar ("dars jadvali", "hujjat nima") - faqat "tuz/tayyorla/сделай" kabi buyruq bilan fayl deb olinadi
WEAK_KINDS = {
    "xlsx": ("jadval", "жадвал", "таблиц"),
    "docx": ("hujjat", "ҳужжат", "хужжат", "документ", "ariza", "ариза"),
}
_ACTION = ("tuz", "туз", "tayyorla", "тайёрла", "тайерла", "qilib ber", "килиб бер", "қилиб бер", "yarat", "ярат",
           "chiqar", "чиқар", "чикар", "fayl", "файл", "сделай", "создай", "составь", "подготовь", "оформи", "сделать",
           "создать", "составить", "make", "create")
KIND_NAMES = {"pptx": "PowerPoint taqdimot (make_presentation)", "xlsx": "Excel jadval (make_excel)",
              "docx": "Word hujjat (make_word)"}


def language(text: str) -> str:
    """'ru', 'uz' yoki 'other'."""
    if any(ch in _UZ_LETTERS for ch in text):
        return "uz"
    words = [w.lower() for w in _WORD.findall(text)]
    cyr = [w for w in words if re.search(r"[а-яё]", w)]
    if len(cyr) < max(1, len(words) // 2):
        return "other"
    ru = sum(w in _RU for w in cyr) + 0.5 * sum(bool(_RU_SUFFIX.search(w)) and w not in _UZ for w in cyr)
    uz = sum(w in _UZ for w in cyr) + 0.5 * sum(bool(_UZ_SUFFIX.search(w)) and w not in _RU for w in cyr)
    if ru > uz:
        return "ru"
    return "uz" if uz > 0 else "ru" if ru > 0 else "other"


def office_kinds(text: str) -> list[str]:
    low = text.lower()
    acting = any(a in low for a in _ACTION)
    return [kind for kind, roots in OFFICE_KINDS.items()
            if any(r in low for r in roots) or (acting and any(r in low for r in WEAK_KINDS.get(kind, ())))]


def hint(text: str, team: dict) -> str:
    """Ali'ga beriladigan yo'naltirish ko'rsatmasi ('' - maxsus yo'naltirish kerak emas)."""
    lang = language(text)
    kinds = office_kinds(text)
    teacher = INFORMATIKA in team and lang == "ru"
    office = OFFICE in team and bool(kinds)
    if not teacher and not office:
        return ""
    lines = ["[Avtomatik yo'naltirish - tizim ko'rsatmasi, foydalanuvchi matni emas]"]
    if teacher and office:
        lines.append(f"Xabar rus tilida va fayl so'ralgan: {', '.join(KIND_NAMES[k] for k in kinds)}. "
                     f"1) ask_agent bilan '{INFORMATIKA}' agentidan mazmunni RUS tilida tayyorlat (o'qituvchi metodikasi bilan). "
                     f"2) ask_agent bilan '{OFFICE}' agentiga shu to'liq mazmunni berib, faylni yaratishni topshir "
                     "(fayl matni rus tilida). Ikkalasini ham albatta ishga tushir.")
    elif teacher:
        lines.append(f"Xabar rus tilida: ask_agent bilan '{INFORMATIKA}' (Учитель информатики) agentiga topshir "
                     "va uning javobini to'liq, rus tilida yetkaz.")
    else:
        lines.append(f"Fayl so'ralgan: {', '.join(KIND_NAMES[k] for k in kinds)}. ask_agent bilan '{OFFICE}' agentiga "
                     "to'liq topshiriq ber; agent haqiqiy faylni yaratsin (matn foydalanuvchi tilida).")
    if office:
        lines.append("Fayl javob bilan birga foydalanuvchiga AVTOMATIK yuboriladi: havola yoki yo'l to'qima, "
                     "qisqa ayt: nima tayyorlandi, nechta slayd/varaq/bo'lim.")
    return "\n".join(lines) + "\n\n"
