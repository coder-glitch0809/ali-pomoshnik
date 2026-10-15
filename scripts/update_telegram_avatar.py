"""Apply the locally reviewed Ali portrait without logging credentials."""
from pathlib import Path
import json
import sys
import httpx
from PIL import Image
from dotenv import dotenv_values

root=Path(__file__).resolve().parents[1]
source=root/'web/assets/ali-telegram-avatar.png'
target=source.with_suffix('.jpg')
Image.open(source).convert('RGB').save(target,quality=94)
token=dotenv_values(root/'.env').get('TELEGRAM_BOT_TOKEN','')
try:
    with target.open('rb') as photo:
        response=httpx.post(f'https://api.telegram.org/bot{token}/setMyProfilePhoto',
            data={'photo':json.dumps({'type':'static','photo':'attach://avatar'})},
            files={'avatar':('ali.jpg',photo,'image/jpeg')},timeout=45)
    result=response.json()
    print(json.dumps({'updated':bool(result.get('ok')),'status':response.status_code}))
except Exception:
    print('Profile update could not reach Telegram.')
    sys.exit(1)
