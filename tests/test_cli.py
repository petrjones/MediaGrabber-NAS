"""Optional real yt-dlp/FFmpeg integration against a local, generated fixture.

MG_TEST_YTDLP and MG_TEST_FFMPEG must point to installed executables.
No request is sent to YouTube; only loopback HTTP is used.
"""
import functools
import json
import math
import os
import struct
import subprocess
import tempfile
import threading
import unittest
import wave
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from mg_nas.domain import DEFAULTS, options
from mg_nas.engine import Engine, Interrupted


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@unittest.skipUnless(os.environ.get("MG_TEST_YTDLP") and os.environ.get("MG_TEST_FFMPEG"), "optional real CLI test: set MG_TEST_YTDLP and MG_TEST_FFMPEG")
class LocalCLITests(unittest.TestCase):
    def test_download_conversion_metadata_cover_and_interruption(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            web = root / "web"
            web.mkdir()
            with wave.open(str(web / "tone.wav"), "wb") as stream:
                stream.setparams((1, 2, 44100, 0, "NONE", "not compressed"))
                stream.writeframes(b"".join(struct.pack("<h", int(4000 * math.sin(i * 440 * 2 * math.pi / 44100))) for i in range(44100 * 3)))
            ffmpeg = Path(os.environ["MG_TEST_FFMPEG"]).resolve()
            subprocess.run([str(ffmpeg), "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=blue:s=300x300", "-frames:v", "1", str(web/"cover.jpg")], check=True, capture_output=True)
            subprocess.run([str(ffmpeg), "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=10", "-i", str(web/"tone.wav"), "-t", "3", "-c:v", "mpeg4", "-c:a", "aac", str(web/"clip.mp4")], check=True, capture_output=True)
            server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(web)))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                origin = "http://127.0.0.1:" + str(server.server_port)
                info = {"id": "offline-fixture", "title": "Offline fixture", "artist": "PJSoft test", "album": "Offline album",
                        "url": origin + "/tone.wav", "ext": "wav", "vcodec": "none", "acodec": "pcm_s16le",
                        "duration": 3, "thumbnail": origin + "/cover.jpg", "webpage_url": origin + "/fixture"}
                fixture = root / "info.json"
                fixture.write_text(json.dumps(info), "utf-8")

                class FixtureEngine(Engine):
                    def _run(self, *args, **kwargs):
                        code, text = super()._run(*args, **kwargs)
                        if code:
                            print(text)
                        return code, text

                    def download_args(self, *args, **kwargs):
                        result = super().download_args(*args, **kwargs)
                        return [*result[:-2], "--load-info-json", str(fixture)]

                engine = FixtureEngine(root, os.environ["MG_TEST_YTDLP"], str(ffmpeg))
                opts = options({"quality": "mp3_192"}, root)
                result = engine.download({"url": "unused fixture"}, opts, root/"100% offline", DEFAULTS, lambda: "", lambda p: None)
                path = Path(result["paths"][0])
                self.assertEqual(path.suffix, ".mp3")
                ffprobe = ffmpeg.with_name("ffprobe" + ffmpeg.suffix)
                report = json.loads(subprocess.run([str(ffprobe), "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)], check=True, capture_output=True, text=True).stdout)
                self.assertEqual(report["format"]["tags"].get("artist"), "PJSoft test")
                self.assertTrue(any(s.get("disposition", {}).get("attached_pic") == 1 for s in report["streams"]))
                audio = next(s for s in report["streams"] if s["codec_type"] == "audio")
                self.assertEqual(audio["codec_name"], "mp3")
                self.assertTrue(185000 <= int(audio["bit_rate"]) <= 195000)
                try:
                    import mutagen
                except ImportError:
                    pass
                else:
                    self.assertEqual(path.read_bytes()[:4], b"ID3\x03", "MP3 tags must use ID3v2.3 for older players")
                video_info = dict(info, url=origin+"/clip.mp4", ext="mp4", vcodec="mpeg4", acodec="aac", width=320, height=180)
                fixture.write_text(json.dumps(video_info), "utf-8")
                video = engine.download({"url": "unused fixture"}, options({"mode": "video", "quality": "1080"}, root), root/"offline-video", DEFAULTS, lambda: "", lambda p: None)
                video_path = Path(video["paths"][0])
                self.assertEqual(video_path.suffix, ".mkv")
                probe = json.loads(subprocess.run([str(ffprobe), "-v", "error", "-show_streams", "-of", "json", str(video_path)], check=True, capture_output=True, text=True).stdout)
                self.assertTrue({"video", "audio"}.issubset({s["codec_type"] for s in probe["streams"]}))
                fixture.write_text(json.dumps(dict(info, upload_date="20200101")), "utf-8")
                filtered = engine.download({"url": "unused fixture"}, opts, root/"filtered-old", DEFAULTS, lambda: "", lambda p: None, date_after="2026-11-01")
                self.assertTrue(filtered["filtered"])
                self.assertEqual(filtered["paths"], [])
                self.assertFalse((root/"filtered-old.mp3").exists())
                with self.assertRaises(Interrupted):
                    engine._run(["--version"], stop=lambda: "paused")
                self.assertEqual(list((root/"process").glob("*.log")), [])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(3)


if __name__ == "__main__":
    unittest.main()
