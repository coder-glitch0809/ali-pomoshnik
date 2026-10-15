import asyncio
import importlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

state = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / "data")
os.environ.update(ALI_STATE_DIR=state.name, ANTHROPIC_API_KEY="", TELEGRAM_BOT_TOKEN="",
                  ACCESS_PASSWORD="test-password", AUTO_LEARN="false", WATCH_PROJECTS="false")

from fastapi.testclient import TestClient
from ali import agents, auth
from ali.brain import Brain
from ali.config import config
from ali.service import brain
from ali.telegram_bot import TelegramBot
from runtime import app
from gateway import app as gateway


def tearDownModule():
    import logging
    from ali.memory import memory
    memory.conn.close()
    logging.shutdown()
    state.cleanup()


class RuntimeTests(unittest.TestCase):
    def test_telegram_setup_rate_limit_does_not_block_and_is_cached(self):
        from types import SimpleNamespace
        from telegram.error import RetryAfter
        bot=TelegramBot();bot.public.set_meta('bot_setup',{})
        method=AsyncMock(side_effect=RetryAfter(3600))
        bot.app=SimpleNamespace(bot=SimpleNamespace(set_my_name=method))
        asyncio.run(bot.configure_bot('set_my_name',name='Ali'))
        asyncio.run(bot.configure_bot('set_my_name',name='Ali'))
        self.assertEqual(method.await_count,1)
        bot.public.set_meta('bot_setup',{})
        method.side_effect=None
        asyncio.run(bot.configure_bot('set_my_name',name='Ali'))
        asyncio.run(bot.configure_bot('set_my_name',name='Ali'))
        self.assertEqual(method.await_count,2)
        bot.public.set_meta('bot_setup',{})

    def test_miniapp_signed_owner_authentication(self):
        import hashlib,hmac,json,time
        from urllib.parse import urlencode
        def signed(uid=999,age=0):
            fields={'auth_date':str(int(time.time())-age),'user':json.dumps({'id':uid,'first_name':'Untrusted'}),'query_id':'test-query'}
            secret=hmac.new(b'WebAppData',b'test-token',hashlib.sha256).digest()
            fields['hash']=hmac.new(secret,'\n'.join(f'{k}={v}' for k,v in sorted(fields.items())).encode(),hashlib.sha256).hexdigest()
            return urlencode(fields)
        with patch.object(config,'telegram_token','test-token'),patch.object(config,'telegram_owner_id',999):
            self.assertEqual(self.client.get('/miniapp').status_code,200)
            for invalid in [signed(888),signed(age=600),signed(age=-90),signed()+'&user=%7B%7D',signed().replace('query_id=test-query','query_id=forged'),None,{'id':999}]:
                self.assertEqual(self.client.post('/api/telegram/login',json={'init_data':invalid}).status_code,403)
                self.assertEqual(self.client.get('/api/status').status_code,401)
            result=self.client.post('/api/telegram/login',json={'init_data':signed()})
            self.assertEqual(result.status_code,200);self.assertEqual(result.json()['name'],'Abbos')
            cookie=self.client.cookies.get('ali_token');self.assertTrue(auth.check_token(cookie))
            self.assertIn('HttpOnly',result.headers['set-cookie'])
            self.assertEqual(self.client.get('/api/status').status_code,200)
            with patch('ali.auth.time.time',return_value=time.time()+9*3600):self.assertFalse(auth.check_token(cookie))
            with patch.object(config,'telegram_owner_id',888):self.assertFalse(auth.check_token(cookie))

    def test_owner_menu_and_abbos_greeting(self):
        from types import SimpleNamespace
        bot=TelegramBot();bot.owner_id=999;bot.users={999}
        owner=[b.text for row in bot.keyboard(999).keyboard for b in row]
        guest=[b.text for row in bot.keyboard(111).keyboard for b in row]
        self.assertIn('⚙️ Sozlamalar',owner);self.assertIn('🖥 Mini App',owner)
        self.assertNotIn('⚙️ Sozlamalar',guest);self.assertNotIn('🖥 Mini App',guest)
        msg=SimpleNamespace(reply_text=AsyncMock())
        update=SimpleNamespace(effective_chat=SimpleNamespace(type='private'),effective_user=SimpleNamespace(id=999,first_name='OtherName'),effective_message=msg)
        ctx=SimpleNamespace(bot=SimpleNamespace(set_chat_menu_button=AsyncMock()))
        asyncio.run(bot.public_start(update,ctx))
        self.assertIn('Abbos',msg.reply_text.call_args.args[0]);self.assertNotIn('OtherName',msg.reply_text.call_args.args[0])
        update.effective_user.id=111
        for text in ['⚙️ Sozlamalar','🖥 Mini App']:
            self.assertTrue(asyncio.run(bot.menu_text(update,ctx,text)))
            self.assertIn('faqat administrator',msg.reply_text.call_args.args[0])

    def test_connections_auth_validation_and_persistence(self):
        from ali import connections
        from types import SimpleNamespace
        self.assertEqual(self.client.post('/api/connections/github',json={'token':'not-a-real-token'}).status_code,401)
        self.login()
        self.assertEqual(self.client.post('/api/connections/github',headers={'Origin':'https://evil.example'},json={'token':'not-a-real-token'}).status_code,403)
        self.assertEqual(self.client.post('/api/connections/google',json={'token':'not-a-real-token'}).status_code,400)
        self.assertEqual(self.client.post('/api/connections/github',json={'token':123}).status_code,400)
        response=SimpleNamespace(status_code=401,json=lambda:{})
        with patch('ali.connections.httpx.AsyncClient.get',new=AsyncMock(return_value=response)),patch('ali.connections.set_key') as save:
            self.assertEqual(self.client.post('/api/connections/github',json={'token':'not-a-real-token'}).status_code,400)
            save.assert_not_called()
        response.status_code=200;response.json=lambda:{'login':'test'}
        with patch('ali.connections.httpx.AsyncClient.get',new=AsyncMock(return_value=response)),patch.object(connections,'ENV_FILE',Path(state.name)/'connection.env'),patch.object(config,'github_token',''),patch.dict(os.environ):
            self.assertEqual(self.client.post('/api/connections/github',json={'token':'not-a-real-token'}).status_code,200)
            self.assertEqual(config.github_token,'not-a-real-token')
            self.assertIn('GITHUB_TOKEN',connections.ENV_FILE.read_text())
            data=self.client.get('/api/permissions').json()
            self.assertNotIn('not-a-real-token',str(data))
            self.assertTrue(all(c['url'].startswith('https://') for c in data['connections']))

    def test_public_welcome_uses_native_menu_and_does_not_require_login(self):
        from types import SimpleNamespace
        bot=TelegramBot();bot.owner_id=999
        message=SimpleNamespace(reply_text=AsyncMock())
        update=SimpleNamespace(effective_chat=SimpleNamespace(type='private'),effective_user=SimpleNamespace(id=108,first_name='Visitor'),effective_message=message)
        ctx=SimpleNamespace(bot=SimpleNamespace(set_chat_menu_button=AsyncMock()))
        asyncio.run(bot.public_start(update,ctx))
        self.assertTrue(bot.public.get(108)['subscribed'])
        self.assertIn('10 ta',message.reply_text.call_args.args[0])
        self.assertNotIn('/login',message.reply_text.call_args.args[0])
        self.assertEqual(ctx.bot.set_chat_menu_button.call_args.kwargs['menu_button'].type,'commands')

    def test_public_weather_only_once_per_day(self):
        from types import SimpleNamespace
        from datetime import datetime
        from ali.telegram_store import TZ
        bot=TelegramBot();uid=109
        data=bot.public.get(uid);data.update(weather=True,location={'lat':41,'lon':69},subscribed=False);bot.public.put(uid,data)
        bot.app=SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))
        class Clock:
            @staticmethod
            def now(tz):return datetime(2026,10,15,8,0,tzinfo=TZ)
        with patch('ali.telegram_public.datetime',Clock),patch.object(bot.public,'subscribers',side_effect=lambda:[(uid,bot.public.get(uid))]),patch.object(bot,'weather_text',new=AsyncMock(return_value='Weather')):
            asyncio.run(bot.public_tick());asyncio.run(bot.public_tick())
        self.assertEqual(bot.app.bot.send_message.await_count,1)

    def test_weather_callback_preserves_owner_menu(self):
        from types import SimpleNamespace
        bot=TelegramBot();bot.owner_id=999
        q=SimpleNamespace(from_user=SimpleNamespace(id=999),data='pub:weather:off',answer=AsyncMock(),message=SimpleNamespace(reply_text=AsyncMock()))
        update=SimpleNamespace(effective_chat=SimpleNamespace(type='private'),effective_user=q.from_user,callback_query=q)
        asyncio.run(bot.public_button(update,None))
        keyboard=q.message.reply_text.call_args.kwargs['reply_markup']
        self.assertIn('⚙️ Sozlamalar',[b.text for row in keyboard.keyboard for b in row])

    def test_stop_removes_weather_location_and_notifications(self):
        from types import SimpleNamespace
        bot=TelegramBot();uid=110
        data=bot.public.get(uid);data.update(weather=True,subscribed=True,location={'lat':41,'lon':69});bot.public.put(uid,data)
        update=SimpleNamespace(effective_chat=SimpleNamespace(type='private'),effective_user=SimpleNamespace(id=uid),effective_message=SimpleNamespace(reply_text=AsyncMock()))
        asyncio.run(bot.public_stop(update,None))
        saved=bot.public.get(uid)
        self.assertFalse(saved['weather']);self.assertFalse(saved['subscribed']);self.assertNotIn('location',saved)

    def test_public_telegram_routes_guests_without_owner_brain(self):
        from types import SimpleNamespace
        bot=TelegramBot();bot.owner_id=999;bot.users={999}
        update=SimpleNamespace(effective_chat=SimpleNamespace(id=101,type='private'),effective_user=SimpleNamespace(id=101,first_name='Guest'),message=SimpleNamespace(text='Salom'))
        with patch.object(bot,'menu_text',new=AsyncMock(return_value=False)),patch.object(bot,'public_process',new=AsyncMock()) as public,patch.object(bot,'process',new=AsyncMock()) as owner:
            asyncio.run(bot.on_text(update,None))
            public.assert_awaited_once();owner.assert_not_awaited()

    def test_public_telegram_location_does_not_replace_owner_location(self):
        from types import SimpleNamespace
        from ali.hub import hub
        bot=TelegramBot();bot.owner_id=999
        update=SimpleNamespace(effective_chat=SimpleNamespace(type='private'),effective_user=SimpleNamespace(id=102),message=SimpleNamespace(location=SimpleNamespace(latitude=40,longitude=70,horizontal_accuracy=1)))
        with patch.object(hub,'last_location',{'lat':1,'lon':2}),patch.object(bot,'save_location',new=AsyncMock()):
            asyncio.run(bot.on_location(update,None))
            self.assertEqual(hub.last_location,{'lat':1,'lon':2})

    def test_public_requests_deduplicate_and_subscription_duration(self):
        from ali.telegram_store import PublicStore
        import time
        store=PublicStore()
        rid,fresh=store.request(103,'trading_week','test')
        self.assertTrue(fresh)
        self.assertEqual(store.request(103,'trading_week','again'),(rid,False))
        before=time.time();store.resolve(rid,True)
        expires=store.get(103)['grants']['trading']
        self.assertAlmostEqual(expires-before,7*86400,delta=2)
        self.assertIsNone(store.resolve(rid,True))
        self.assertEqual(store.get(104)['grants'],{})

    def test_guest_cannot_approve_own_request(self):
        from types import SimpleNamespace
        bot=TelegramBot();bot.owner_id=999
        rid,_=bot.public.request(105,'content','test')
        query=SimpleNamespace(from_user=SimpleNamespace(id=105),data=f'own:{rid}:yes',answer=AsyncMock())
        update=SimpleNamespace(effective_chat=SimpleNamespace(type='private'),effective_user=query.from_user,callback_query=query)
        asyncio.run(bot.public_button(update,None))
        self.assertEqual(bot.public.get(105)['grants'],{})

    def test_public_quota_and_history_are_separate(self):
        from ali.telegram_store import PublicStore
        store=PublicStore()
        for _ in range(10):self.assertTrue(store.quota(106))
        self.assertFalse(store.quota(106))
        self.assertTrue(store.quota(107))
        data=store.get(106);data['history']=[{'role':'user','content':'private guest test'}];store.put(106,data)
        self.assertEqual(store.get(107)['history'],[])
        from ali.memory import memory
        self.assertEqual(memory.vault_list('private guest test')['total'],0)

    def test_malformed_api_inputs_are_rejected(self):
        self.assertEqual(self.client.post('/api/login', json=[]).status_code, 400)
        self.login()
        for route in ['/api/vault', '/api/permissions', '/api/agents', '/api/tts']:
            self.assertEqual(self.client.post(route, json=[]).status_code, 400)
            self.assertEqual(self.client.post(route, content='{', headers={'Content-Type':'application/json'}).status_code, 400)
        self.assertEqual(self.client.post('/api/agents', json={'tools':5}).status_code, 400)
        self.assertEqual(self.client.post('/api/tts', json={'text':[]}).status_code, 400)

    def test_permissions_enforce_auto_ask_deny_and_reload(self):
        from ali import permissions
        from ali.skills import Skill
        from unittest.mock import Mock
        fn = Mock(return_value='ok')
        tool = Skill('permission_test','Test',{},[],fn,True)
        path=Path(state.name)/'permission-test.json'
        with patch.object(permissions,'PATH',path), patch.dict(brain.registry,{'permission_test':tool}), patch.object(brain,'confirm',return_value=False) as confirm:
            self.assertTrue(brain._run_one('permission_test',{})[1])
            fn.assert_not_called()
            permissions.save({'permission_test':'auto'},brain.registry)
            self.assertEqual(brain._run_one('permission_test',{}),('ok',False))
            self.assertEqual(confirm.call_count,1)
            permissions.save({'permission_test':'deny'},brain.registry)
            self.assertTrue(brain._run_one('permission_test',{})[1])
            self.assertEqual(fn.call_count,1)
            self.assertEqual(permissions.load()['rules']['permission_test'],'deny')
            path.write_text('broken',encoding='utf-8')
            self.assertEqual(permissions.mode('permission_test'),'deny')

    def test_permissions_api_auth_validation_and_catalog(self):
        from ali import permissions
        path=Path(state.name)/'permissions-api.json'
        with patch.object(permissions,'PATH',path):
            self.assertEqual(self.client.get('/api/permissions').status_code,401)
            self.assertEqual(self.client.post('/api/permissions',json={'rules':{}}).status_code,401)
            self.login()
            data=self.client.get('/api/permissions').json()
            self.assertIn('write_project_file',[t['name'] for t in data['tools']])
            self.assertTrue(all('token' not in c and 'secret' not in c for c in data['connections']))
            self.assertEqual(self.client.post('/api/permissions',json={'rules':{'fake_tool':'auto'}}).status_code,400)
            self.assertEqual(self.client.post('/api/permissions',json={'rules':{'web_search':'ask'}}).status_code,400)
            self.assertEqual(self.client.post('/api/permissions',json={'rules':{}},headers={'Origin':'https://untrusted.test'}).status_code,403)
            self.assertEqual(self.client.post('/api/permissions',json={'rules':{'get_datetime':'deny'}}).status_code,200)
            self.assertEqual(permissions.mode('get_datetime'),'deny')

    def test_vault_auth_search_detail_and_persistent_note(self):
        from ali.memory import memory, Memory
        self.assertEqual(self.client.get('/api/vault').status_code, 401)
        self.assertEqual(self.client.post('/api/vault', json={'title':'x','content':'y'}).status_code, 401)
        self.login()
        self.assertEqual(self.client.post('/api/vault', json={'title':'','content':'x'}).status_code, 400)
        response = self.client.post('/api/vault', json={'title':'Vault test', 'content':'Unique vault needle <script>alert(1)</script>'})
        record_id = response.json()['id']
        result = self.client.get('/api/vault', params={'q':'Unique vault needle'}).json()
        self.assertEqual(result['total'],1)
        self.assertEqual(result['items'][0]['id'],record_id)
        self.assertNotIn('content',result['items'][0])
        self.assertIn('<script>',self.client.get('/api/vault/entry',params={'id':record_id}).json()['content'])
        second = Memory(config.db_path)
        try:
            self.assertEqual(second.vault_detail(record_id)['title'],'Vault test')
        finally:
            second.conn.close()
        self.assertEqual(self.client.get('/api/vault/entry',params={'id':'../../.env'}).status_code,404)

    def test_vault_news_history_and_exact_duplicate(self):
        from ali.memory import memory
        one = memory.add_knowledge('[yangiliklar] Test news','Source https://example.com unique-news')
        two = memory.add_knowledge('[yangiliklar] Test news','Source https://example.com unique-news')
        self.assertEqual(one,two)
        memory.log_message('vault-test','user','A past conversation needle')
        self.assertEqual(memory.vault_list('unique-news','news')['total'],1)
        self.assertEqual(memory.vault_list('past conversation needle','chats')['total'],1)
        self.assertEqual(memory.vault_list('unique-news','identity')['total'],0)

    def test_learning_failure_retries_without_claiming_success(self):
        from ali import autopilot
        import threading
        from types import SimpleNamespace
        fake = SimpleNamespace(agents={"tester": SimpleNamespace(learn=[], description="Testing")}, lock=threading.Lock())
        path = Path(state.name) / "learning-test.json"
        with patch.object(autopilot, "STATE", path), patch.object(config, "auto_learn", True), patch.object(config, "watch_projects", False), patch.object(autopilot, "learn", side_effect=RuntimeError("API failed")) as learn:
            autopilot._tick(fake)
            saved = autopilot._load()
            self.assertEqual(saved["learning"]["tester"]["status"], "error")
            self.assertNotIn("tester", saved["learn"])
            self.assertFalse(fake.lock.locked())
            autopilot._tick(fake)
            self.assertEqual(learn.call_count, 1)

    def test_learning_success_tracks_saved_knowledge_and_waits(self):
        from ali import autopilot
        from ali.memory import memory
        import threading
        from types import SimpleNamespace
        fake = SimpleNamespace(agents={"research-test": SimpleNamespace(learn=["Research"], description="Testing")}, lock=threading.Lock())
        path = Path(state.name) / "learning-success.json"
        def learn(*args):
            memory.add_knowledge("[research-test] Verified topic", "Source: https://example.com; checked today")
            return "Saved one topic"
        with patch.object(autopilot, "STATE", path), patch.object(config, "auto_learn", True), patch.object(config, "watch_projects", False), patch.object(autopilot, "learn", side_effect=learn) as run:
            autopilot._tick(fake)
            saved = autopilot.learning_status(fake)
            self.assertEqual(saved["agents"]["research-test"]["status"], "updated")
            self.assertEqual(saved["agents"]["research-test"]["added"], 1)
            autopilot._tick(fake)
            self.assertEqual(run.call_count, 1)

    def test_self_improve_fixes_tools_adds_lessons_and_rolls_back(self):
        from ali import evolution
        from ali.skills import REGISTRY
        agents.save("evo-test", "Evo", "E", "Testing", ["search_knowledge", "missing_tool"], "Base prompt", ["Topic"])
        try:
            report = evolution.health(REGISTRY, "evo-test")
            self.assertIn("missing_tool", report["unknown_tools"])
            self.assertLess(report["score"], 100)
            self.assertEqual(evolution.auto_fix(REGISTRY, "evo-test"), ["Mavjud bo'lmagan vositalar olib tashlandi: missing_tool"])
            self.assertEqual(agents.load()["evo-test"].tools, ["search_knowledge"])
            self.assertIn("Qo'shib bo'lmaydi", evolution.improve(REGISTRY, "evo-test", add_tools=["write_project_file"]))
            result = evolution.improve(REGISTRY, "evo-test", lessons=["Avval manbani tekshir", "Avval manbani tekshir"], learn=["New topic"])
            self.assertIn("+1 saboq", result)
            a = agents.load()["evo-test"]
            self.assertTrue(a.prompt.startswith("Base prompt"))
            self.assertEqual(evolution.split_lessons(a.prompt)[1], ["Avval manbani tekshir"])
            self.assertEqual(a.learn, ["Topic", "New topic"])
            self.assertIn("O'zgarish yo'q", evolution.improve(REGISTRY, "evo-test", lessons=["avval manbani tekshir"]))
            evolution.rollback("evo-test")
            self.assertEqual(agents.load()["evo-test"].prompt, "Base prompt")
            evolution.rollback("evo-test")
            self.assertIn("missing_tool", agents.load()["evo-test"].tools)
        finally:
            agents.delete("evo-test")

    def test_self_improve_cycle_one_agent_per_tick_reports_and_retries(self):
        from ali import autopilot, evolution
        import threading
        from types import SimpleNamespace
        fake = SimpleNamespace(agents={"a1": SimpleNamespace(icon="A", name="One"), "a2": SimpleNamespace(icon="B", name="Two")},
                               lock=threading.Lock(), registry={})
        path = Path(state.name) / "improve-test.json"
        calls = []
        def cycle(brain, key, last):
            calls.append(key)
            if key == "a2" and calls.count("a2") == 1:
                raise RuntimeError("API failed")
            return {"status": "healthy", "score": 100, "issues": [], "fixed": [], "summary": "", "jobs_seen": 0}
        with patch.object(autopilot, "STATE", path), patch.object(config, "auto_learn", False), \
                patch.object(config, "watch_projects", False), patch.object(config, "self_improve", True), \
                patch.object(evolution, "run_cycle_for", side_effect=cycle), patch.object(autopilot.hub, "notify") as notify:
            autopilot._tick(fake)
            autopilot._tick(fake)
            autopilot._tick(fake)
            self.assertEqual(calls, ["ali", "a1", "a2"])
            self.assertEqual(autopilot._load()["improve"]["a2"]["status"], "error")
            self.assertFalse(fake.lock.locked())
            autopilot._tick(fake)  # a2 bir soat kutadi, hisobot hali yo'q
            notify.assert_not_called()
            data = autopilot._load(); data["improve"]["a2"]["retry_at"] = 0; autopilot._save(data)
            autopilot._tick(fake)
            autopilot._tick(fake)
            self.assertEqual(calls, ["ali", "a1", "a2", "a2"])
            notify.assert_called_once()
            self.assertIn("100/100", notify.call_args[0][0])
            self.assertIn("🧠", notify.call_args[0][0])
            autopilot._tick(fake)
            self.assertEqual(len(calls), 4)
            notify.assert_called_once()

    def test_ali_self_improve_lessons_reach_system_prompt_and_roll_back(self):
        from ali import evolution
        from ali.brain import build_system_prompt
        from ali.monitor import monitor
        from ali.skills import REGISTRY
        evolution.ALI_PATH.unlink(missing_ok=True)
        job = monitor.start_job("ali", "Broken request", "test")
        monitor.finish(job, False)
        report = evolution.health(REGISTRY, "ali")
        self.assertEqual(report["key"], "ali")
        self.assertIn("Broken request", report["failed_tasks"])
        self.assertIn("faqat lessons", evolution.improve(REGISTRY, "ali", learn=["x"]))
        self.assertIn("+1 saboq", evolution.improve(REGISTRY, "ali", lessons=["Fayl so'ralsa avval list_projects ishlat"]))
        self.assertIn("Fayl so'ralsa avval list_projects ishlat", build_system_prompt({}))
        self.assertIn("O'zgarish yo'q", evolution.improve(REGISTRY, "ali", lessons=["fayl so'ralsa avval list_projects ishlat"]))
        evolution.rollback("ali")
        self.assertEqual(evolution.ali_lessons(), [])
        self.assertNotIn("Tajriba (o'z xatolaringdan", build_system_prompt({}))

    def test_mtf_signal_blocks_against_higher_timeframe_and_aggregates_4h(self):
        from ali.skills import signals
        hourly = [signals.Bar(i * 3600, 1 + i, 2 + i, i, 1.5 + i) for i in range(8)]
        four = signals._aggregate(hourly, 4 * 3600)
        self.assertEqual([(b.t, b.o, b.h, b.l, b.c) for b in four], [(0, 1, 5, 0, 4.5), (14400, 5, 9, 4, 8.5)])
        up = [signals.Bar(i, 100 + i, 101 + i, 99 + i, 100.5 + i) for i in range(120)]
        down = [signals.Bar(i, 300 - i, 301 - i, 299 - i, 299.5 - i) for i in range(120)]
        fetch = lambda symbol, market, interval, htf=False: down if interval == "1d" or htf else up
        def analyze(symbol, market, interval, bars, htf):
            return signals.Plan(symbol=symbol, market=market, interval=interval, side=1, score=3, setup="EMA cross",
                                entry=1, sl=0.5, tps=(1.75, 2.1, 2.5), zone=(0.9, 1.1))
        with patch.object(signals, "_fetch", side_effect=fetch), patch.object(signals, "analyze", side_effect=analyze):
            plans = signals._mtf_plans("EURUSD", "auto")
            self.assertEqual([p.side for p in plans], [0, 0, 0, 1])
            self.assertIn("Yuqori timeframe qarshi: 1d DOWN", plans[0].reason)
            text = signals.mtf_signal("EURUSD")
            self.assertIn("1d: ▲ LONG", text)
            self.assertIn("Eng kuchli tekshirilgan signal", text)
        def opposed(symbol, market, interval, bars, htf):
            plan = analyze(symbol, market, interval, bars, htf)
            plan.against = 1
            return plan
        with patch.object(signals, "_fetch", side_effect=lambda *a, **k: up), patch.object(signals, "analyze", side_effect=opposed):
            self.assertIn("Hamma tekshiruvdan o'tgan signal yo'q", signals.mtf_signal("EURUSD"))

    def test_mt5_signals_reads_v5_csv_and_hides_unverified(self):
        from ali.skills import signals
        folder = Path(state.name) / "mt5files"
        folder.mkdir(exist_ok=True)
        (folder / "AZT_signals_v5.csv").write_text(
            "time,symbol,timeframe,side,setup,entry,sl,tp1,tp2,tp3,zone_low,zone_high,score,atr,ai,ai_conf,sent,mtf\r\n"
            "2026.10.15 10:00,EURUSD,M15,BUY,EMA cross,1.1,1.09,1.115,1.12,1.13,1.099,1.101,3,0.001,APPROVE,82,1,Yuqori TF: H1 ▲UP\r\n"
            "2026.10.15 11:00,EURUSD,H1,SELL,BOS,1.1,1.11,1.085,1.08,1.07,1.099,1.101,2,0.002,REJECT,40,0,\r\n",
            encoding="utf-8")
        with patch.dict(os.environ, {"MT5_FILES_DIR": str(folder)}):
            sent = signals.mt5_signals()
            self.assertIn("Claude APPROVE 82%", sent)
            self.assertNotIn("SELL", sent)
            self.assertIn("❌ yuborilmagan", signals.mt5_signals(all=True))

    def test_agent_upgrade_keeps_lessons_and_extra_topics(self):
        source, target = Path(state.name) / "upgrade-src", Path(state.name) / "upgrade-dst"
        source.mkdir(exist_ok=True); target.mkdir(exist_ok=True)
        (target / "trader.md").write_text("---\nnom: Old\nbelgi: T\ntavsif: old\nvositalar: a\no'rganish: x; coach topic\n---\n"
                                          "Old prompt\n\n## Tajriba (avtomatik)\n- Keep this lesson\n", encoding="utf-8")
        (source / "trader.md").write_text("---\nnom: New\nbelgi: T\ntavsif: new\nvositalar: a, b\no'rganish: x\nversiya: 2\n---\n"
                                          "New prompt\n", encoding="utf-8")
        self.assertEqual(agents.upgrade_defaults(source, target), ["trader"])
        a = agents._parse("trader", (target / "trader.md").read_text(encoding="utf-8"))
        self.assertTrue(a.prompt.startswith("New prompt"))
        self.assertIn("- Keep this lesson", a.prompt)
        self.assertEqual((a.version, a.tools, a.learn), (2, ["a", "b"], ["x", "coach topic"]))
        self.assertEqual(agents.upgrade_defaults(source, target), [])
        repo = {k: agents._parse(k, (Path(__file__).resolve().parents[1] / "agents" / f"{k}.md").read_text(encoding="utf-8"))
                for k in ("treyder",)}
        from ali.skills import REGISTRY
        self.assertEqual(repo["treyder"].version, 2)
        self.assertTrue(set(repo["treyder"].tools) - {"web_search"} <= set(REGISTRY))

    def test_coach_agent_and_improve_skills_are_registered(self):
        from ali.skills import REGISTRY
        coach = agents._parse("murabbiy", (Path(__file__).resolve().parents[1] / "agents" / "murabbiy.md").read_text(encoding="utf-8"))
        self.assertTrue(set(coach.tools) - {"web_search"} <= set(REGISTRY))
        for name in ("agent_health", "improve_agent", "rollback_agent", "improve_agents_now"):
            self.assertFalse(REGISTRY[name].dangerous)

    def test_restricted_agent_cannot_call_unlisted_tools(self):
        from types import SimpleNamespace
        block = SimpleNamespace(type="tool_use", name="write_project_file", input={}, id="blocked")
        with patch.object(brain, "_run_one") as run:
            results = brain._run_tools([block], lambda *args: None, {"search_knowledge"})
            self.assertTrue(results[0]["is_error"])
            run.assert_not_called()

    def test_agent_respects_web_search_deny_and_sees_user_facts(self):
        from types import SimpleNamespace
        from ali import permissions
        from ali.memory import memory
        captured = {}

        def fake_call(emit, effort, system=None, tools=None, messages=None):
            captured.update(system=system, tools=tools)
            return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="ok")])

        memory.set_fact("test_sevimli_rang", "ko'k")
        path = Path(state.name) / "permission-web.json"
        try:
            with patch.object(permissions, "PATH", path), patch.object(config, "web_search", True), \
                 patch.object(brain, "_call", side_effect=fake_call):
                permissions.save({"web_search": "deny"}, brain.registry)
                brain._run_agent({"agent": "yangiliklar", "task": "yangilik"}, lambda *a: None)
                self.assertNotIn("web_search", [t["name"] for t in captured["tools"]])
                self.assertIn("test_sevimli_rang", captured["system"])
                permissions.save({"web_search": "auto"}, brain.registry)
                brain._run_agent({"agent": "yangiliklar", "task": "yangilik"}, lambda *a: None)
                self.assertIn("web_search", [t["name"] for t in captured["tools"]])
        finally:
            memory.delete_fact("test_sevimli_rang")

    def test_github_push_creates_and_updates_with_sha(self):
        import base64, json
        import httpx
        from ali.skills import github as gh
        seen = []

        def handler(request):
            if request.method == "GET":
                if "missing.py" in request.url.path:
                    return httpx.Response(404, json={})
                return httpx.Response(200, json={"sha": "abc123"})
            seen.append(json.loads(request.content))
            return httpx.Response(201, json={"commit": {"html_url": "https://github.com/u/r/commit/1"}})

        transport = httpx.MockTransport(handler)
        with patch.object(gh, "_client", lambda: httpx.Client(base_url=gh.API, transport=transport)), \
             patch.object(gh, "_repo", lambda r: "u/r"):
            out1 = gh.github_push_file("r", "missing.py", "print(1)", "yangi")
            out2 = gh.github_push_file("r", "ali/x.py", "print(2)", "yangila")
        self.assertIn("commit/1", out1)
        self.assertNotIn("sha", seen[0])
        self.assertEqual(seen[1]["sha"], "abc123")
        self.assertEqual(base64.b64decode(seen[1]["content"]).decode(), "print(2)")
        from ali.skills import REGISTRY
        self.assertTrue(REGISTRY["github_push_file"].dangerous)

    def test_failed_turn_rolls_back_pending_messages(self):
        before = list(brain.messages)
        with patch.object(brain, "_call", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                brain._ask("test savol", None, False, False, None)
        self.assertEqual(brain.messages, before)

    def setUp(self):
        self.client = TestClient(app)

    def login(self):
        result = self.client.post("/api/login", json={"password": "test-password"})
        self.assertEqual(result.status_code, 200)

    def test_site_opens_without_ai_key_and_requires_login(self):
        self.assertEqual(self.client.get("/healthz").status_code, 200)
        self.assertEqual(self.client.get("/").url.path, "/login")
        self.assertEqual(self.client.get("/api/agents").status_code, 401)
        self.login()
        self.assertIn('id="feed"', self.client.get("/").text)
        self.assertEqual(self.client.get("/api/status").status_code, 200)
        self.assertTrue(self.client.get("/api/agents").json()["agents"])

    def test_auth_unicode_is_rejected_without_crashing(self):
        self.assertFalse(auth.check_password("пароль"))
        self.assertFalse(auth.check_token("пароль"))

    def test_session_survives_new_brain(self):
        first = Brain()
        first.messages = [{"role": "user", "content": "salom"},
                          {"role": "assistant", "content": "Assalomu alaykum"}]
        first._save_session()
        second = Brain()
        self.assertEqual(first.session_id, second.session_id)
        self.assertEqual(first.messages, second.messages)
        second.new_session()
        self.assertEqual(Brain().messages, [])

    def test_agent_edits_and_deletion_survive_reload(self):
        agents.save("test-agent", "Test", "T", "Test", [], "Test prompt")
        self.assertIn("test-agent", agents.load())
        agents.delete("test-agent")
        importlib.reload(agents)
        self.assertNotIn("test-agent", agents.load())
        self.assertTrue(str(agents.AGENTS_DIR).startswith(state.name))
        with self.assertRaises(ValueError):
            agents.delete("../secrets")

    def test_websocket_auth_and_history(self):
        from starlette.websockets import WebSocketDisconnect
        with self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect("/ws"):
                pass
        self.login()
        with self.client.websocket_connect("/ws") as ws:
            self.assertEqual(ws.receive_json()["type"], "hello")
            self.assertEqual(ws.receive_json()["type"], "history")

    def test_vercel_gateway_does_not_import_runtime(self):
        client = TestClient(gateway)
        with patch.dict(os.environ, {"ALI_BACKEND_URL": ""}):
            self.assertEqual(client.get("/").status_code, 503)
        with patch.dict(os.environ, {"ALI_BACKEND_URL": "https://ali.example.com"}):
            result = client.get("/login?next=chat", follow_redirects=False)
            self.assertEqual(result.status_code, 307)
            self.assertEqual(result.headers["location"], "https://ali.example.com/login?next=chat")
        with patch.dict(os.environ, {"ALI_BACKEND_URL": "https://user:secret@ali.example.com"}):
            self.assertEqual(client.get("/").status_code, 503)

    def test_telegram_panel_and_private_guard(self):
        bot = TelegramBot()
        with patch.object(config, "public_url", "https://ali.example.com"):
            self.assertEqual(bot.site_keyboard().inline_keyboard[0][0].web_app.url,
                             "https://ali.example.com/miniapp")
        from types import SimpleNamespace
        update = SimpleNamespace(effective_chat=SimpleNamespace(type="group"),
                                 effective_message=SimpleNamespace(reply_text=AsyncMock()))
        self.assertFalse(asyncio.run(bot._guard(update)))

    def test_chat_request_reaches_brain_and_returns_response(self):
        with patch("runtime.scheduler.start"), patch("runtime.autopilot.start"), \
                patch.object(brain, "ask", return_value="Sinov javobi") as ask:
            with TestClient(app) as client:
                client.post("/api/login", json={"password": "test-password"})
                with client.websocket_connect("/ws") as ws:
                    ws.receive_json()  # hello
                    ws.receive_json()  # history
                    ws.send_json({"type": "ask", "id": "test-turn", "text": "Salom",
                                  "super": False, "agent": "treyder"})
                    for _ in range(12):
                        message = ws.receive_json()
                        if message["type"] == "done":
                            self.assertEqual(message["text"], "Sinov javobi")
                            self.assertEqual(message["id"], "test-turn")
                            break
                    else:
                        self.fail("Chat did not return a result")
                self.assertEqual(ask.call_args.args[0], "Salom")
                self.assertIs(ask.call_args.args[3], True)
                self.assertIsNone(ask.call_args.args[5])

    def test_super_mode_consults_models_before_ali_answers(self):
        from types import SimpleNamespace
        from anthropic.types import TextBlock
        response = SimpleNamespace(stop_reason="end_turn", content=[TextBlock(type="text", text="Ali javobi")])
        b = Brain()
        events = []
        with patch("ali.brain.providers.available", return_value={"openai": True}), \
                patch("ali.brain.providers.ask_all", return_value={"GPT": "Tekshiriladigan maslahat"}) as experts, \
                patch.object(b, "_call", return_value=response):
            self.assertEqual(b.ask("Reja tuz", on_event=lambda k, d: events.append((k, d)), super_mode=True), "Ali javobi")
        experts.assert_called_once()
        self.assertIn("Reja tuz", experts.call_args.args[0])
        self.assertEqual(events[0][0], "tool_start")
        self.assertEqual(events[1][0], "tool_end")
        self.assertIn("Tekshiriladigan maslahat", b.messages[-2]["content"])

    def test_super_mode_advisor_failure_does_not_block_ali(self):
        from types import SimpleNamespace
        from anthropic.types import TextBlock
        response = SimpleNamespace(stop_reason="end_turn", content=[TextBlock(type="text", text="Ali davom etdi")])
        b = Brain()
        with patch("ali.brain.providers.available", return_value={"gemini": True}), \
                patch("ali.brain.providers.ask_all", return_value={"Gemini": "[xato: unavailable]"}), \
                patch.object(b, "_call", return_value=response):
            self.assertEqual(b.ask("Salom", super_mode=True), "Ali davom etdi")


if __name__ == "__main__":
    unittest.main()
