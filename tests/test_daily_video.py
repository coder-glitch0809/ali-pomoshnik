import json
import tempfile
import unittest
import zipfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import test_runtime  # noqa: F401 - vaqtinchalik ALI_STATE_DIR va test sozlamalari ali'dan oldin o'rnatilsin
from ali import chat_import, daily_video


class DailyVideoTests(unittest.TestCase):
    def test_runs_at_11_and_16_once_and_skips_stale_slots(self):
        started = []
        with tempfile.TemporaryDirectory() as d, patch.object(daily_video, "STATE", Path(d) / "dv.json"), \
                patch.object(daily_video.threading, "Thread") as thread:
            thread.side_effect = lambda target, args, **kw: started.append(args[0]) or unittest.mock.MagicMock()
            daily_video.tick(print, datetime(2026, 11, 5, 10, 59))
            daily_video.tick(print, datetime(2026, 11, 5, 11, 0, 30))
            daily_video.tick(print, datetime(2026, 11, 5, 11, 5))  # qayta yoqilgandek - takrorlanmaydi
            self.assertEqual(started, ["11:00"])
            # kompyuter uxlagan: 10 soatdan eskisi (11:00) o'tkaziladi, 16:00 uyg'ongach yasaladi
            daily_video.tick(print, datetime(2026, 11, 6, 23, 30))
            self.assertEqual(started, ["11:00", "16:00"])

    def test_template_without_ai_has_all_scenes_and_cta(self):
        data = {**daily_video.IDEAS[1], "scenes": daily_video.IDEAS[1]["scenes"]}
        page = daily_video.template(data)
        self.assertIn("@keyframes", page)
        self.assertIn("HAJMLI HARFLAR", page)
        self.assertIn("Bepul o&#x27;lchov", page)
        self.assertNotIn("<script", page)

    def test_idea_without_ai_rotates_topics(self):
        with tempfile.TemporaryDirectory() as d, patch.object(daily_video, "STATE", Path(d) / "dv.json"), \
                patch("ali.service._ask_json", side_effect=RuntimeError("limit")):
            first, src = daily_video.idea("11:00")
            daily_video._save({"history": [{"title": first["title"]}]})
            second, _ = daily_video.idea("16:00")
        self.assertEqual(src, "bilim")
        self.assertNotEqual(first["title"], second["title"])
        self.assertGreaterEqual(len(first["scenes"]), 3)


class CouncilGateTests(unittest.TestCase):
    def _run(self, score):
        from ali import studio_flow
        res = {"path": "v.mp4", "sources": "g'oya: AI", "idea": {**daily_video.IDEAS[0], "caption": "c", "hashtags": "#h",
                                                                 "scenes": daily_video.IDEAS[0]["scenes"]}}
        with tempfile.TemporaryDirectory() as d, patch.object(daily_video, "STATE", Path(d) / "dv.json"), \
                patch.object(studio_flow, "STATE", Path(d) / "st.json"), \
                patch.object(daily_video, "make", return_value=res), \
                patch("ali.team_hub.review_video", return_value=("qaror", score)), \
                patch("ali.tg_account.send_file", return_value=7) as post, \
                patch.object(studio_flow, "send_files") as owner:
            daily_video.run("11:00", print)
        return post.call_count, owner.call_args[0][0]

    def test_video_goes_to_channel_only_after_council_approves(self):
        posted, text = self._run(8.0)
        self.assertEqual(posted, 1)
        self.assertIn("Kengash bahosi: 8/10", text)
        posted, text = self._run(3.0)
        self.assertEqual(posted, 0)
        self.assertIn("kengashdan o'tmadi", text)

    def test_score_parsed_from_decision(self):
        from ali.team_hub import score_of
        self.assertEqual(score_of("📊 Instagram uchun BAHO: 7/10 - hook kuchli"), 7.0)
        self.assertEqual(score_of("Baho: 6.5 — o'rtacha"), 6.5)
        self.assertIsNone(score_of("baho berilmadi"))


