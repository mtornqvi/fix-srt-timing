"""Video transcription using OpenAI Whisper."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from logging_utils import log


def transcribe_video(video_file: Path, model_size: str = "base") -> list[dict[str, object]]:
    """Transcribe video audio to text using Whisper, with caching support."""
    log(f"\n[TRANSCRIBE] Starting transcription process")
    log(f"[TRANSCRIBE] Video file: {video_file}")
    log(f"[TRANSCRIBE] Model size: {model_size}")
    
    # Check if transcript already exists
    transcript_file = video_file.with_suffix(".transcript.json")
    if transcript_file.exists():
        log(f"[TRANSCRIBE] Found existing transcript: {transcript_file}")
        log(f"[TRANSCRIBE] Skipping transcription to save time")
        transcript = json.loads(transcript_file.read_text(encoding="utf-8"))
        segments = transcript.get("segments", [])
        log(f"[TRANSCRIBE] Loaded {len(segments)} transcript segments from cache")
        return segments
    
    log(f"[TRANSCRIBE] No existing transcript found, creating new one...")
    log(f"[TRANSCRIBE] This may take several minutes depending on video length")
    import_failure: Exception | None = None
    whisper_failure: Exception | None = None
    try:
        import whisper  # type: ignore
    except ImportError as exc:
        import_failure = exc
    else:
        try:
            log(f"[TRANSCRIBE] Loading Whisper model '{model_size}'...")
            model = whisper.load_model(model_size)
            log(f"[TRANSCRIBE] Model loaded successfully")
            log(f"[TRANSCRIBE] Transcribing audio with enhanced timestamp accuracy...")
            log(f"[TRANSCRIBE] Options: fp16=False (CPU), word_timestamps=True, condition_on_previous_text=False")
            result = model.transcribe(
                str(video_file), 
                verbose=False, 
                fp16=False,
                word_timestamps=True,  # More accurate word-level timing
                condition_on_previous_text=False,  # Reduce hallucinations
            )
            segments = result.get("segments", [])
            log(f"[TRANSCRIBE] Transcription complete! Generated {len(segments)} segments")
            
            # Log segments with high no_speech_prob as warnings
            suspicious_segments = [s for s in segments if s.get("no_speech_prob", 0) > 0.5]
            if suspicious_segments:
                log(f"[TRANSCRIBE] ⚠ Warning: {len(suspicious_segments)} segments have high no-speech probability")
                log(f"[TRANSCRIBE]   These may be misdetected silence or background noise")
            
            # Save transcript to target folder
            transcript_file.write_text(
                json.dumps({"segments": segments}, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            log(f"[TRANSCRIBE] Transcript saved to: {transcript_file}")
            log(f"[TRANSCRIBE] Future runs will reuse this transcript")
            return segments
        except Exception as exc:
            whisper_failure = exc
            log(f"[TRANSCRIBE] Python whisper failed with error: {exc}")
            log(f"[TRANSCRIBE] Error type: {type(exc).__name__}")

    # Fallback to Whisper CLI
    with tempfile.TemporaryDirectory() as temp_dir:
        cmd = [
            "whisper",
            str(video_file),
            "--model",
            model_size,
            "--output_format",
            "json",
            "--output_dir",
            temp_dir,
            "--fp16",
            "False",
            "--verbose",
            "False",
            "--word_timestamps",
            "True",
            "--condition_on_previous_text",
            "False",
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            whisper_reason = f"whisper python failure: {whisper_failure}; " if whisper_failure else ""
            import_reason = f"import failure: {import_failure}; " if import_failure else ""
            raise RuntimeError(
                "Unable to transcribe video. Install openai-whisper (pip install openai-whisper) "
                "or make sure the whisper CLI is available. "
                f"{import_reason}{whisper_reason}cli failure: {exc}"
            ) from exc

        temp_transcript = Path(temp_dir) / f"{video_file.stem}.json"
        if not temp_transcript.exists():
            raise RuntimeError("Whisper CLI did not produce a transcript JSON file.")
        transcript = json.loads(temp_transcript.read_text(encoding="utf-8"))
        # Save transcript to target folder
        transcript_file.write_text(
            json.dumps(transcript, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        log(f"[TRANSCRIBE] Transcript saved to: {transcript_file}")
        log(f"[TRANSCRIBE] Future runs will reuse this transcript")
        return transcript.get("segments", [])
