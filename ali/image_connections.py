"""Separate API credential setup from a verified image-generation capability."""
import asyncio
import hashlib
import io
import json
import re
import threading
from datetime import datetime, timezone

from dotenv import set_key
from .config import config

STATE = config.data_dir / 'image_connections.json'
LOCK = threading.RLock()
TEST_LOCK = threading.Lock()
FIELDS = {
    'chatgpt': {'model': ('openai_image_model', 'OPENAI_IMAGE_MODEL')},
    'gemini': {'model': ('gemini_image_model', 'GEMINI_IMAGE_MODEL'),
               'pro_model': ('gemini_image_pro_model', 'GEMINI_IMAGE_PRO_MODEL')},
}


def _identity(key):
    token = config.openai_api_key if key == 'chatgpt' else config.gemini_api_key
    values = [token, config.image_quality, *[getattr(config, field) for field, _ in FIELDS[key].values()]]
    return hashlib.sha256(json.dumps(values).encode()).hexdigest()


def _state():
    try:
        data = json.loads(STATE.read_text(encoding='utf8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def status(key):
    with LOCK:
        saved = _state().get(key, {})
    if saved.get('identity') != _identity(key):
        return {'ok': None, 'message': 'Rasm yaratish hali tekshirilmagan', 'at': ''}
    return {k: saved.get(k) for k in ('ok', 'message', 'at', 'file')}


def reset(key):
    from . import providers, story_video
    if key == 'gemini':
        providers._gemini = None
        providers._gemini_good.clear()
    else:
        providers._openai = None
    story_video._image_cooldowns.clear()


async def configure(key, values):
    if key not in FIELDS or not isinstance(values, dict):
        raise ValueError('Rasm provayderi yoki sozlamasi noto‘g‘ri')
    if set(values) - (set(FIELDS[key]) | {'quality'}):
        raise ValueError('Noma’lum rasm sozlamasi')
    updates = []
    for name, value in values.items():
        if name == 'quality':
            if value not in ('pro', 'standard'):
                raise ValueError('Sifat: pro yoki standard bo‘lishi kerak')
            updates.append(('image_quality', 'IMAGE_QUALITY', value))
        else:
            if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,119}', value):
                raise ValueError('Model identifikatorini to‘liq kiriting')
            updates.append((*FIELDS[key][name], value))
    from . import connections
    async with connections._lock:
        for field, env, value in updates:
            await asyncio.to_thread(set_key, str(connections.ENV_FILE), env, value)
            setattr(config, field, value)
        reset(key)
    return {'ok': True, 'message': 'Rasm sozlamalari saqlandi. Endi sinov rasmini yarating.'}


def test_image(key):
    if key not in FIELDS:
        raise ValueError('Noma’lum rasm provayderi')
    token = config.openai_api_key if key == 'chatgpt' else config.gemini_api_key
    if not token:
        raise ValueError('Avval shu xizmatning API kalitini tekshirib saqlang')
    if not TEST_LOCK.acquire(blocking=False):
        raise ValueError('Rasm sinovi davom etmoqda; tugashini kuting')
    identity = _identity(key)
    result = {'identity': identity, 'at': datetime.now(timezone.utc).isoformat(), 'file': ''}
    try:
        from . import providers, outbox
        from PIL import Image
        prompt = 'A small blue ceramic cup beside a green plant on a wooden desk, daylight, detailed illustration, no text.'
        if key == 'chatgpt':
            data = providers._openai_image(prompt, 'high' if config.image_quality == 'pro' else 'medium')
        else:
            model = config.gemini_image_pro_model if config.image_quality == 'pro' else config.gemini_image_model
            data = providers.generate_image(prompt, model)
        image = Image.open(io.BytesIO(data))
        image.load()
        if min(image.size) < 256:
            raise ValueError('Image too small')
        output = outbox.new_path(key + '_ulanish_sinovi', 'png')
        image.convert('RGB').save(output, 'PNG')
        outbox.register(output)
        result.update(ok=True, message='Rasm yaratildi va tekshirildi', file=output.name)
        reset(key)
    except Exception as error:
        raw = str(error).lower()
        code = getattr(error, 'status_code', None) or getattr(error, 'code', None)
        if code in (401, 403) or any(t in raw for t in ('401', '403', 'permission', 'api_key_invalid')):
            message = 'Kalit yoki rasm modeli ruxsati tasdiqlanmadi. Kalit va loyiha ruxsatlarini tekshiring.'
        elif code in (402, 429) or any(t in raw for t in ('402', '429', 'quota', 'resource_exhausted', 'billing')):
            message = 'API kvotasi, kredit yoki billing cheklovi. Hisobdagi limitlarni tekshiring.'
        elif '404' in raw or 'not found' in raw:
            message = 'Rasm modeli topilmadi. Model nomi va hisob uchun mavjudligini tekshiring.'
        else:
            message = 'Rasm yaratilmadi. Internet, model va xizmat holatini tekshirib qayta urinib ko‘ring.'
        result.update(ok=False, message=message)
    finally:
        TEST_LOCK.release()
    with LOCK:
        saved = _state()
        saved[key] = result
        STATE.parent.mkdir(parents=True, exist_ok=True)
        temp = STATE.with_suffix('.tmp')
        temp.write_text(json.dumps(saved, ensure_ascii=False), encoding='utf8')
        temp.replace(STATE)
    return {k: result[k] for k in ('ok', 'message', 'at', 'file')}
