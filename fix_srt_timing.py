from __future__ import annotations

import json
import re
import subprocess
import tempfile
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path


@dataclass
class SubtitleEntry:
    index: int
    start: float
    end: float
    text: str


def load_dotenv(path: Path) -> dict[str, str]:
    settings: dict[str, str] = {}
    if not path.exists():
        return settings
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        key, sep, value = line.partition("=")
        if not sep:
            continue
        settings[key.strip()] = value.strip().strip('"').strip("'")
    return settings


def parse_timestamp(value: str) -> float:
    hours, minutes, seconds_ms = value.split(":")
    seconds, millis = seconds_ms.split(",")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000


def format_timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    total_millis = int(round(seconds * 1000))
    hours = total_millis // 3_600_000
    total_millis %= 3_600_000
    minutes = total_millis // 60_000
    total_millis %= 60_000
    secs = total_millis // 1000
    millis = total_millis % 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


TIMING_PATTERN = re.compile(
    r"(?P<start>\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(?P<end>\d{2}:\d{2}:\d{2},\d{3})"
)
SIMILARITY_THRESHOLD = 0.6
MIN_SUBTITLE_DURATION_SECONDS = 0.5


def parse_srt(text: str) -> list[SubtitleEntry]:
    entries: list[SubtitleEntry] = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [line.strip("\ufeff") for line in block.splitlines() if line.strip()]
        if len(lines) < 2:
            continue
        try:
            index = int(lines[0])
            timing_line = lines[1]
            content_start = 2
        except ValueError:
            index = len(entries) + 1
            timing_line = lines[0]
            content_start = 1
        match = TIMING_PATTERN.search(timing_line)
        if not match:
            continue
        entries.append(
            SubtitleEntry(
                index=index,
                start=parse_timestamp(match.group("start")),
                end=parse_timestamp(match.group("end")),
                text="\n".join(lines[content_start:]),
            )
        )
    return entries


def serialize_srt(entries: list[SubtitleEntry]) -> str:
    blocks = []
    for position, entry in enumerate(entries, start=1):
        blocks.append(
            "\n".join(
                [
                    str(position),
                    f"{format_timestamp(entry.start)} --> {format_timestamp(entry.end)}",
                    entry.text,
                ]
            )
        )
    return "\n\n".join(blocks) + "\n"


def _normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", value.lower())).strip()


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _normalized_text(a), _normalized_text(b)).ratio()


def align_subtitles_to_transcript(
    entries: list[SubtitleEntry],
    transcript_segments: list[dict[str, object]],
    similarity_threshold: float = SIMILARITY_THRESHOLD,
    min_duration_seconds: float = MIN_SUBTITLE_DURATION_SECONDS,
) -> list[SubtitleEntry]:
    aligned: list[SubtitleEntry] = []
    previous_end = 0.0
    for entry in entries:
        best = None
        best_score = 0.0
        for segment in transcript_segments:
            text = str(segment.get("text", "")).strip()
            if not text:
                continue
            score = _similarity(entry.text, text)
            if score > best_score:
                best_score = score
                best = segment

        if best and best_score > similarity_threshold:
            start = float(best.get("start", entry.start))
            end = float(best.get("end", entry.end))
        else:
            start = entry.start
            end = entry.end

        start = max(start, previous_end)
        end = max(end, start + min_duration_seconds)
        previous_end = end
        aligned.append(SubtitleEntry(index=entry.index, start=start, end=end, text=entry.text))
    return aligned


def transcribe_video(video_file: Path, model_size: str = "base") -> list[dict[str, object]]:
    import_failure: Exception | None = None
    whisper_failure: Exception | None = None
    try:
        import whisper  # type: ignore
    except ImportError as exc:
        import_failure = exc
    else:
        try:
            model = whisper.load_model(model_size)
            result = model.transcribe(str(video_file), verbose=False)
            return result.get("segments", [])
        except Exception as exc:
            whisper_failure = exc

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

        output_file = Path(temp_dir) / f"{video_file.stem}.json"
        if not output_file.exists():
            raise RuntimeError("Whisper CLI did not produce a transcript JSON file.")
        transcript = json.loads(output_file.read_text(encoding="utf-8"))
        return transcript.get("segments", [])


def resolve_paths(settings: dict[str, str], repository_root: Path) -> tuple[Path, Path]:
    folder = settings.get("PROCESS_FOLDER", ".")
    process_dir = (repository_root / folder).resolve()
    stem = settings.get("PROCESS_FILE")
    video_name = settings.get("VIDEO_FILE")
    subtitle_name = settings.get("SUBTITLE_FILE")
    if stem:
        video_name = video_name or f"{stem}.mp4"
        subtitle_name = subtitle_name or f"{stem}.srt"
    if not video_name or not subtitle_name:
        raise ValueError("Set PROCESS_FILE or both VIDEO_FILE and SUBTITLE_FILE in .env")

    video_path = (process_dir / video_name).resolve()
    subtitle_path = (process_dir / subtitle_name).resolve()
    if video_path.suffix.lower() != ".mp4":
        raise ValueError(f"Expected .mp4 video file, got: {video_path.name}")
    if subtitle_path.suffix.lower() != ".srt":
        raise ValueError(f"Expected .srt subtitle file, got: {subtitle_path.name}")
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")
    if not subtitle_path.exists():
        raise FileNotFoundError(f"Subtitle file not found: {subtitle_path}")
    return video_path, subtitle_path


def process_from_env(env_path: Path = Path(".env")) -> Path:
    repository_root = env_path.resolve().parent
    settings = load_dotenv(env_path)
    video_path, subtitle_path = resolve_paths(settings, repository_root=repository_root)
    model_size = settings.get("WHISPER_MODEL", "base")
    similarity_threshold = float(settings.get("ALIGNMENT_SIMILARITY_THRESHOLD", SIMILARITY_THRESHOLD))
    min_duration_seconds = float(
        settings.get("MIN_SUBTITLE_DURATION_SECONDS", MIN_SUBTITLE_DURATION_SECONDS)
    )
    transcript_segments = transcribe_video(video_path, model_size=model_size)
    entries = parse_srt(subtitle_path.read_text(encoding="utf-8"))
    adjusted = align_subtitles_to_transcript(
        entries,
        transcript_segments,
        similarity_threshold=similarity_threshold,
        min_duration_seconds=min_duration_seconds,
    )
    subtitle_path.write_text(serialize_srt(adjusted), encoding="utf-8")
    return subtitle_path


if __name__ == "__main__":
    updated_file = process_from_env()
    print(f"Updated subtitle timings in: {updated_file}")
