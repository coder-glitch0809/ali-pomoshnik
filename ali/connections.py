"""Owner-only connection setup. Credentials never appear in catalog responses."""
import asyncio
import os
import re
import httpx
from dotenv import set_key
from .config import config, STATE_ROOT

ENV_FILE = STATE_ROOT / '.env'
_lock = asyncio.Lock()
PROVIDERS = {
    'telegram': dict(name='Telegram bot', url='https://t.me/BotFather', link='BotFather orqali sozlash',
        steps=['BotFather’da /mybots ni oching va Ali botini tanlang.', 'API Token bo‘limidan bot tokenini oling va pastga kiriting.', 'Saqlagach Ali serverini qayta ishga tushiring.'], field='telegram_token', env='TELEGRAM_BOT_TOKEN'),
    'instagram': dict(name='Instagram tahlili', url='https://developers.facebook.com/apps/', link='Meta orqali sozlash',
        steps=['Meta hisobingiz bilan kiring va Instagram ilovasini tanlang.', 'Professional Instagram hisobini ulang va kerakli tahlil ruxsatlarini bering.', 'Graph API tokenini kiriting. Hisob IDlarini serverdagi IG_ACCOUNTS sozlamasiga yozing.'], field='ig_access_token', env='IG_ACCESS_TOKEN'),
    'github': dict(name='GitHub', url='https://github.com/settings/personal-access-tokens/new', link='GitHub orqali davom etish',
        steps=['GitHub hisobingizga kiring va Ali uchun fine-grained token yarating.', 'Faqat kerakli repozitoriylarni tanlang. O‘qish uchun Contents: Read-only; tahrirlash kerak bo‘lsa Read and write ruxsatini bering.', 'Tokenni nusxalab pastga kiriting. Ali ulanishni tekshirib saqlaydi.'], field='github_token', env='GITHUB_TOKEN'),
    'vercel': dict(name='Vercel', url='https://vercel.com/account/settings/tokens', link='Vercel orqali davom etish',
        steps=['Vercel hisobingizga o‘zingiz ishlatadigan usul bilan kiring.', 'Ali uchun token yarating, kerakli jamoa va amal qilish muddatini tanlang.', 'Tokenni pastga kiriting va tekshirib saqlang.'], field='vercel_token', env='VERCEL_TOKEN'),
    'voice': dict(name='Ovoz', url='https://elevenlabs.io/app/settings/api-keys', link='ElevenLabs sozlamalari',
        steps=['Standart Edge ovozi alohida hisob talab qilmaydi.', 'Shaxsiy ovoz uchun ElevenLabs hisobiga kiring.', 'Serverda ELEVENLABS_API_KEY va ELEVENLABS_VOICE_ID ni sozlang.']),
    'google': dict(name='Google', url='https://console.cloud.google.com/auth/overview', link='Google orqali sozlash',
        steps=['Google hisobingiz bilan Cloud Console’ga kiring va loyiha tanlang.', 'Google Auth Platform’da OAuth ilovasi, ruxsatlar va Web client yarating.', 'Ali’da Google OAuth callback va Gmail/Drive vositalari hali o‘rnatilmagan. Hozir hisob ulash tugallanmaydi; bu sozlash yo‘riqnomasi.']),
    'meta': dict(name='Meta Ads', url='https://developers.facebook.com/apps/', link='Meta orqali sozlash',
        steps=['Meta hisobingizga kiring va Business ilovasini tanlang.', 'Marketing API va reklama hisobiga tegishli ruxsatlarni sozlang.', 'Ali’da Meta Ads boshqaruv vositasi hali o‘rnatilmagan. Hozir bu sozlash yo‘riqnomasi.']),
    'channels': dict(name='Telegram kanallari', url='https://telegram.org/faq_channels', link='Kanalni ulash yo‘riqnomasi',
        steps=['Telegram’da o‘z kanalingiz sozlamalarini oching.', 'Ali botini administrator qilib qo‘shing, faqat post joylash ruxsatini bering.', 'Kanalga avtomatik post vositasi hali o‘rnatilmagan. Botni qo‘shishning o‘zi avtomatik postni yoqmaydi.']),
    'gemini': dict(name='Gemini plagini', url='https://aistudio.google.com/apikey', link='Google AI Studio’da kalit olish', plugin='gemini',
        steps=['Google hisobingiz bilan AI Studio’ga kiring.', '“Create API key” tugmasi bilan kalit yarating.', 'Kalitni pastga kiriting - plagin avtomatik ishga tushadi.'], field='gemini_api_key', env='GEMINI_API_KEY'),
    'chatgpt': dict(name='ChatGPT plagini', url='https://platform.openai.com/api-keys', link='OpenAI’da kalit olish', plugin='chatgpt',
        steps=['OpenAI Platform hisobingizga kiring va balans borligini tekshiring.', '“Create new secret key” bilan Ali uchun kalit yarating.', 'Kalitni pastga kiriting - plagin avtomatik ishga tushadi.'], field='openai_api_key', env='OPENAI_API_KEY'),
    'photoshop': dict(name='Photoshop plagini', url='https://www.adobe.com/products/photoshop.html', link='Adobe Photoshop', plugin='photoshop',
        steps=['Photoshop shu kompyuterga o‘rnatilgan bo‘lsa, kalit kerak emas - Ali uni o‘zi topadi.', 'Ali kerak bo‘lganda Photoshop’ni o‘zi ochadi va dizaynni PSD/PNG qilib yuboradi.', 'Faqat Ali serveri shu Windows kompyuterda ishlaganda ishlaydi.']),
    'coreldraw': dict(name='CorelDRAW plagini', url='https://www.coreldraw.com/', link='CorelDRAW', plugin='coreldraw',
        steps=['CorelDRAW shu kompyuterga o‘rnatilgan bo‘lsa, kalit kerak emas - Ali uni o‘zi topadi.', 'Ali kerak bo‘lganda CorelDRAW’ni o‘zi ochadi va dizaynni CDR/PNG/PDF qilib yuboradi.', 'Faqat Ali serveri shu Windows kompyuterda ishlaganda ishlaydi.']),
}

