"""Office fayllarini serverning o'zida yaratish: Word (.docx) va Excel (.xlsx). PowerPoint - presentation.py.

Fayl outbox'ga yoziladi va so'rov tugagach Telegram/saytga avtomatik yuboriladi. Skript yozish yoki tasdiq shart emas.
"""
from __future__ import annotations

import re

from .. import outbox
from . import skill

def _clean(value, limit: int = 600) -> str:
    return " ".join(str(value or "").split())[:limit]


def _list(value, limit: int = 40) -> list[str]:
    if isinstance(value, str):
        value = [v for v in re.split(r"\n+", value) if v.strip()]
    return [_clean(v, 400) for v in (value or []) if _clean(v)][:limit]


# ---------------------------------------------------------------- Word
@skill(
    description=(
        "Professional Word (.docx) hujjat yaratadi: sarlavha sahifasi, mundarija (ixtiyoriy), bo'lim sarlavhalari, "
        "paragraflar, punkt va raqamli ro'yxatlar, jadvallar, sahifa raqamlari. Referat, doklad, dars ishlanmasi, "
        "ariza, xat, hisobot, test uchun. Fayl foydalanuvchiga AVTOMATIK yuboriladi. sections: [{heading, level (1|2), "
        "paragraphs: [...], bullets: [...], numbered: [...], table: [[sarlavhalar], [qator]...]}]."
    ),
    params={
        "title": {"type": "string", "description": "Hujjat nomi"},
        "subtitle": {"type": "string", "description": "Kichik sarlavha / muallif / sana"},
        "sections": {"type": "array", "items": {"type": "object"}, "description": "Bo'limlar"},
        "toc": {"type": "boolean", "description": "Mundarija qo'shish (Word'da F9 bilan yangilanadi)"},
        "title_page": {"type": "boolean", "description": "Alohida sarlavha sahifasi (standart false)"},
    },
    required=["title", "sections"],
)
def make_word(title: str, sections: list, subtitle: str = "", toc: bool = False, title_page: bool = False) -> str:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt, RGBColor

    title = _clean(title, 150) or "Hujjat"
    doc = Document()
    styles = doc.styles
    styles["Normal"].font.name, styles["Normal"].font.size = "Calibri", Pt(12)
    for name, size in (("Heading 1", 16), ("Heading 2", 13), ("Title", 26)):
        styles[name].font.name, styles[name].font.size = "Calibri", Pt(size)
        styles[name].font.color.rgb = RGBColor.from_string("1F4E99")

    def field(paragraph, code: str):
        run = paragraph.add_run()
        for tag, text in (("begin", None), (None, code), ("separate", None), ("end", None)):
            if tag:
                el = OxmlElement("w:fldChar")
                el.set(qn("w:fldCharType"), tag)
            else:
                el = OxmlElement("w:instrText")
                el.set(qn("xml:space"), "preserve")
                el.text = text
            run._r.append(el)

    head = doc.add_paragraph(title, style="Title")
    head.alignment = WD_ALIGN_PARAGRAPH.CENTER if title_page else WD_ALIGN_PARAGRAPH.LEFT
    if subtitle:
        p = doc.add_paragraph(_clean(subtitle, 300))
        p.alignment = head.alignment
        p.runs[0].italic = True
    if title_page:
        doc.add_page_break()
    if toc:
        doc.add_paragraph("Mundarija / Содержание", style="Heading 1")
        field(doc.add_paragraph(), 'TOC \\o "1-2" \\h \\z \\u')
        doc.add_page_break()
    tables = 0
    for raw in (sections or [])[:60]:
        if not isinstance(raw, dict):
            continue
        if raw.get("heading"):
            doc.add_heading(_clean(raw["heading"], 200), level=2 if raw.get("level") == 2 else 1)
        for text in _list(raw.get("paragraphs"), 60):
            p = doc.add_paragraph(text)
            p.paragraph_format.space_after = Pt(6)
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        for text in _list(raw.get("bullets"), 60):
            doc.add_paragraph(text, style="List Bullet")
        for text in _list(raw.get("numbered"), 60):
            doc.add_paragraph(text, style="List Number")
        rows = raw.get("table")
        if isinstance(rows, list) and rows and all(isinstance(r, list) for r in rows):
            rows = [[_clean(c, 300) for c in r[:10]] for r in rows[:200]]
            cols = max(len(r) for r in rows)
            table = doc.add_table(rows=len(rows), cols=cols)
            table.style = "Light Grid Accent 1"
            for r, row in enumerate(rows):
                for c in range(cols):
                    table.cell(r, c).text = row[c] if c < len(row) else ""
            tables += 1
            doc.add_paragraph()
    footer = doc.sections[0].footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    field(footer, "PAGE")
    path = outbox.new_path(title, "docx")
    doc.save(path)
    paragraphs = len(Document(path).paragraphs)
    outbox.register(path)
    return (f"✅ Word tayyor: {path.name} ({paragraphs} paragraf, {tables} jadval). Fayl javob bilan birga avtomatik "
            "yuboriladi." + (" Mundarija Word'da ochilganda F9 bilan yangilanadi." if toc else ""))


# ---------------------------------------------------------------- Excel
_DANGEROUS_FORMULA = re.compile(r"\|| DDE|WEBSERVICE|FILTERXML|CALL\(|REGISTER\(|EXEC\(|HYPERLINK\(", re.I)


