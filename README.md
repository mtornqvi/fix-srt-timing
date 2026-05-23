# fix-srt-timing

Fix subtitle timing for an `.srt` file by transcribing the matching `.mp4` file and aligning subtitle timestamps to the transcript.

## Configuration

Create a `.env` file in the repository root:

```env
PROCESS_FOLDER=media
PROCESS_FILE=my_video
# or set files directly:
# VIDEO_FILE=my_video.mp4
# SUBTITLE_FILE=my_video.srt
# optional:
# WHISPER_MODEL=base
# ALIGNMENT_SIMILARITY_THRESHOLD=0.6
# MIN_SUBTITLE_DURATION_SECONDS=0.5
```

- `PROCESS_FOLDER` decides which folder to process.
- `PROCESS_FILE` is the shared filename stem (`.mp4` and `.srt` are inferred).
- Alternatively, set `VIDEO_FILE` and `SUBTITLE_FILE` explicitly.

## Run

```bash
python fix_srt_timing.py
```

The script updates the configured `.srt` file in place.

## Transcription backend

The script first tries Python `openai-whisper`, then the `whisper` CLI.
Install one of them before running:

```bash
pip install openai-whisper
```
