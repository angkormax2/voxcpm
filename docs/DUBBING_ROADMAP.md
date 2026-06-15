# Video Dubbing Roadmap (planned)

This document describes the **next major feature** for VoxCPM: professional-style **video dubbing**, based on your requirements.

## Goal

Take a video (or audio track), produce **timed dubbed speech** where:

- Text matches what was said (ASR / transcription)
- Each **character** keeps a **consistent voice** (male/female, cloned timbre)
- The system knows **who speaks which line**
- Output respects **when to talk and when to stay silent** (dubbing timeline)

## Pipeline (high level)

```mermaid
flowchart LR
  A[Video / Audio] --> B[Extract audio]
  B --> C[ASR + word timestamps]
  C --> D[Speaker diarization]
  D --> E[Character mapping UI]
  E --> F[Voice profile per character]
  F --> G[VoxCPM2 TTS per line]
  G --> H[Align to timeline]
  H --> I[Dubbed audio / video mux]
```

### Step 1 — Extract & transcribe

- Extract audio from video (`ffmpeg`)
- Run **ASR with timestamps** (e.g. Whisper, SenseVoice) → segments: `{start, end, text, speaker_id?}`

### Step 2 — Who spoke? (diarization)

- **Speaker diarization** (pyannote, etc.) labels segments: Speaker A, B, C…
- Optional: face/speaker naming UI → map Speaker A → "Host", B → "Guest"

### Step 3 — Character + voice library

- Per character:
  - Name, gender (male/female)
  - **Saved voice profile** (reference clip from video or uploaded)
  - Default speaking style (news, calm, etc.)
- Reuse the **Voice Library** in the app (already started)

### Step 4 — Line-by-line TTS

- For each timed segment:
  - `reference_wav` = character’s saved clone
  - `target_text` = translated or corrected line (Khmer / mixed language)
  - Chain segments per character with **voice continuation** (already in `core.py`)

### Step 5 — Dubbing timeline

- Place each generated clip at `start` time on a master track
- **Silence** between lines where original had pause
- Export:
  - Mixed WAV/MP3
  - Optional SRT for subtitles
  - Optional remux with video (`ffmpeg`)

## Khmer accuracy notes

VoxCPM2 is **not primarily trained on Khmer**. For better Khmer dubbing long term:

- Fine-tune LoRA on Khmer data (`lora_ft_webui.py`)
- Fix transcript text manually before TTS (ASR errors cause wrong reads)
- Use **។** between sentences; avoid mid-word splits
- Consider external Khmer G2P / dictionary pass (future)

## What exists today in the app

| Feature | Status |
|--------|--------|
| Voice clone (reference audio) | ✅ |
| Saved voice library (reuse clones) | ✅ |
| Long text split (Khmer-aware at ។) | ✅ |
| One voice across split segments | ✅ |
| Speaking style presets | ✅ |
| Video import + diarization + timeline | 📋 Planned |

## Suggested implementation order

1. **Voice library** — save/select clones (done in app)
2. **Script editor** — import ASR JSON, edit lines per speaker
3. **Character panel** — assign voice profile + gender per speaker
4. **Batch generate** — one WAV per line, chained per character
5. **Timeline export** — pydub / ffmpeg align to video
6. **Video preview** — optional Gradio video + audio player

If you want to prioritize one step next, **Script editor + batch line TTS** is the most useful after the voice library.