def catalog(telegram_live=False):
    result=[]
    for key,p in PROVIDERS.items():
        configured=bool(getattr(config,p.get('field',''),''))
        status='Kalit sozlangan, aloqa tekshirilmagan' if configured else 'Sozlanmagan'
        if key=='telegram' and telegram_live:status='Ulangan'
        if key=='voice':status=f'Sozlangan: {config.tts_backend}'
        if key in {'google','meta','channels'}:status='Integratsiya hali o‘rnatilmagan'
        if 'plugin' in p:
            from . import plugins
            plug=plugins.PLUGINS.get(p['plugin'])
            status=plug.status if plug else 'Plagin o‘chirilgan (PLUGINS_DISABLED)'
            configured=bool(plug and plug.ready)
        result.append(dict(id=key,name=p['name'],status=status,url=p['url'],link=p['link'],steps=p['steps'],can_save='field' in p,configured=configured))
    return result

async def connect(key, token):
    p=PROVIDERS.get(key)
    if not p or 'field' not in p:raise ValueError('Bu xizmat uchun hozir faqat yo‘riqnoma mavjud.')
    if not isinstance(token,str) or not 12<=len(token)<=4096 or re.search(r'\s',token):
        raise ValueError('To‘liq token kiriting; bo‘sh joy bo‘lmasin.')
    headers={}
    if key=='telegram':
        if not re.fullmatch(r'\d+:[A-Za-z0-9_-]+',token):raise ValueError('Telegram token formati noto‘g‘ri.')
        url=f'https://api.telegram.org/bot{token}/getMe'
    elif key=='instagram':
        url=f'https://graph.facebook.com/{config.ig_graph_version}/me'
        headers={'Authorization':f'Bearer {token}'}
    elif key=='gemini':
        url='https://generativelanguage.googleapis.com/v1beta/models'
        headers={'x-goog-api-key':token}
    else:
        url={'github':'https://api.github.com/user','vercel':'https://api.vercel.com/v2/user','chatgpt':'https://api.openai.com/v1/models'}[key]
        headers={'Authorization':f'Bearer {token}'}
    try:
        async with httpx.AsyncClient(timeout=15,follow_redirects=False) as client:
            response=await client.get(url,headers=headers)
        if response.status_code!=200:raise ValueError('Xizmat tokenni tasdiqlamadi. Token muddati va ruxsatlarini tekshiring.')
        body=response.json()
        if not isinstance(body,dict) or (key=='telegram' and not body.get('ok')):
            raise ValueError('Xizmatdan ulanish tasdig‘i olinmadi.')
    except httpx.HTTPError:
        raise ValueError('Xizmatga ulanib bo‘lmadi. Internetni tekshirib qayta urinib ko‘ring.') from None
    async with _lock:
        try:await asyncio.to_thread(set_key,str(ENV_FILE),p['env'],token)
        except OSError:raise ValueError('Server sozlamani saqlay olmadi.') from None
        setattr(config,p['field'],token)
        os.environ[p['env']]=token
    if 'plugin' in p:
        from . import plugins
        await asyncio.to_thread(plugins.restart,p['plugin'])
    return {'ok':True,'message':'Token tekshirildi va saqlandi.'+(' Botni yangilash uchun Ali serverini qayta ishga tushiring.' if key=='telegram' else '')}
