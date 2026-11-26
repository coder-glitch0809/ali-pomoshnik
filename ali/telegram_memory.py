"""Durable, searchable memory of trusted Telegram requests and successful deliveries."""
import contextvars
import hashlib
import logging
import re
from telegram import Update
from telegram.ext import ExtBot, TypeHandler
from .config import config
from .memory import memory

_request_chat = contextvars.ContextVar('telegram_memory_chat', default=None)
log = logging.getLogger(__name__)


def redact(text):
    text = str(text or '')
    if re.match(r'^/login(?:@\w+)?\b', text, re.I):
        return '/login [parol yashirildi]'
    for name, value in vars(config).items():
        if any(part in name for part in ('key', 'token', 'password', 'secret')) and isinstance(value, str) and len(value) >= 6:
            text = text.replace(value, '[maxfiy]')
    text = re.sub(r'\b\d{6,}:[A-Za-z0-9_-]{20,}\b|\b(?:sk-|sk_)[A-Za-z0-9_-]{16,}', '[maxfiy]', text)
    text = re.sub(r'(https?://[^\s?]+\?)[^\s]+', r'\1[maxfiy parametrlar]', text)
    return text[:12000]


def record(source, chat, key, direction, text):
    content = f'Telegram · {source} · chat {chat}\n{redact(text)}'
    try:
        memory.log_event(f'telegram:{source}:{chat}:{key}', f'telegram:{source}:{chat}',
                         f'telegram:{direction}', content)
    except Exception:
        log.exception('Telegram hodisasini xotiraga saqlab bo‘lmadi')


def observe(source, trusted):
    async def incoming(update, context):
        _request_chat.set(None)
        user, chat = update.effective_user, update.effective_chat
        if not user or not chat or user.id not in trusted():
            return
        _request_chat.set(chat.id)
        message, query = update.effective_message, update.callback_query
        if query:
            text = 'Tugma bosildi: ' + str(query.data or '')
        elif message:
            text = message.text or message.caption or ''
            for kind in ('document', 'video', 'audio', 'voice', 'photo', 'location'):
                media = getattr(message, kind, None)
                if media:
                    text += f'\nBiriktirma: {kind}'
                    name = getattr(media, 'file_name', None)
                    if name:
                        text += f' · {name}'
        else:
            return
        if text.strip():
            record(source, chat.id, f'update:{update.update_id}', 'request', text)
    return TypeHandler(Update, incoming)


class MemoryBot(ExtBot):
    __slots__ = ('_memory_source',)

    def __init__(self, token, *, source):
        super().__init__(token)
        self._memory_source = source

    async def _do_post(self, endpoint, data, **kwargs):
        result = await super()._do_post(endpoint, data, **kwargs)
        # Record only confirmed deliveries, never tokens, binary payloads or unrelated public chats.
        chat = data.get('chat_id')
        trusted = {config.telegram_owner_id, _request_chat.get()} - {None, 0}
        if chat not in trusted or not (endpoint.startswith('send') or endpoint in ('editMessageText', 'editMessageCaption')):
            return result
        messages = result if isinstance(result, list) else [result]
        for item in messages:
            if not isinstance(item, dict) or not item.get('message_id'):
                continue
            text = item.get('text') or item.get('caption') or data.get('text') or data.get('caption') or ''
            for kind in ('document', 'video', 'audio', 'voice', 'photo'):
                if kind in item:
                    media = item[kind]
                    text += f'\nYuborilgan fayl: {kind}'
                    if isinstance(media, dict) and media.get('file_name'):
                        text += ' · ' + str(media['file_name'])
            text = redact(text)
            if text:
                digest = hashlib.sha256(text.encode()).hexdigest()[:16]
                record(self._memory_source, chat, f'{endpoint}:{item["message_id"]}:{digest}', 'result', text)
        return result
