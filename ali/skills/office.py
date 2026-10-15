"""Discover document tooling without starting Office or changing user files."""
import importlib.util
import json
import platform
import shutil
import sys

from . import skill


@skill(description="Office vazifasidan oldin Python yo‘li, Word/Excel/PowerPoint kutubxonalari va render vositasi mavjudligini tekshiradi. Microsoft Office o‘rnatilganligini kafolatlamaydi.")
def office_capabilities() -> str:
    packages = {name: importlib.util.find_spec(module) is not None for name, module in
                {'python-docx':'docx', 'openpyxl':'openpyxl', 'python-pptx':'pptx'}.items()}
    return json.dumps({'platform':platform.system(), 'python':sys.executable, 'packages':packages,
                       'libreoffice':shutil.which('soffice') or shutil.which('libreoffice'),
                       'desktop_office':'Not verified; desktop/API connection must be checked for native operations.',
                       'formula_calculation':'openpyxl writes formulas but does not calculate them.'}, ensure_ascii=False)
