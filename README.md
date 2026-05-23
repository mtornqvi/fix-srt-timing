# fix-srt-timing

Fix subtitle timing for an `.srt` file by transcribing the matching `.mp4` file and aligning subtitle timestamps to the transcript.

## Setup

### Prerequisites

Install ffmpeg (required for audio extraction):

**Windows (Chocolatey):**
```bash
choco install ffmpeg
```

**Windows (Scoop):**
```bash
scoop install ffmpeg
```

**Linux:**
```bash
sudo apt install ffmpeg  # Debian/Ubuntu
sudo yum install ffmpeg  # CentOS/RHEL
```

**macOS:**
```bash
brew install ffmpeg
```

### Python Environment

Create and activate a virtual environment:

```bash
# Create virtual environment
python -m venv venv

# Activate (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# Activate (Windows Command Prompt)
venv\Scripts\activate.bat

# Activate (Linux/macOS)
source venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

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

The script:
1. Checks for an existing transcript file (`.transcript.json`) next to the video file
2. If found, reuses it to save time; otherwise transcribes the video using Whisper
3. Saves the transcript permanently in the same folder as the video for future use
4. Aligns subtitle timings with the transcript
5. Creates a timestamped backup of the original `.srt` file (e.g., `video.backup.20240523_143022.srt`)
6. Updates the configured `.srt` file in place
7. Generates a detailed log file named after the video (e.g., `video.log`)

### Output Files

The script creates several files in the target folder:
- **`video.transcript.json`** - Cached transcription for future runs
- **`video.backup.YYYYMMDD_HHMMSS.srt`** - Backup of original subtitles
- **`video.log`** - Detailed processing log with:
  - Configuration settings used
  - Each subtitle's alignment process
  - Similarity scores for transcript matching
  - Timing adjustments made
  - Final statistics

**Note:** Console output is minimal. Check the log file for detailed information about the alignment process.

## Dependencies

The script requires `openai-whisper` for audio transcription. Install via:

```bash
pip install -r requirements.txt
```

Alternatively, you can use the `whisper` CLI if already installed.