def _cell_value(value):
    if isinstance(value, str):
        value = value.strip()
        if value.startswith("="):
            return value if not _DANGEROUS_FORMULA.search(value) else "'" + value
        number = value.replace(" ", "").replace(",", ".")
        if re.fullmatch(r"-?\d+(\.\d+)?", number) and not (len(number) > 1 and number.startswith("0") and "." not in number):
            return float(number) if "." in number else int(number)
    return value


@skill(
    description=(
        "Chiroyli Excel (.xlsx) fayl yaratadi: bir nechta varaq, rangli sarlavha, filtr, muzlatilgan sarlavha, ustun kengligi, "
        "raqam formatlari, formulalar (\"=SUM(B2:B10)\" kabi), avtomatik JAMI qatori va diagramma. Jurnal, baholar, "
        "byudjet, hisobot, jadval uchun. Fayl foydalanuvchiga AVTOMATIK yuboriladi. sheets: [{name, columns: [...], "
        "rows: [[...]], totals: true|false, number_format: \"#,##0.00\", chart: {type: column|bar|line|pie, title, "
        "x_col: 1, y_cols: [2,3]}}]. Formulalar Excel ochilganda hisoblanadi."
    ),
    params={
        "title": {"type": "string", "description": "Fayl nomi"},
        "sheets": {"type": "array", "items": {"type": "object"}, "description": "Varaqlar"},
    },
    required=["title", "sheets"],
)
def make_excel(title: str, sheets: list) -> str:
    from openpyxl import Workbook, load_workbook
    from openpyxl.chart import BarChart, LineChart, PieChart, Reference
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    title = _clean(title, 120) or "Jadval"
    wb = Workbook()
    wb.remove(wb.active)
    thin = Side(style="thin", color="D0D7E2")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    used: set[str] = set()
    summary = []
    for index, raw in enumerate((sheets or [])[:20]):
        if not isinstance(raw, dict):
            continue
        name = re.sub(r"[\[\]:*?/\\]", "", _clean(raw.get("name"), 31)) or f"Varaq{index + 1}"
        while name in used:
            name = (name[:28] + f"_{index}")[:31]
        used.add(name)
        ws = wb.create_sheet(name)
        columns = [_clean(c, 80) for c in raw.get("columns") or []][:50]
        rows = [r for r in (raw.get("rows") or []) if isinstance(r, list)][:5000]
        width = max([len(columns)] + [len(r) for r in rows] + [1])
        if columns:
            ws.append(columns + [""] * (width - len(columns)))
        for r in rows:
            ws.append([_cell_value(v) for v in r[:width]])
        first_data = 2 if columns else 1
        last = ws.max_row
        if raw.get("totals") and rows and columns:
            total_row = last + 1
            ws.cell(total_row, 1, "JAMI / ИТОГО").font = Font(bold=True)
            for c in range(2, width + 1):
                if any(isinstance(ws.cell(r, c).value, (int, float)) for r in range(first_data, last + 1)):
                    letter = get_column_letter(c)
                    ws.cell(total_row, c, f"=SUM({letter}{first_data}:{letter}{last})").font = Font(bold=True)
            for c in range(1, width + 1):
                ws.cell(total_row, c).fill = PatternFill("solid", fgColor="FFF2CC")
        fmt = _clean(raw.get("number_format"), 30)
        for row in ws.iter_rows(min_row=first_data, max_row=ws.max_row, max_col=width):
            for cell in row:
                cell.border = border
                if fmt and isinstance(cell.value, float):
                    cell.number_format = fmt
                elif isinstance(cell.value, float):
                    cell.number_format = "#,##0.00"
                elif isinstance(cell.value, int) and abs(cell.value) >= 1000:
                    cell.number_format = "#,##0"
        if columns:
            for c in range(1, width + 1):
                cell = ws.cell(1, c)
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill("solid", fgColor="1F4E99")
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
                cell.border = border
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = f"A1:{get_column_letter(width)}{last}"
            ws.row_dimensions[1].height = 28
        for c in range(1, width + 1):
            longest = max((len(str(ws.cell(r, c).value or "")) for r in range(1, min(ws.max_row, 300) + 1)), default=8)
            ws.column_dimensions[get_column_letter(c)].width = min(60, max(10, longest + 3))
        chart_spec = raw.get("chart")
        if isinstance(chart_spec, dict) and columns and last >= first_data:
            kind = chart_spec.get("type", "column")
            chart = PieChart() if kind == "pie" else LineChart() if kind == "line" else BarChart()
            if isinstance(chart, BarChart):
                chart.type = "bar" if kind == "bar" else "col"
            chart.title = _clean(chart_spec.get("title"), 80) or name
            chart.height, chart.width = 9, 18
            x_col = int(chart_spec.get("x_col") or 1)
            y_cols = [int(c) for c in chart_spec.get("y_cols") or [2] if isinstance(c, (int, float)) and 1 <= c <= width]
            for c in (y_cols[:1] if kind == "pie" else y_cols[:6]):
                chart.add_data(Reference(ws, min_col=c, min_row=1, max_row=last), titles_from_data=True)
            chart.set_categories(Reference(ws, min_col=x_col, min_row=first_data, max_row=last))
            ws.add_chart(chart, f"{get_column_letter(width + 2)}2")
        summary.append(f"{name}: {len(rows)} qator")
    if not wb.sheetnames:
        return "sheets bo'sh: kamida bitta varaq kerak."
    path = outbox.new_path(title, "xlsx")
    wb.save(path)
    load_workbook(path)  # qayta ochib tekshirish
    outbox.register(path)
    return (f"✅ Excel tayyor: {path.name} ({'; '.join(summary)}). Formulalar Excel ochilganda hisoblanadi. "
            "Fayl javob bilan birga avtomatik yuboriladi.")
