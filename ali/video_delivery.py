"""Durable owner delivery: a rendered file is not a Telegram receipt."""
import hashlib
import json
import logging
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

import httpx

from .config import config

DB = config.data_dir / 'video_delivery.sqlite3'
log = logging.getLogger('ali.video_delivery')


@contextmanager
def _db():
    DB.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute('CREATE TABLE IF NOT EXISTS deliveries '
                       '(id TEXT PRIMARY KEY, payload TEXT NOT NULL, receipts TEXT NOT NULL DEFAULT \'[]\', '
                       'sent INTEGER NOT NULL DEFAULT 0, retry REAL NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT \'\')')
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def _post(method, **kwargs):
    response = httpx.post(f'https://api.telegram.org/bot{config.telegram_token}/{method}', timeout=300, **kwargs)
    # Never expose token-bearing request URLs from HTTP exceptions in logs.
    if response.status_code != 200:
        raise RuntimeError(f'Telegram HTTP {response.status_code}')
    result = response.json()
    if not result.get('ok') or not result.get('result', {}).get('message_id'):
        raise RuntimeError(f'Telegram receipt missing (code {result.get("error_code", "unknown")})')
    return result['result']['message_id']


def enqueue(text, files):
    payload = {'chat_id': config.telegram_owner_id, 'text': text[:4000],
               'files': [str(Path(p).resolve()) for p in files]}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    key = hashlib.sha256(encoded.encode()).hexdigest()
    with _db() as db:
        db.execute('INSERT OR IGNORE INTO deliveries(id,payload) VALUES (?,?)', (key, encoded))
    return key


def send_files(text, files, queue=True):
    return _send(enqueue(text, files))


def _send(key):
    with _db() as db:
        row = db.execute('SELECT * FROM deliveries WHERE id=?', (key,)).fetchone()
        if not row:
            return False
        if row['sent']:
            return True
        # Claim across threads/processes; a crashed sender becomes retryable.
        claimed = db.execute('UPDATE deliveries SET retry=? WHERE id=? AND sent=0 AND retry<=?',
                             (time.time() + 600, key, time.time())).rowcount
    if not claimed:
        return False
    payload, receipts = json.loads(row['payload']), json.loads(row['receipts'])
    try:
        if not config.telegram_token or not payload['chat_id']:
            raise RuntimeError('Telegram bot or owner is not configured')
        files = payload['files']
        # Validate the complete payload before sending a misleading success text.
        for filename in files:
            path = Path(filename)
            if not path.is_file():
                raise RuntimeError(f'Delivery file missing: {path.name}')
            if path.stat().st_size > 45 * 1024 * 1024:
                raise RuntimeError(f'Delivery file exceeds bot limit: {path.name}')
        steps = [None, *files]
        for index, filename in enumerate(steps):
            if index < len(receipts):
                continue
            if filename is None:
                receipt = _post('sendMessage', data={'chat_id': payload['chat_id'], 'text': payload['text']})
            else:
                path = Path(filename)
                video = path.suffix.lower() == '.mp4'
                method, field = ('sendVideo', 'video') if video else ('sendDocument', 'document')
                data = {'chat_id': payload['chat_id']}
                if video:
                    from .skills.video_edit import info
                    meta = info(path)
                    data.update(width=meta['width'], height=meta['height'],
                                duration=int(round(meta['duration'])), supports_streaming='true')
                with path.open('rb') as stream:
                    receipt = _post(method, data=data, files={field: (path.name, stream)})
            receipts.append(receipt)
            with _db() as db:
                db.execute('UPDATE deliveries SET receipts=?,retry=? WHERE id=?',
                           (json.dumps(receipts), time.time() + 600, key))
        with _db() as db:
            db.execute('UPDATE deliveries SET sent=1,error=\'\' WHERE id=?', (key,))
        log.info('Owner delivery confirmed: %s (%s files)', key[:12], len(files))
        return True
    except Exception as error:
        detail = str(error) if isinstance(error, RuntimeError) else type(error).__name__
        with _db() as db:
            db.execute('UPDATE deliveries SET retry=?,error=? WHERE id=?', (time.time() + 900, detail[:300], key))
        log.warning('Owner delivery pending: %s: %s', key[:12], detail)
        return False


def flush_pending():
    with _db() as db:
        keys = [row['id'] for row in db.execute(
            'SELECT id FROM deliveries WHERE sent=0 AND retry<=? ORDER BY rowid LIMIT 3', (time.time(),))]
    for key in keys:
        _send(key)
