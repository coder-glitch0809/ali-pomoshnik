"""Public Telegram state. Kept separate from the owner's facts and conversations."""
import json
import time
from datetime import datetime, timezone, timedelta
from .memory import memory

TZ = timezone(timedelta(hours=5))


class PublicStore:
    def __init__(self):
        memory._exec('CREATE TABLE IF NOT EXISTS tg_public (uid INTEGER PRIMARY KEY, data TEXT NOT NULL)')
        memory._exec('CREATE TABLE IF NOT EXISTS tg_requests (id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER NOT NULL, kind TEXT NOT NULL, text TEXT NOT NULL, status TEXT NOT NULL DEFAULT "pending", created REAL NOT NULL)')
        memory._exec('CREATE TABLE IF NOT EXISTS tg_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)')

    def get(self, uid):
        row=memory._exec('SELECT data FROM tg_public WHERE uid=?',(uid,)).fetchone()
        return json.loads(row['data']) if row else {'history':[], 'grants':{}, 'subscribed':True, 'weather':False}

    def put(self, uid, data):
        memory._exec('INSERT INTO tg_public(uid,data) VALUES(?,?) ON CONFLICT(uid) DO UPDATE SET data=excluded.data',
                     (uid,json.dumps(data,ensure_ascii=False)))

    def subscribers(self):
        return [(r['uid'],json.loads(r['data'])) for r in memory._exec('SELECT uid,data FROM tg_public').fetchall()]

    def quota(self, uid, limit=10):
        data=self.get(uid); day=datetime.now(TZ).date().isoformat()
        count=data.get('count',0) if data.get('day')==day else 0
        if count>=limit:return False
        data.update(day=day,count=count+1);self.put(uid,data);return True

    def request(self, uid, kind, text):
        old=memory._exec('SELECT id FROM tg_requests WHERE uid=? AND kind=? AND status="pending"',(uid,kind)).fetchone()
        if old:return old['id'],False
        row=memory._exec('INSERT INTO tg_requests(uid,kind,text,created) VALUES(?,?,?,?)',(uid,kind,text[:1500],time.time()))
        return row.lastrowid,True

    def resolve(self, rid, allow):
        row=memory._exec('SELECT * FROM tg_requests WHERE id=?',(rid,)).fetchone()
        if not row or row['status']!='pending':return None
        memory._exec('UPDATE tg_requests SET status=? WHERE id=?',('approved' if allow else 'denied',rid))
        if allow and row['kind'] in {'content','trading_week','trading_month'}:
            grant='content' if row['kind']=='content' else 'trading'
            duration={'content':86400,'trading_week':7*86400,'trading_month':30*86400}[row['kind']]
            data=self.get(row['uid']); data.setdefault('grants',{})[grant]=max(time.time(),data.get('grants',{}).get(grant,0))+duration;self.put(row['uid'],data)
        return dict(row)

    def pending(self):
        return [dict(r) for r in memory._exec('SELECT * FROM tg_requests WHERE status="pending" ORDER BY id DESC LIMIT 30').fetchall()]

    def meta(self,key,default=None):
        row=memory._exec('SELECT value FROM tg_meta WHERE key=?',(key,)).fetchone()
        return json.loads(row['value']) if row else default

    def set_meta(self,key,value):
        memory._exec('INSERT INTO tg_meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,json.dumps(value)))
