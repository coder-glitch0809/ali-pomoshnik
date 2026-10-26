"""Owner-only connection setup. Credentials never appear in catalog responses."""
import asyncio
import json
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
    'instagram': dict(name='Instagram', url='https://developers.facebook.com/apps/', link='Meta Developers’da ilova ochish',
        steps=['Instagram akkauntingizni Professional (Business yoki Creator) qiling: Instagram → Sozlamalar → Akkaunt turi.', 'Meta Developers’da ilova yarating → “Instagram” mahsulotini qo‘shing → “API setup with Instagram login”.', 'Ruxsatlar: instagram_business_basic, content_publish, manage_comments, manage_insights, manage_messages — barchasini belgilang (to‘liq boshqaruv: joylash, analitika, izohlar, Direct).', '“Generate access token” → akkauntingiz bilan kiring → tokenni (IGAA… bilan boshlanadi) pastga kiriting. Ali akkauntni o‘zi topadi va eslab qoladi.'], field='ig_access_token', env='IG_ACCESS_TOKEN'),
    'github': dict(name='GitHub', url='https://github.com/settings/personal-access-tokens/new', link='GitHub orqali davom etish',
        steps=['GitHub hisobingizga kiring va Ali uchun fine-grained token yarating.', 'Faqat kerakli repozitoriylarni tanlang. O‘qish uchun Contents: Read-only; tahrirlash kerak bo‘lsa Read and write ruxsatini bering.', 'Tokenni nusxalab pastga kiriting. Ali ulanishni tekshirib saqlaydi.'], field='github_token', env='GITHUB_TOKEN'),
    'vercel': dict(name='Vercel', url='https://vercel.com/account/settings/tokens', link='Vercel orqali davom etish',
        steps=['Vercel hisobingizga o‘zingiz ishlatadigan usul bilan kiring.', 'Ali uchun token yarating, kerakli jamoa va amal qilish muddatini tanlang.', 'Tokenni pastga kiriting va tekshirib saqlang.'], field='vercel_token', env='VERCEL_TOKEN'),
    'render': dict(name='Render', url='https://dashboard.render.com/u/settings#api-keys', link='Render API kalitlari',
        steps=['Render hisobingizga kiring → Account Settings → API Keys.', '“Create API Key” bosing, nom bering (masalan: Ali) va kalitni nusxalang (rnd_… bilan boshlanadi).', 'Kalitni pastga kiriting. Ali xizmatlar holati, deploylar va loglarni erkin ko‘radi; qayta deploy va to‘xtatish faqat sizning tasdig‘ingiz bilan.'], field='render_api_key', env='RENDER_API_KEY'),
    'voice': dict(name='Ovoz', url='https://elevenlabs.io/app/settings/api-keys', link='ElevenLabs sozlamalari',
        steps=['Standart Edge ovozi alohida hisob talab qilmaydi.', 'Shaxsiy ovoz uchun ElevenLabs hisobiga kiring.', 'Serverda ELEVENLABS_API_KEY va ELEVENLABS_VOICE_ID ni sozlang.']),
    'google': dict(name='Google', url='https://console.cloud.google.com/auth/overview', link='Google orqali sozlash',
        steps=['Google hisobingiz bilan Cloud Console’ga kiring va loyiha tanlang.', 'Google Auth Platform’da OAuth ilovasi, ruxsatlar va Web client yarating.', 'Ali’da Google OAuth callback va Gmail/Drive vositalari hali o‘rnatilmagan. Hozir hisob ulash tugallanmaydi; bu sozlash yo‘riqnomasi.']),
    'meta': dict(name='Meta Ads', url='https://developers.facebook.com/apps/', link='Meta orqali sozlash',
        steps=['Meta hisobingizga kiring va Business ilovasini tanlang.', 'Marketing API va reklama hisobiga tegishli ruxsatlarni sozlang.', 'Ali’da Meta Ads boshqaruv vositasi hali o‘rnatilmagan. Hozir bu sozlash yo‘riqnomasi.']),
    'channels': dict(name='Telegram kanallari', url='https://telegram.org/faq_channels', link='Kanalni ulash yo‘riqnomasi',
        steps=['Telegram’da o‘z kanalingiz sozlamalarini oching.', 'Ali botini administrator qilib qo‘shing, faqat post joylash ruxsatini bering.', 'Kanalga avtomatik post vositasi hali o‘rnatilmagan. Botni qo‘shishning o‘zi avtomatik postni yoqmaydi.']),
    'firebase': dict(name='Firebase (xotira nusxasi)', url='https://console.firebase.google.com/', link='Firebase Console', json=True,
        steps=['Firebase Console’da loyihangizni oching → Build → Firestore Database → yoqilganini tekshiring (yo‘q bo‘lsa “Create database”).', 'Project settings (⚙) → Service accounts → “Generate new private key” → JSON fayl yuklanadi.', 'Faylni Bloknot bilan oching, butun matnni nusxalab pastga joylang. Ali tekshiradi va har daqiqada xotirani Firebase’ga yozadi.', 'Kalit faqat shu kompyuterda (data/ papkasida) saqlanadi va GitHub’ga chiqmaydi.']),
    'bedrock': dict(name='Amazon Bedrock (Claude)', url='https://console.aws.amazon.com/bedrock/home#/api-keys', link='AWS Bedrock → API keys',
        steps=['AWS Console’da Amazon Bedrock → API keys bo‘limini oching va “Generate long-term API key” bilan kalit yarating.', 'Bedrock → Model access bo‘limida Anthropic Claude modellariga ruxsat yoqilganini tekshiring.', 'Kalitni pastga kiriting. Mintaqa us-east-1 emas bo‘lsa, oldiga yozing: “eu-central-1 ABSK…”. Ali modelni o‘zi topadi va tekshiradi.', 'Bedrock pullik (AWS hisobingizdan). Ali uni Pro ilovalardan keyin, bepul Gemini’dan oldin ishlatadi.'], field='bedrock_api_key', env='BEDROCK_API_KEY'),
    'tg_account': dict(name='Telegram akkaunt (kanallar)', url='https://my.telegram.org/apps', link='my.telegram.org → API development tools',
        steps=['my.telegram.org saytiga telefon raqamingiz bilan kiring → “API development tools” → ilova yarating (nomi: Ali).', 'Chiqqan api_id (raqam) va api_hash ni pastga bo‘sh joy bilan kiriting: “12345678 abcdef0123…”.', 'Kompyuterda oyna ochiladi: telefon raqamingiz, Telegram yuborgan kod va (bo‘lsa) 2 bosqichli parolni O‘ZINGIZ kiritasiz.', 'Ali faqat O‘QIYDI: kanal va guruhlardagi post va fayllardan o‘rganadi, hech narsa yubormaydi.'], field='tg_api_hash', env='TG_API_HASH'),
    'chatplace': dict(name='ChatPlace (Instagram/Telegram avtomatlashtirish)', url='https://chatplace.io', link='ChatPlace sayti', action='/api/mcp/chatplace/start', action_label='ChatPlace’ga kirish va ruxsat berish',
        steps=['Pastdagi tugmani bosing - ChatPlace sahifasi ochiladi, akkauntingizga kiring.', 'Ali so‘ragan ruxsatlarni tasdiqlang (avtomatlashtirish, chatlar, tarqatmalar, izohlar, AI agent).', '“Ali’ga ulandi” chiqqach, bu oynani yoping. Ali ma’lumotni erkin o‘qiydi, o‘zgartirishlarni (xabar, tarqatma, avtojavob) faqat sizning tasdig‘ingiz bilan qiladi.']),
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
        if key=='instagram' and config.ig_accounts:status='Ulangan: '+', '.join('@'+a for a in config.ig_accounts)
        if key=='voice':status=f'Sozlangan: {config.tts_backend}'
        if key in {'google','meta','channels'}:status='Integratsiya hali o‘rnatilmagan'
        if key in ('github','vercel'):
            from . import local_ai
            if local_ai.app_state().get(key,{}).get('connected'):
                status,configured='Ulangan (ilova orqali) · Ruxsatlar → Ilovalar',True
        if key=='bedrock' and config.bedrock_api_key:status=f'Ulangan · {config.bedrock_model or "model avtomatik"} ({config.bedrock_region})'
        if key=='tg_account':
            from . import tg_account
            status='Ulangan (faqat o‘qish)' if tg_account.configured() else ('Kalit bor · kirish kerak (qayta “Sozlash”)' if tg_account.credentials() else 'Sozlanmagan')
            configured=tg_account.configured()
        if key=='chatplace':
            from . import mcp_client
            configured=mcp_client.connected('chatplace')
            status='Ulangan (MCP)' if configured else 'Sozlanmagan'
        if key=='firebase':
            from . import cloud
            configured=cloud.configured()
            st=cloud.status
            status=('Xato: '+st['error'][:120]) if st['error'] else (('Ulangan · oxirgi nusxa '+__import__('time').strftime('%H:%M',__import__('time').localtime(st['last_sync']))) if st['last_sync'] else ('Ulangan · birinchi nusxa tayyorlanmoqda' if configured else 'Sozlanmagan'))
        if 'plugin' in p:
            from . import plugins
            plug=plugins.PLUGINS.get(p['plugin'])
            status=plug.status if plug else 'Plagin o‘chirilgan (PLUGINS_DISABLED)'
            configured=bool(plug and plug.ready)
        result.append(dict(id=key,name=p['name'],status=status,url=p['url'],link=p['link'],steps=p['steps'],action=p.get('action',''),action_label=p.get('action_label',''),can_save='field' in p or p.get('json',False),json=p.get('json',False),configured=configured))
    return result