class VoiceAndCharacterTests(unittest.TestCase):
    def test_numbers_spoken_as_uzbek_words(self):
        from ali.tts import say_numbers
        self.assertIn("nol", say_numbers("0 ta xato"))
        self.assertIn("o'n ikki million bir yuz sakson ming", say_numbers("12.180.000 SOM"))
        self.assertIn("yigirma foiz", say_numbers("20% chegirma"))
        self.assertIn("олти бутун беш", say_numbers("Баҳо 6.5"))

    def test_character_appears_in_template_and_saved_from_photo_caption(self):
        page = daily_video.template({**daily_video.IDEAS[0], "scenes": daily_video.IDEAS[0]["scenes"]}, 20,
                                    "data:image/jpeg;base64,AAAA")
        self.assertIn('class="hero" src="data:image/jpeg;base64,AAAA"', page)
        self.assertIn("@keyframes talk", page)
        self.assertTrue(daily_video.CHAR_SAVE.search("shu personajni eslab qol"))
        with tempfile.TemporaryDirectory() as d, patch.object(daily_video, "CHAR_DIR", Path(d) / "ch"):
            img = Path(d) / "a.png"
            img.write_bytes(b"png")
            daily_video.save_character(str(img))
            self.assertEqual(daily_video.character().name, "personaj.png")

    def test_video_order_makes_video_not_brief(self):
        from ali import montage, studio_flow
        text = "Таргет учун битта видео килиб бер лида ва вовлечения нима учун йокилишини оргатадиган видео"
        self.assertTrue(montage.is_creation(text))
        self.assertFalse(studio_flow.is_query(text))
        self.assertTrue(studio_flow.is_query("kreativ reels video uchun brif tuz"))


class TalkingHeadTests(unittest.TestCase):
    def test_scene_visual_matches_topic(self):
        from ali.skills import motion_bg
        self.assertEqual(motion_bg.pick({"big": "LIDLAR YO'QOLADI"}, []), "chart_down")
        self.assertEqual(motion_bg.pick({"big": "Noto'g'ri auditoriya"}, []), "warning")
        self.assertEqual(motion_bg.pick({"big": "x", "visual": "rocket"}, []), "rocket")
        html, css = motion_bg.layer([{"big": "Narx arzon"}, {"big": "Direktga yozing"}], 5, 10)
        self.assertIn("SO'M", html)
        self.assertIn("@keyframes draw", css)

    def test_template_with_talking_face_and_mouth_levels(self):
        import numpy as np
        from ali.skills import talking_head
        face = {"base": "data:image/png;base64,AAAA", "w": 900, "h": 1125, "blink": ("data:b", 1, 2, 3, 4),
                "mouths": [("data:m", 10, 20, 30, 40)] * 7}
        page = daily_video.template({**daily_video.IDEAS[0], "scenes": daily_video.IDEAS[0]["scenes"]}, 20, face)
        self.assertIn("window.__face", page)
        self.assertEqual(page.count('class="fm"'), 7)
        self.assertIn('class="grid"', page)
        tone = np.concatenate([np.zeros(8000), 0.5 * np.sin(np.arange(8000) / 3), np.zeros(8000)])
        with tempfile.TemporaryDirectory() as d:
            wav = Path(d) / "v.wav"
            import wave
            with wave.open(str(wav), "wb") as w:
                w.setnchannels(1), w.setsampwidth(2), w.setframerate(16000)
                w.writeframes((tone * 32767).astype("<i2").tobytes())
            lv = talking_head.levels(wav, 1.5, 30)
        self.assertEqual(lv[:10], [0] * 10)  # jimlik - og'iz yopiq
        self.assertGreater(max(lv[16:30]), 4)  # ovoz - og'iz ochiq
        self.assertTrue(any(talking_head.blinks(10, 30)))


