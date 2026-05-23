import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from models import SubtitleEntry
from alignment import align_subtitles_to_transcript
from config import load_dotenv, resolve_paths
from srt_parser import parse_srt
from fix_srt_timing import process_from_env
from logging_utils import close_logging


class FixSrtTimingTests(unittest.TestCase):
    def test_process_file_resolves_correct_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media = root / "media"
            media.mkdir()
            (media / "demo.mp4").write_bytes(b"")
            (media / "demo.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nHi\n", encoding="utf-8")
            env = root / ".env"
            env.write_text("PROCESS_FOLDER=media\nPROCESS_FILE=demo\n", encoding="utf-8")

            settings = load_dotenv(env)
            video, subtitle = resolve_paths(settings, repository_root=root)

            self.assertEqual(video, media / "demo.mp4")
            self.assertEqual(subtitle, media / "demo.srt")

    def test_align_subtitles_adjusts_timings_to_match_transcript(self) -> None:
        entries = parse_srt(
            "1\n00:00:00,000 --> 00:00:01,000\nHello there\n\n"
            "2\n00:00:01,100 --> 00:00:02,100\nGeneral Kenobi\n"
        )
        transcript = [
            {"start": 5.0, "end": 6.0, "text": "General Kenobi"},
            {"start": 2.0, "end": 3.0, "text": "Hello there"},
        ]

        aligned = align_subtitles_to_transcript(entries, transcript)

        self.assertEqual((aligned[0].start, aligned[0].end), (2.0, 3.0))
        self.assertEqual((aligned[1].start, aligned[1].end), (5.0, 6.0))

    def test_process_from_env_updates_srt_file(self) -> None:
        # Mock the whisper module at import time
        mock_whisper = MagicMock()
        mock_whisper.load_model.return_value.transcribe.return_value = {
            "segments": [{"start": 4.0, "end": 5.0, "text": "Shift me"}]
        }
        
        with patch.dict('sys.modules', {'whisper': mock_whisper}):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "clip.mp4").write_bytes(b"")
                srt = root / "clip.srt"
                srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nShift me\n", encoding="utf-8")
                env = root / ".env"
                env.write_text("PROCESS_FILE=clip\n", encoding="utf-8")

                try:
                    process_from_env(env)
                finally:
                    close_logging()

                updated = srt.read_text(encoding="utf-8")
                self.assertIn("00:00:04,000 --> 00:00:05,000", updated)

    def test_process_from_env_rejects_invalid_alignment_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "clip.mp4").write_bytes(b"")
            (root / "clip.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nHi\n", encoding="utf-8")
            env = root / ".env"
            env.write_text("PROCESS_FILE=clip\nALIGNMENT_SIMILARITY_THRESHOLD=abc\n", encoding="utf-8")

            try:
                with self.assertRaisesRegex(
                    ValueError, "ALIGNMENT_SIMILARITY_THRESHOLD must be a valid float value."
                ):
                    process_from_env(env)
            finally:
                close_logging()


if __name__ == "__main__":
    unittest.main()
