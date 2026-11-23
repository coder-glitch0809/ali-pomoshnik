import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import test_runtime
from ali import youtube_video as video


class YouTubeScheduleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state_patch = patch.object(video, "STATE", Path(self.temp.name) / "youtube.json")
        self.state_patch.start()
        self.addCleanup(self.state_patch.stop)
        video._scheduled.clear()
        self.addCleanup(video._scheduled.clear)

    def test_timezone_slots_and_pending_deduplication(self):
        with patch.object(video.threading, "Thread") as thread:
            video.tick(Mock(), datetime(2026, 11, 19, 4, 59, tzinfo=timezone.utc))
            thread.assert_not_called()
            video.tick(Mock(), datetime(2026, 11, 19, 5, 0, tzinfo=timezone.utc))
            self.assertEqual(thread.call_count, 1)
            video.tick(Mock(), datetime(2026, 11, 19, 8, 0, tzinfo=timezone.utc))
            self.assertEqual(thread.call_count, 2)
            video.tick(Mock(), datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc))
            self.assertEqual(thread.call_count, 3)
            video.tick(Mock(), datetime(2026, 11, 19, 13, 0, tzinfo=timezone.utc))
            self.assertEqual(thread.call_count, 4)
            self.assertTrue(thread.call_args.kwargs['kwargs']['shorts'])
            video.tick(Mock(), datetime(2026, 11, 19, 13, 1, tzinfo=timezone.utc))
            self.assertEqual(thread.call_count, 4)
            self.assertNotIn("done", video._state())

    def test_failed_job_is_retryable_and_success_is_not_repeated(self):
        key = "2026-11-19 10:00"
        with patch.object(video, "make", side_effect=RuntimeError("network")):
            video.run("10:00", Mock(), key=key)
        state = video._state()
        self.assertNotIn(key, state.get("done", {}))
        self.assertIn(key, state["retry"])
        before_retry = datetime(2026, 11, 19, 10, 0, tzinfo=video.TZ)
        video._save({"retry": {key: before_retry.timestamp() + 900}})
        with patch.object(video.threading, "Thread") as thread:
            video.tick(Mock(), before_retry)
            thread.assert_not_called()
        output = Path(self.temp.name) / "final.mp4"
        output.write_bytes(b"validated fixture")
        result = {"path": str(output), "idea": {"title": "New", "scenes": [{"voice": "Unique"}]},
                  "sources": "test", "duration": 30}
        with patch.object(video, "make", return_value=result) as make, \
                patch.object(video, "quality_issues", return_value=[]), \
                patch("ali.studio_flow.send_files") as send:
            video.run("10:00", Mock(), key=key)
            video.run("10:00", Mock(), key=key)
            make.assert_called_once()
            send.assert_called_once()
        self.assertEqual(video._state()["done"][key], str(output))
        self.assertEqual(len(video._state()["history"]), 1)

    def test_quality_gate_rejects_portrait_or_missing_audio(self):
        with patch("ali.skills.video_edit.info", return_value={"width": 1080, "height": 1920,
                "fps": 30, "duration": 30, "audio": False}):
            self.assertEqual(len(video.quality_issues("fixture", 40)), 3)
        with patch("ali.skills.video_edit.info", return_value={"width": 1920, "height": 1080,
                "fps": 30, "duration": 30, "audio": True}):
            self.assertEqual(video.quality_issues("fixture", 30), [])

    def test_quality_failure_never_completes_slot(self):
        with patch.object(video, "make", return_value={"path": "bad.mp4"}), \
                patch.object(video, "quality_issues", return_value=["bad export"]), \
                patch("ali.studio_flow.send_files") as send:
            video.run("13:00", Mock(), key="2026-11-19 13:00")
            send.assert_not_called()
        self.assertFalse(video._state().get("history"))
        self.assertFalse(video._state().get("done"))

    def test_make_uses_landscape_render_and_mux_without_reels_postprocess(self):
        from ali import outbox
        scene = {"voice": "Test narration", "big": "Test", "layout": "host_center"}
        data = {"title": "Test", "scenes": [scene]}
        output = Path(self.temp.name) / "export.mp4"

        def mux(args):
            Path(args[-1]).write_bytes(b"mux output")

        with patch("ali.youtube_content.script", return_value=data), \
                patch("ali.daily_video._ready", return_value=[]), \
                patch("ali.daily_video.character", return_value=None), \
                patch("ali.video_variety.direction"), patch("ali.video_variety.select_media", return_value=None), \
                patch("ali.story_video.voices", return_value=(Path("voice.wav"), [30])), \
                patch("ali.video_variety.sync_studio"), \
                patch("ali.story_video.images", return_value=[(Path("photo.jpg"), "image")]) as images, \
                patch("ali.youtube_render.page", return_value=("html", [])), \
                patch("ali.skills.presenter.vector_rig", return_value={}), \
                patch("ali.skills.talking_head.levels", return_value=[]), \
                patch("ali.skills.talking_head.blinks", return_value=[]), \
                patch("ali.story_video.host_frames", return_value=[]), \
                patch("ali.story_video.render") as render, \
                patch("ali.skills.video_edit._run", side_effect=mux) as ffmpeg, \
                patch.object(video, "quality_issues", return_value=[]), \
                patch.object(outbox, "new_path", return_value=output), patch.object(outbox, "register"):
            result = video.make()
        self.assertEqual(images.call_args.kwargs["size"], (1920, 1080))
        self.assertEqual(render.call_args.kwargs["viewport"], (1920, 1080))
        self.assertIn("+faststart", ffmpeg.call_args.args[0])
        self.assertIn("48000", ffmpeg.call_args.args[0])
        self.assertEqual(Path(result["path"]).read_bytes(), b"mux output")
        metadata = json.loads(output.with_suffix('.json').read_text(encoding='utf-8'))
        self.assertEqual(metadata['duration'], 30)
        self.assertEqual(metadata['chapters'][0]['start'], 0)


if __name__ == "__main__":
    unittest.main()