class PresenterTests(unittest.TestCase):
    def test_gestures_change_and_frames_are_complete(self):
        from ali.skills import presenter
        got = presenter.frames(5, 4.0, 20, 30, [3] * 600, [False] * 600)
        self.assertEqual(len(got), 600)
        self.assertIn("polyline", got[100]["a"])
        self.assertNotEqual(got[150]["a"], got[210]["a"])  # qo'llar harakatlanadi
        self.assertNotEqual(got[10]["h"], got[40]["h"])  # bosh qimirlaydi
        self.assertNotEqual(got[60]["x"], got[200]["x"])  # sahnalar orasida joy almashadi

    def test_stage_has_diagram_for_each_scene_without_invented_numbers(self):
        from ali.skills import stage
        scenes = [{"big": "Lidlar yo'qoladi", "diagram": {"type": "funnel", "title": "Yo'l", "labels": ["A", "B", "C"]}},
                  {"big": "Direktga yozing"}]
        back, desk, css = stage.layer(scenes, 5, 10)
        self.assertEqual(back.count('class="panel"'), 2)
        self.assertNotIn("%<", back)
        self.assertIn("PLANET PRINT", desk)
        self.assertIn("@keyframes pin", css)


class WatchListTests(unittest.TestCase):
    def test_only_chosen_chats_and_people_are_read(self):
        from ali import tg_account
        with tempfile.TemporaryDirectory() as d, patch.object(tg_account, "STATE", Path(d) / "c.json"):
            self.assertEqual(tg_account.reminder_sources(), {})
            self.assertEqual(tg_account.learn_all_channels(), [])  # hech narsa belgilanmagan - o'qilmaydi
            self.assertEqual(tg_account.recent_chats(reminders_only=True), "")
            tg_account.set_reminder_source(-100, "Guruh", True)
            self.assertTrue(tg_account.allows_sender(-100, 5))  # odam tanlanmagan - hamma
            self.assertTrue(tg_account.toggle_person(-100, 7, "Ali"))
            self.assertFalse(tg_account.allows_sender(-100, 5))
            self.assertTrue(tg_account.allows_sender(-100, 7))
            tg_account.set_reminder_source(-100, "Guruh", False)
            self.assertEqual(tg_account.source_people(), {})


class MusicMemoryTests(unittest.TestCase):
    def test_noise_rejected_and_library_preferred(self):
        from ali.skills import music, music_lib
        self.assertFalse(music_lib.is_music({"rms": .05, "tonal": 25, "beat": .7, "bpm": 180}))  # ko'cha shovqini
        self.assertTrue(music_lib.is_music({"rms": .05, "tonal": 170, "beat": .1, "bpm": 120}))
        with tempfile.TemporaryDirectory() as d, patch.object(music_lib, "LIB", Path(d)), \
                patch.object(music_lib, "STATE", Path(d) / "t.json"):
            (Path(d) / "energetic").mkdir()
            for name, mood in (("a", "energetic"), ("b", "calm")):
                (Path(d) / f"{name}.m4a").write_bytes(b"x")
            music_lib._save({"seen": {}, "tracks": {"a": {"file": "a.m4a", "mood": "energetic", "seconds": 30},
                                                    "b": {"file": "b.m4a", "mood": "calm", "seconds": 30}}})
            first, src = music.for_video(20, "calm")
            self.assertTrue(first.endswith("b.m4a"))
            self.assertIn("egam", src)
            # ishlatilgani keyin orqaga tushadi - bir xil trek takrorlanmaydi
            second = music_lib.choose("calm", 20)
            third = music_lib.choose("calm", 20)
            self.assertNotEqual(second, third)


class NoBackgroundMusicTests(unittest.TestCase):
    def test_video_pro_fon_musiqasi_o_chirilgan(self):
        from ali.skills import video_pro as vp
        self.assertFalse(vp.BG_MUSIC)  # egam qoidasi: videolarda faqat ovoz, musiqa yo'q