async def connect(key, token):
    if key=='firebase':return await connect_firebase(token)
    if key=='tg_account':return await connect_tg_account(token)
    if key=='bedrock':return await connect_bedrock(token)
    p=PROVIDERS.get(key)
    if not p or 'field' not in p:raise ValueError('Bu xizmat uchun hozir faqat yo‘riqnoma mavjud.')
    if not isinstance(token,str) or not 12<=len(token)<=4096 or re.search(r'\s',token):
        raise ValueError('To‘liq token kiriting; bo‘sh joy bo‘lmasin.')
    headers={}
    if key=='instagram':return await connect_instagram(token)
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
        url={'github':'https://api.github.com/user','vercel':'https://api.vercel.com/v2/user','render':'https://api.render.com/v1/users','chatgpt':'https://api.openai.com/v1/models'}[key]
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


async def connect_instagram(token):
    """Instagram: token turini aniqlaydi, akkaunt(lar)ni topadi va token bilan birga saqlaydi."""
    from .skills.instagram import discover
    try:accounts=await asyncio.to_thread(discover,token)
    except (RuntimeError,httpx.HTTPError,KeyError,ValueError):
        raise ValueError('Instagram tokenni tasdiqlamadi. Token to‘liq nusxalanganini va ruxsatlarni tekshiring.') from None
    if not accounts:
        raise ValueError('Token ishladi, lekin Instagram Professional akkaunt topilmadi (Facebook sahifaga ulanganini tekshiring).')
    value=','.join(f'{name}={uid}' for name,uid in accounts.items())
    async with _lock:
        try:
            await asyncio.to_thread(set_key,str(ENV_FILE),'IG_ACCESS_TOKEN',token)
            await asyncio.to_thread(set_key,str(ENV_FILE),'IG_ACCOUNTS',value)
        except OSError:raise ValueError('Server sozlamani saqlay olmadi.') from None
        config.ig_access_token=token;config.ig_accounts=dict(accounts)
        os.environ['IG_ACCESS_TOKEN']=token;os.environ['IG_ACCOUNTS']=value
    return {'ok':True,'message':'Instagram ulandi: '+', '.join('@'+n for n in accounts)+'. Ali joylash, analitika, izohlar va Direct’ni boshqara oladi (har bir amal tasdiq bilan).'}


