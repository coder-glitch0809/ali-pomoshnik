"""Persistent Telegram controls for the existing creative studio."""
import asyncio
import json
from telegram import InlineKeyboardButton as Button, InlineKeyboardMarkup as Keyboard
from .config import config


class StudioPanel:
    def _state(self):
        try:
            return json.loads((config.data_dir / 'multik_panel.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {}

    def _remember(self, user, **values):
        state = self._state()
        state.setdefault(str(user), {}).update(values)
        target = config.data_dir / 'multik_panel.json'
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix('.tmp')
        temp.write_text(json.dumps(state, ensure_ascii=False), encoding='utf-8')
        temp.replace(target)

    async def panel(self, update, context):
        if not await self._authorized(update):
            return
        prefs = self._state().get(str(update.effective_user.id), {})
        rows = [[Button('📐 Tik 9:16', callback_data='studio:format:9:16'),
                 Button('📐 Keng 16:9', callback_data='studio:format:16:9'),
                 Button('Kvadrat', callback_data='studio:format:1:1')],
                [Button('🎙 AI Studio WAV', callback_data='studio:voice:aistudio')],
                [Button('Sardor · avtomatik', callback_data='studio:voice:sardor'),
                 Button('Madina · avtomatik', callback_data='studio:voice:madina')],
                [Button('📂 Loyiham / holati', callback_data='studio:current')]]
        await update.effective_message.reply_text(
            '🎬 ALI VIDEO STUDIYA\n\nG‘oyangizni yozing → uslubni tanlang → sahnalarni ko‘ring → video oling.\n'
            f"\nFormat: {prefs.get('format', '9:16')}\nOvoz: {prefs.get('voice', 'aistudio')}\n\n"
            'AI Studio: har sahna uchun WAV yuboriladi. Sardor/Madina: ovoz va video avtomatik tayyorlanadi. '
            'Sozlamalar keyingi video uchun saqlanadi. /panel — boshqaruv.', reply_markup=Keyboard(rows))

    def _controls(self, job_id, job):
        rows = [[Button('🔄 Holati', callback_data=f'studio:status:{job_id}'),
                 Button('🖼 Sahnalar', callback_data=f'studio:scene:{job_id}:1')]]
        if job.get('status') == 'ready':
            rows.append([Button('▶️ Videoni yasash', callback_data=f'studio:render:{job_id}')])
        if job.get('status') == 'done':
            rows.append([Button('📥 Videoni olish', callback_data=f'studio:download:{job_id}')])
        return Keyboard(rows)

    async def studio_action(self, update, context):
        from . import creative_video as studio
        q = update.callback_query
        if not await self._authorized(update):
            await q.answer()
            return
        await q.answer()
        uid = update.effective_user.id
        parts = q.data.split(':')
        action = parts[1]
        prefs = self._state().get(str(uid), {})
        if action in ('format', 'voice'):
            value = ':'.join(parts[2:])
            allowed = ('9:16', '16:9', '1:1') if action == 'format' else ('aistudio', 'sardor', 'madina')
            if value in allowed:
                self._remember(uid, **{action: value})
                await q.message.reply_text(f'✅ Saqlandi: {value}')
            return
        job_id = prefs.get('job') if action == 'current' else parts[2]
        if not job_id and action == 'current' and uid == config.telegram_owner_id:
            projects = sorted((config.data_dir / 'creative_videos').glob('*/job.json'),
                              key=lambda p: p.stat().st_mtime, reverse=True)
            for project in projects:
                candidate = studio.get(project.parent.name)
                if candidate and not candidate.get('bot_user'):
                    job_id = project.parent.name
                    studio._update(job_id, bot_user=uid, bot_chat=q.message.chat_id,
                                   bot_voice=prefs.get('voice', 'aistudio'))
                    self._remember(uid, job=job_id)
                    break
        job = studio.get(job_id) if job_id else None
        if not job or job.get('bot_user') != uid or job.get('bot_chat') != q.message.chat_id:
            await q.message.reply_text('Bu chatda loyihangiz topilmadi. Yangi g‘oya yuboring.')
            return
        try:
            if action == 'scene':
                scenes = (job.get('story') or {}).get('scenes', [])
                index = int(parts[3])
                if not 1 <= index <= len(scenes):
                    raise ValueError('Sahna hali tayyor emas')
                scene = scenes[index-1]
                text = f"🎞 {index}/{len(scenes)} · {scene.get('speaker', 'Hikoyachi')}\n{scene.get('voice', '')}"
                rows = [[Button('🎙 Shu sahnaga WAV yuborish', callback_data=f'studio:audio:{job_id}:{index}')]]
                if job.get('status') == 'ready':
                    rows.append([Button('🎨 Qayta chizish', callback_data=f'studio:redraw:{job_id}:{index}')])
                nav = []
                for n, label in ((index-1, '⬅️'), (index+1, '➡️')):
                    if 1 <= n <= len(scenes):
                        nav.append(Button(label, callback_data=f'studio:scene:{job_id}:{n}'))
                rows.append(nav or [Button('Holati', callback_data=f'studio:status:{job_id}')])
                path = studio.scene_path(job_id, index)
                if path:
                    with path.open('rb') as stream:
                        await q.message.reply_photo(stream, caption=text[:1000], reply_markup=Keyboard(rows))
                else:
                    await q.message.reply_text(text, reply_markup=Keyboard(rows))
            elif action == 'redraw':
                index = int(parts[3])
                await q.message.reply_text(f'🎨 {index}-sahna qayta chizilmoqda…')
                async def redraw():
                    try:
                        await asyncio.to_thread(studio.redraw_scene, job_id, index)
                        await q.message.reply_text('✅ Rasm yangilandi. Sahnalar tugmasidan ko‘ring.',
                            reply_markup=self._controls(job_id, studio.get(job_id)))
                    except Exception:
                        await q.message.reply_text('Qayta chizilmadi. Oldingi rasm saqlandi; qayta urinib ko‘ring.')
                context.application.create_task(redraw())
            elif action == 'audio':
                if job['status'] != 'ready':
                    raise ValueError('Avval barcha sahnalar tayyor bo‘lsin')
                index = int(parts[3])
                scene = job['story']['scenes'][index-1]
                self._remember(uid, upload=[job_id, index, q.message.chat_id])
                await q.message.reply_text(
                    f"🎙 {index}-sahna uchun AI Studio’da ovoz yarating va WAV faylini shu chatga yuboring (20 MB gacha).\n\n"
                    'Tabiiy o‘zbekcha, aniq talaffuz va rolga mos hissiyot bilan o‘qing.\n\n'
                    f"{scene.get('voice', '')}\n\nhttps://aistudio.google.com/generate-speech")
            elif action == 'render':
                studio.start_render(job_id, job.get('voices') or {
                    str(s.get('speaker') or 'Hikoyachi'): job.get('bot_voice', 'aistudio') for s in job['story']['scenes']})
                context.application.create_task(self._deliver(job_id, q.message.chat_id, context))
                await q.message.reply_text('🎬 Video yig‘ilishi boshlandi.')
            elif action == 'download':
                from . import outbox
                path = outbox.resolve(job.get('video', ''))
                if not path:
                    raise ValueError('Video fayli topilmadi')
                with path.open('rb') as stream:
                    await q.message.reply_document(stream, caption='📥 Tayyor MP4', write_timeout=120)
            else:
                await q.message.reply_text(self._progress_text(job), reply_markup=self._controls(job_id, job))
        except (ValueError, RuntimeError, IndexError) as error:
            await q.message.reply_text(str(error)[:900])

    async def receive_audio(self, update, context):
        from . import studio_audio, creative_video as studio
        if not await self._authorized(update):
            return
        uid = update.effective_user.id
        target = self._state().get(str(uid), {}).get('upload')
        message = update.effective_message
        if not target or target[2] != message.chat_id:
            await message.reply_text('Avval /panel → Loyiham → Sahnalar → Shu sahnaga WAV yuborish tugmasini bosing.')
            return
        job_id, index, _ = target
        job = studio.get(job_id)
        if not job or job.get('bot_user') != uid:
            return
        media = message.document or message.audio
        try:
            if not media or not media.file_size or media.file_size > studio_audio.MAX_BYTES:
                raise ValueError('20 MB gacha bo‘lgan WAV faylini yuboring')
            file = await media.get_file()
            data = await file.download_as_bytearray()
            job = studio_audio.save(job_id, index, bytes(data))
            self._remember(uid, upload=None)
            await message.reply_text(f'✅ {index}-sahna ovozi saqlandi.', reply_markup=self._controls(job_id, job))
        except ValueError as error:
            await message.reply_text(str(error))

    @staticmethod
    def _progress_text(job):
        scenes = (job.get('story') or {}).get('scenes', [])
        return (f"🎬 {(job.get('story') or {}).get('title', 'Ali video')}\n\n"
                f"⏳ {job.get('progress', 0)}% · {job.get('message', '')}\n"
                f"🖼 Rasmlar: {len(job.get('scene_images', []))}/{len(scenes)}\n"
                f"🎙 Yuklangan ovozlar: {len(job.get('scene_audio', {}))}/{len(scenes)}")