class PunishmentTests(unittest.TestCase):
    def _brain(self):
        from types import SimpleNamespace
        return SimpleNamespace(agents={"kontent": SimpleNamespace(name="Kontent", icon="✍️")}, registry={})

    def test_idle_agent_task_is_judged_strictly(self):
        from ali import ecosystem, team_hub
        with tempfile.TemporaryDirectory() as d, patch.object(ecosystem, "STATE", Path(d) / "e.json"), \
                patch.object(team_hub, "feed"):
            ecosystem.punish("kontent", "3 kun ish yo'q")
            with patch.object(team_hub, "agent_answer", return_value="Salom, qilaman"):
                lines = ecosystem.work_off(self._brain())
            self.assertIn("rad etildi", lines[0])  # oddiy gap bilan o'tib ketmaydi
            self.assertIn("punish", ecosystem._state()["agents"]["kontent"])
            long_answer = "aniq ish " * 100
            with patch.object(team_hub, "agent_answer", return_value=long_answer), \
                    patch("ali.service._ask_json", side_effect=RuntimeError("limit")):
                lines = ecosystem.work_off(self._brain())
            self.assertIn("tekshirilmadi", lines[0])  # AI band - qabul ham qilinmaydi
            with patch.object(team_hub, "agent_answer", return_value=long_answer), \
                    patch("ali.service._ask_json", return_value={"score": 5, "critique": "suv"}):
                ecosystem.work_off(self._brain())
                lines = ecosystem.work_off(self._brain())
            self.assertIn("o'tmadi", lines[0])
            self.assertEqual(ecosystem._state()["agents"]["kontent"]["strikes"], 2)
            with patch.object(team_hub, "agent_answer", return_value=long_answer), \
                    patch("ali.service._ask_json", return_value={"score": 9, "critique": ""}):
                lines = ecosystem.work_off(self._brain())
            self.assertIn("qabul qilindi", lines[0])
            self.assertNotIn("punish", ecosystem._state()["agents"]["kontent"])

    def test_video_idea_stays_on_topic_without_ai(self):
        topic = "Lidlar nega arzon lekin sotuv yo'q: lid sifati past, javob kech berilyapti, taklif aniq emas"
        with patch("ali.service._ask_json", side_effect=RuntimeError("limit")):
            got, src = daily_video.idea("x", topic)
        self.assertEqual(src, "bilim")
        self.assertIn("Lidlar", got["title"])
        self.assertGreaterEqual(len(got["scenes"]), 3)


class VideoOrderRoutingTests(unittest.TestCase):
    def test_orders_reach_the_queue_not_the_agent(self):
        started = []
        with patch.object(daily_video, "run", side_effect=lambda slot, notify, topic: started.append(slot)), \
                patch.object(daily_video.threading, "Thread") as th:
            th.side_effect = lambda target, **kw: unittest.mock.MagicMock(start=target)
            note = daily_video.handle_text("Жазони отаб срази 3та видеони килиб каналга ташлаб кой", print)
        self.assertIn("3 ta video", note)
        self.assertEqual(len(started), 3)
        self.assertEqual(daily_video._jobs["active"], 0)

    def test_status_and_other_text(self):
        self.assertIn("video", daily_video.handle_text("Видео келмабти нега", print).lower())
        self.assertEqual(daily_video.handle_text("Salom, bugun ishlar qanday", print), "")
        self.assertEqual(daily_video.order_count("5 ta video qil"), 5)
        self.assertEqual(daily_video.order_count("video qil"), 1)

    def test_character_without_photo_is_drawn(self):
        from ali.skills import presenter
        rig = presenter.vector_rig()
        self.assertEqual(len(rig["mouths"]), 7)
        page = daily_video.template({**daily_video.IDEAS[0], "scenes": daily_video.IDEAS[0]["scenes"]}, 20, rig)
        self.assertIn("image/svg+xml", page)
        self.assertIn("__rig", page)
        with tempfile.TemporaryDirectory() as d, patch.object(daily_video, "CHAR_DIR", Path(d)):
            self.assertIsNone(daily_video.character())


class StoryVideoTests(unittest.TestCase):
    def test_layouts_vary_and_scenes_do_not_cover_each_other(self):
        from ali import story_video
        scenes = [{"voice": f"gap {k} bu yerda", "big": "x", "layout": "full"} for k in range(6)]
        story_video.fix_layouts(scenes)
        lays = [s["layout"] for s in scenes]
        self.assertTrue(all(a != b for a, b in zip(lays, lays[1:])))  # ketma-ket takror yo'q
        self.assertTrue(any(x != "full" for x in lays))
        html, subs = story_video.page({"title": "t", "scenes": scenes}, [0, 2, 4, 6, 8, 10], [2] * 6,
                                      [(None, "")] * 6, None, lambda s, k: "<div></div>")
        import re
        self.assertIsNone(re.search(r"hold [\d.]+s [\d.]+s both", html))  # sahna oldindan ko'rinib, keyingisini yopmaydi
        self.assertIn("forwards", html)
        self.assertGreater(len(subs), 6)

    def test_fallback_script_without_ai(self):
        from ali import story_video
        got = story_video.fallback("Lid nega yo'q: javob kech, taklif zaif, auditoriya noto'g'ri")
        self.assertGreaterEqual(len(got["scenes"]), 4)
        self.assertTrue(all(s.get("image") for s in got["scenes"]))