async def connect_firebase(text):
    """Firebase service account kalitini tekshiradi, data/ ga saqlaydi va sinxronlashni boshlaydi."""
    from . import cloud
    if not isinstance(text,str) or len(text)>20000:raise ValueError('Kalit matnini to‘liq joylang.')
    data=await asyncio.to_thread(cloud.validate,text.strip())
    async with _lock:
        cloud.KEY_FILE.write_text(json.dumps(data),encoding='utf-8')
        cloud.reset()
    cloud.start()
    try:result=await asyncio.to_thread(cloud.sync_once)
    except Exception as e:return {'ok':True,'message':f'Kalit saqlandi ({data["project_id"]}), lekin birinchi nusxa xato berdi: {str(e)[:200]}'}
    return {'ok':True,'message':f'Firebase ulandi ({data["project_id"]}). Birinchi nusxa: {result["pushed"]} ta yozuv yuborildi. Endi har daqiqada avtomatik.'}


async def connect_bedrock(text):
    """Bedrock API kaliti: modelni topadi, qisqa so'rov bilan tekshiradi, kalit va modelni saqlaydi."""
    from . import providers
    parts=(text or '').strip().split()
    if not parts or len(parts)>2:raise ValueError('Kalitni kiriting (kerak bo‘lsa oldiga mintaqa: “eu-central-1 ABSK…”).')
    region,key=(parts[0],parts[1]) if len(parts)==2 else (config.bedrock_region,parts[0])
    if not re.fullmatch(r'[a-z]{2}(-[a-z]+)+-\d',region):raise ValueError('Mintaqa noto‘g‘ri (masalan us-east-1).')
    models=await asyncio.to_thread(providers.bedrock_models,key,region)
    model=config.bedrock_model or (models[0] if models else '')
    if not model:raise ValueError('Kalit ishladi, lekin Claude modeli topilmadi. Bedrock → Model access’da Anthropic’ni yoqing.')
    try:answer=await asyncio.to_thread(providers.bedrock_chat,'Qisqa javob ber.',[],'Faqat OK deb yoz',20,model,key,region)
    except RuntimeError as e:raise ValueError(f'Bedrock tekshiruvdan o‘tmadi: {str(e)[:250]}') from None
    if not answer:raise ValueError('Bedrock javob qaytarmadi.')
    async with _lock:
        for env,value,attr in (('BEDROCK_API_KEY',key,'bedrock_api_key'),('BEDROCK_REGION',region,'bedrock_region'),('BEDROCK_MODEL',model,'bedrock_model')):
            await asyncio.to_thread(set_key,str(ENV_FILE),env,value)
            setattr(config,attr,value);os.environ[env]=value
    return {'ok':True,'message':f'Bedrock ulandi: {model} ({region}). Ali endi Pro ilovalardan keyin Bedrock’dan foydalanadi.'}


async def connect_tg_account(text):
    """Telegram API (api_id + api_hash) ni saqlaydi va kompyuterda kirish oynasini ochadi."""
    from . import tg_account
    parts=(text or '').split()
    if len(parts)==1 and tg_account.credentials():parts=[]  # faqat qayta kirish
    if parts:
        if len(parts)!=2 or not parts[0].isdigit() or not re.fullmatch(r'[0-9a-f]{32}',parts[1]):
            raise ValueError('api_id (raqam) va api_hash (32 belgi) ni bo‘sh joy bilan kiriting: “12345678 abcdef…”.')
        async with _lock:
            for env,value in (('TG_API_ID',parts[0]),('TG_API_HASH',parts[1])):
                await asyncio.to_thread(set_key,str(ENV_FILE),env,value);os.environ[env]=value
    try:await asyncio.to_thread(tg_account.open_login)
    except RuntimeError as e:raise ValueError(str(e)) from None
    return {'ok':True,'message':'Kompyuterda oyna ochildi: telefon raqamingiz va Telegram yuborgan kodni o‘zingiz kiriting. Kirgach, Telegram’da Ali’ga “/kanallar” deb yozing.'}
