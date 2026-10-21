"""Owner-managed tool permissions. Models cannot edit this policy through a tool."""
import json
import threading
from datetime import datetime, timezone

from .config import config

PATH = config.data_dir / 'permissions.json'
AUDIT = config.data_dir / 'permissions-activity.jsonl'
LOCK = threading.RLock()
MODES = {'auto', 'ask', 'deny'}
REVIEW_DEFAULT = {'create_agent', 'github_clone', 'open_application', 'forget_fact'}


def load() -> dict:
    with LOCK:
        try:
            data = json.loads(PATH.read_text(encoding='utf-8'))
            if not isinstance(data, dict) or not isinstance(data.get('rules'), dict):
                raise ValueError('Invalid policy')
            if any(v not in MODES for v in data['rules'].values()):
                raise ValueError('Invalid rule')
            return data
        except FileNotFoundError:
            return {'rules': {}}
        except (OSError, ValueError, TypeError):
            return {'rules': {}, 'unavailable': True}


def mode(name, dangerous=False):
    data = load()
    if data.get('unavailable'):
        return 'deny'
    rule = data['rules'].get(name)
    if config.full_access:  # o'z kompyuterida to'liq ruxsat: faqat egasi qo'lda taqiqlagani bloklanadi
        return 'deny' if rule == 'deny' else 'auto'
    return rule or ('ask' if dangerous or name in REVIEW_DEFAULT else 'auto')


def save(rules, registry):
    valid = set(registry) | {'web_search'}
    if not isinstance(rules, dict) or any(k not in valid or v not in MODES for k,v in rules.items()):
        raise ValueError('Noma’lum vosita yoki noto‘g‘ri ruxsat.')
    if rules.get('web_search') == 'ask':
        raise ValueError('Internet qidiruvi uchun avtomatik yoki taqiqlangan rejimni tanlang.')
    with LOCK:
        data = {'rules': rules, 'updated_at': datetime.now(timezone.utc).isoformat()}
        temp = PATH.with_suffix('.tmp')
        temp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        temp.replace(PATH)
        audit('settings', 'saved')
    return data


# Windows o'rnatuvchisidagi ruxsat guruhlari -> vosita modullari (ali/skills/*.py, ali/plugins/*.py)
INSTALL_GROUPS = {
    'pc': {'pc', 'coding'},
    'screen': set(),  # take_screenshot - nomi bo'yicha
    'apps': {'system'},
    'files': {'projects', 'office'},
    'photoshop': {'photoshop'},
    'coreldraw': {'coreldraw'},
    'ai': {'gemini', 'chatgpt'},
    'online': {'github', 'vercel', 'instagram'},
}


def _install_group(skill):
    if skill.name == 'take_screenshot':
        return 'screen'
    module = skill.func.__module__.rsplit('.', 1)[-1]
    return next((g for g, mods in INSTALL_GROUPS.items() if module in mods), None)


def apply_install_choice(registry):
    """Birinchi ishga tushishda: o'rnatishda belgilanmagan guruhlar vositalarini taqiqlaydi.
    Keyin egasi Ruxsatlar bo'limida istalganini qayta yoqishi mumkin."""
    allowed = config.install_groups
    if allowed is None or PATH.exists():
        return
    rules = {s.name: 'deny' for s in registry.values() if (g := _install_group(s)) and g not in allowed}
    save(rules, registry)
    audit('install', 'applied')


def audit(name, outcome):
    # Never record passwords, tool arguments, message bodies or tokens here.
    with LOCK:
        with AUDIT.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'at': datetime.now(timezone.utc).isoformat(), 'tool': name, 'outcome': outcome})+'\n')


def catalog(registry):
    data = load()
    rows = [{'name': s.name, 'description': s.description, 'group': s.func.__module__.rsplit('.',1)[-1],
             'dangerous': s.dangerous or s.name in REVIEW_DEFAULT, 'mode': mode(s.name,s.dangerous)} for s in registry.values()]
    rows.append({'name':'web_search','description':'Internetdan ma’lumot qidirish','group':'knowledge','dangerous':False,'mode':mode('web_search')})
    return {'tools':rows,'updated_at':data.get('updated_at'),'unavailable':data.get('unavailable',False)}