class TeamFlowTests(unittest.TestCase):
    def test_voice_falls_back_to_local_whisper(self):
        from ali import providers
        with patch("ali.providers._gemini_transcribe", side_effect=RuntimeError("429")),                 patch("ali.providers.local_transcribe", return_value="dasturchiga ayt tugma qo'sh") as local,                 patch.object(providers.config, "gemini_api_key", "x"):
            self.assertEqual(providers.transcribe(b"ogg", "voice.ogg"), "dasturchiga ayt tugma qo'sh")
        local.assert_called_once()

    def test_oybek_is_montajchi_and_plan_is_applied(self):
        from types import SimpleNamespace
        from ali import story_video, team_hub
        agents = {"video_montajchi": SimpleNamespace(key="video_montajchi", name="Video montajchi", icon="🎬"),
                  "kontent": SimpleNamespace(key="kontent", name="Kontent", icon="✍️")}
        self.assertEqual(team_hub.addressed("Oybek, Sevaraning ssenariysini ol", agents), "video_montajchi")
        data = {"scenes": [{"voice": "a", "layout": "full"}, {"voice": "b", "layout": "full"}]}
        plan = {"scenes": [{"image": "wide establishing shot of a dark street with shops", "layout": "host_left",
                            "move": "pan_left", "transition": "zoom"}, {"layout": "full", "move": "zoom_in"}],
                "mood": "calm", "notes": "subtitr katta"}
        with patch("ali.service._ask_json", return_value=plan):
            notes, src = story_video.montage_plan(data, [])
        self.assertEqual(src, "AI")
        self.assertEqual(data["scenes"][0]["move"], "kb_left")
        self.assertEqual(data["scenes"][0]["transition"], "t_zoom")
        self.assertEqual(data["mood"], "calm")


class VoiceFixAndCouncilTests(unittest.TestCase):
    def test_voice_corrections_are_learned_and_applied(self):
        from ali import voice_fixes
        with tempfile.TemporaryDirectory() as d, patch.object(voice_fixes, "FILE", Path(d) / "v.json"):
            pairs = voice_fixes.learn("Sevar es senari yasun, aybeik mantash kılsun",
                                      "Sevara ssenariy yozsin, Oybek montaj qilsin")
            self.assertIn(("aybeik", "Oybek"), [(a.lower(), b) for a, b in pairs])
            self.assertEqual(voice_fixes.apply("aybeik bugun keladi"), "Oybek bugun keladi")
            self.assertIn("Oybek", voice_fixes.hint())

    def test_all_agents_take_part_in_council(self):
        from types import SimpleNamespace
        from ali import team_hub
        agents = {k: SimpleNamespace(key=k, name=k, icon="•") for k in ("kontent", "dasturchi", "huquqshunos", "18-agent")}
        asked = []
        with patch.object(team_hub, "post"), patch.object(team_hub, "touch"):
            team_hub.council("Yangi xizmat narxi qancha bo'lsin?", agents,
                             ask=lambda key, text: asked.append(key) or "fikrim bor")
        self.assertEqual(sorted(k for k in asked if k), ["dasturchi", "huquqshunos", "kontent"])


class RemoteStreamTests(unittest.TestCase):
    def test_stream_sends_length_prefixed_frames(self):
        import struct
        from fastapi.testclient import TestClient
        import runtime
        frames = iter([b"\xff\xd8one", b"\xff\xd8one", b"\xff\xd8two"])
        with patch.object(runtime, "remote_allowed", return_value=True), \
                patch("ali.remote_pc.frame", side_effect=lambda w, q: next(frames)), \
                patch("starlette.requests.Request.is_disconnected", side_effect=[False, False, False, True]):
            body = TestClient(runtime.app).get("/api/remote/stream?fps=20").content
        n = struct.unpack(">I", body[:4])[0]
        self.assertEqual(body[4:4 + n], b"\xff\xd8one")
        self.assertIn(b"two", body)
        self.assertEqual(body.count(b"one"), 1)  # o'zgarmagan kadr qayta yuborilmaydi


class AgentActTests(unittest.TestCase):
    def test_agent_runs_its_own_tool_without_api(self):
        from types import SimpleNamespace
        from ali import service
        from ali.skills import Skill
        made = []
        tool = Skill(name="make_pdf", description="PDF yasaydi", params={"title": {"type": "string"}}, required=["title"],
                     func=lambda title: made.append(title) or "PDF tayyor. Fayl javob bilan birga yuboriladi.")
        agent = SimpleNamespace(key="dizayner", name="Dizayner", icon="🎨", tools=["make_pdf", "web_search"])
        answers = iter([{"tool": "make_pdf"}, {"title": "RAVON TRAVEL"}])
        with patch.dict(service.brain.registry, {"make_pdf": tool}),                 patch.object(service, "agent_system", return_value="sen dizayner"),                 patch.object(service, "_ask_json", side_effect=lambda *a, **k: next(answers)):
            out = service.agent_act("RAVON TRAVEL brendbukini PDF qilib ber", agent, [])
        self.assertEqual(made, ["RAVON TRAVEL"])
        self.assertEqual(out, "PDF tayyor.")
        self.assertIsNone(service.agent_act("salom, ishlar qalay", agent, []))  # oddiy gap - vosita yo'q


class OwnKnowledgeTests(unittest.TestCase):
    def test_when_ai_is_out_agents_answer_from_knowledge_without_waiting(self):
        from ali import ai_status, team_hub
        calls = []
        with patch.object(ai_status, "PAUSE", 600),                 patch("ali.providers.chat", side_effect=lambda *a, **k: calls.append(1) or (_ for _ in ()).throw(RuntimeError("429"))),                 patch("ali.service.knowledge_answer", return_value="📚 o'z bilimidan"):
            ai_status.up()
            self.assertEqual(team_hub.agent_answer("kontent", "hook qanday?", []), "📚 o'z bilimidan")
            self.assertTrue(ai_status.is_down())
            self.assertEqual(team_hub.agent_answer("kontent", "yana savol", []), "📚 o'z bilimidan")
            self.assertEqual(len(calls), 1)  # ikkinchi safar AI kutilmadi
            ai_status.up()


class ChatImportTests(unittest.TestCase):
    def test_parses_chatgpt_and_claude_exports(self):
        gpt = [{"title": "Pilon narxi", "mapping": {
            "a": {"message": {"author": {"role": "user"}, "content": {"parts": ["Pilon qancha turadi?"]}, "create_time": 1}},
            "b": {"message": {"author": {"role": "assistant"}, "content": {"parts": ["Taxminan 8-15 mln so'm."]},
                              "create_time": 2}},
            "c": {"message": None}}}]
        claude = [{"name": "Reels hook", "chat_messages": [{"sender": "human", "text": "Hook yoz"},
                                                           {"sender": "assistant", "text": "Tunda ham kunduzdek!"}]}]
        with tempfile.TemporaryDirectory() as d:
            z = Path(d) / "export.zip"
            with zipfile.ZipFile(z, "w") as f:
                f.writestr("conversations.json", json.dumps(gpt))
            convs = chat_import.load(z)
            self.assertEqual(convs[0]["source"], "ChatGPT")
            self.assertEqual([r for r, _ in convs[0]["messages"]], ["user", "assistant"])
            self.assertIn("8-15 mln", chat_import.digest(convs[0]))
            j = Path(d) / "conversations.json"
            j.write_text(json.dumps(claude), encoding="utf-8")
            self.assertEqual(chat_import.load(j)[0]["source"], "Claude")


if __name__ == "__main__":
    unittest.main()
