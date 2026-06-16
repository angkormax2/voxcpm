from voxcpm.cuda_env import ensure_cuda_paths

ensure_cuda_paths()

import sys

if sys.platform == "win32":
    import os

    os.environ.setdefault("PYTHONUTF8", "1")

import torch

# Import VoxCPM core before numpy/soundfile/uvicorn — on Windows, reversing
# this order can leave torch.cuda.is_available() stuck on False.
from app import VoxCPMDemo, DEFAULT_MODEL_ID, ProcessLog

from license_manager import require_valid_license, revalidate_online_license

import os
import io
import uuid
import base64
import json
import re
import queue
import threading
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf
import uvicorn
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from speaking_styles import SPEAKING_STYLE_CHOICES, get_style_control
from voxcpm.cuda_env import describe_cuda_status
from voice_profiles import (
    GENDER_OPTIONS,
    SPEAKER_GENDER_OPTIONS,
    list_profiles,
    get_profile,
    get_profile_audio_path,
    save_profile,
    delete_profile,
    resolve_auto_voice,
    merge_speaker_control,
)

if torch.cuda.is_available():
    torch.cuda.init()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        access = require_valid_license()
    except RuntimeError as exc:
        print("================================================================")
        print("  LICENSE ERROR:", exc)
        print("  Enter a license in the launcher before Open UI or Start Studio.")
        print("================================================================")
        raise
    print(f"  {access.message}")
    demo.refresh_device()
    cuda = describe_cuda_status()
    print("================================================================")
    print(f"  PyTorch CUDA Status: {cuda['cuda_available']}")
    print(f"  PyTorch Version: {cuda['pytorch_version']}")
    if cuda.get("device_name"):
        print(f"  GPU: {cuda['device_name']}")
    if cuda.get("cuda_error"):
        print(f"  CUDA Error: {cuda['cuda_error']}")
    print(f"  VoxCPM is using DEVICE: {demo.device}")
    print("================================================================")
    if demo.device == "cpu":
        print("WARNING: PyTorch is running on CPU. Synthesis will be very slow.")
        print("Tip: launch with run.bat or use .venv\\Scripts\\python.exe api.py directly.")
    else:
        print("API is ready! Model loads on GPU when you send your first synthesis request.")
    yield


from studio_branding import STUDIO_NAME

app = FastAPI(title=STUDIO_NAME, version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

demo = VoxCPMDemo(model_id=DEFAULT_MODEL_ID)
OUTPUT_DIR = Path("data") / "generated_audio"
MAX_TTS_CHUNK_CHARS = 260
MAX_TTS_CHUNKS = 80
CHUNK_PAUSE_SECONDS = 0.12
AUTO_FALLBACK_STYLE_BY_SPEAKER = {
    "male": "neutral",
    "female": "neutral",
    "neutral": "neutral",
    "child": "child",
}
VOICE_CONSISTENCY_DIRECTIVE = (
    "Keep the exact same speaker identity and vocal timbre across all sentences and chunks. "
    "Do not switch to another voice model, accent, or persona mid-output."
)


def _ensure_output_dir() -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR


def _list_output_files() -> list[dict[str, object]]:
    out = _ensure_output_dir()
    files = []
    for p in sorted(out.glob("*.wav"), key=lambda x: x.stat().st_mtime, reverse=True):
        st = p.stat()
        files.append(
            {
                "name": p.name,
                "size_bytes": st.st_size,
                "modified_at": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
            }
        )
    return files


def _split_long_text_for_tts(text: str, max_chars: int = MAX_TTS_CHUNK_CHARS) -> list[str]:
    cleaned = " ".join((text or "").split()).strip()
    if not cleaned:
        return []
    if len(cleaned) <= max_chars:
        return [cleaned]

    # Split by sentence boundaries first to preserve natural prosody.
    sentence_parts = [s.strip() for s in re.split(r"(?<=[.!?။៕])\s+|(?<=[.!?])\n+", cleaned) if s.strip()]
    if not sentence_parts:
        sentence_parts = [cleaned]

    chunks: list[str] = []
    current = ""

    def flush_current() -> None:
        nonlocal current
        if current.strip():
            chunks.append(current.strip())
        current = ""

    for sentence in sentence_parts:
        if len(sentence) > max_chars:
            words = sentence.split()
            piece = ""
            for word in words:
                candidate = f"{piece} {word}".strip()
                if len(candidate) <= max_chars:
                    piece = candidate
                else:
                    if piece:
                        chunks.append(piece.strip())
                    piece = word
            if piece:
                if current and len(f"{current} {piece}") <= max_chars:
                    current = f"{current} {piece}".strip()
                else:
                    flush_current()
                    current = piece
            continue

        candidate = f"{current} {sentence}".strip()
        if len(candidate) <= max_chars:
            current = candidate
        else:
            flush_current()
            current = sentence

    flush_current()
    return chunks


def _auto_fallback_voice_for_speaker(speaker_gender: str) -> str:
    key = (speaker_gender or "").strip().lower()
    style = AUTO_FALLBACK_STYLE_BY_SPEAKER.get(key, "neutral")
    return f"preset:{style}"


def _enforce_voice_consistency(control_instruction: str) -> str:
    base = (control_instruction or "").strip()
    lower = base.lower()
    if "same speaker identity" in lower or "same voice" in lower:
        return base
    if base:
        return f"{base}. {VOICE_CONSISTENCY_DIRECTIVE}"
    return VOICE_CONSISTENCY_DIRECTIVE


def _sanitize_text_for_tts(text: str) -> tuple[str, bool]:
    raw = (text or "").strip()
    if not raw:
        return "", False
    # Never let Khmer punctuation sign "៖" be spoken literally.
    sanitized = raw.replace("៖", " ")
    sanitized = " ".join(sanitized.split())
    return sanitized, sanitized != raw


class GenerateRequest(BaseModel):
    text: str
    voice_select: str = "none"
    control_instruction: str = ""
    cfg_value: float = 2.0
    normalize: bool = True
    denoise: bool = True
    timesteps: int = 10
    prompt_text: str = ""


@app.get("/api/health")
def health_check():
    return {"status": "ok", "device": demo.device}


@app.get("/api/voices")
def get_voices():
    builtins = [{"id": f"preset:{k}", "name": v, "type": "builtin", "gender": None} for k, v in SPEAKING_STYLE_CHOICES]
    saved = [
        {
            "id": f"saved:{p['id']}",
            "name": p.get("name", "Unnamed"),
            "type": "saved",
            "gender": p.get("gender", "unknown"),
            "transcript": p.get("transcript", ""),
            "created": p.get("created", ""),
        }
        for p in list_profiles()
    ]
    return {
        "voices": builtins + saved,
        "gender_options": [{"label": label, "value": value} for label, value in GENDER_OPTIONS],
        "speaker_options": [{"label": label, "value": value} for label, value in SPEAKER_GENDER_OPTIONS],
    }


@app.post("/api/voices/save")
def save_voice(
    name: str = Form(...),
    gender: str = Form("unknown"),
    audio: UploadFile = File(...),
    prompt: str = Form(""),
):
    try:
        ext = os.path.splitext(audio.filename or "")[1] or ".wav"
        temp_path = f"data/temp_{uuid.uuid4().hex}{ext}"
        os.makedirs("data", exist_ok=True)
        with open(temp_path, "wb") as f:
            f.write(audio.file.read())

        profile_id, _msg = save_profile(
            name=name,
            audio_path=temp_path,
            gender=gender,
            transcript=prompt,
        )
        os.remove(temp_path)
        return {"status": "success", "message": f"Voice '{name}' saved.", "id": f"saved:{profile_id}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/voices/{voice_id}")
def delete_voice(voice_id: str):
    try:
        if not voice_id.startswith("saved:"):
            raise HTTPException(status_code=400, detail="Can only delete saved voices.")
        delete_profile(voice_id.replace("saved:", ""))
        return {"status": "success", "message": "Voice deleted."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/outputs")
def get_outputs():
    files = _list_output_files()
    return {"folder": str(_ensure_output_dir().resolve()), "count": len(files), "files": files}


@app.post("/api/outputs/open-folder")
def open_outputs_folder():
    folder = _ensure_output_dir().resolve()
    try:
        if sys.platform == "win32":
            os.startfile(str(folder))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)])
        else:
            subprocess.Popen(["xdg-open", str(folder)])
        return {"status": "success", "folder": str(folder)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not open folder: {e}")


@app.delete("/api/outputs")
def delete_outputs():
    folder = _ensure_output_dir()
    deleted = 0
    for p in folder.glob("*.wav"):
        try:
            p.unlink()
            deleted += 1
        except Exception:
            continue
    return {"status": "success", "deleted": deleted, "folder": str(folder.resolve())}


@app.post("/api/asr")
def transcribe_audio(audio: UploadFile = File(...)):
    try:
        temp_path = f"data/temp_asr_{uuid.uuid4().hex}.wav"
        os.makedirs("data", exist_ok=True)
        with open(temp_path, "wb") as f:
            f.write(audio.file.read())

        text = demo.prompt_wav_recognition(temp_path)
        os.remove(temp_path)
        return {"text": text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/generate")
def generate_audio(
    text: str = Form(...),
    voice_select: str = Form("none"),
    speaker_gender: str = Form(""),
    control_instruction: str = Form(""),
    cfg_value: float = Form(2.0),
    normalize: bool = Form(True),
    denoise: bool = Form(True),
    timesteps: int = Form(10),
    prompt_text: str = Form(""),
    reference_audio: Optional[UploadFile] = File(None),
):
    ref_bytes: bytes | None = None
    ref_filename: str | None = None
    if reference_audio is not None:
        ref_bytes = reference_audio.file.read()
        ref_filename = reference_audio.filename

    def stream():
        log_queue: queue.Queue = queue.Queue()

        def worker() -> None:
            temp_ref_path: str | None = None
            try:
                online_check = revalidate_online_license(force=True)
                if not online_check.ok:
                    log_queue.put({"type": "error", "message": online_check.message})
                    return

                def on_line(line: str) -> None:
                    log_queue.put({"type": "log", "line": line})

                log = ProcessLog(on_line=on_line)
                ref_wav_path = None
                effective_voice = voice_select

                log.add("Job started.")
                log.add(f"Device: {demo.device}")

                if effective_voice == "auto" and speaker_gender:
                    auto = resolve_auto_voice(speaker_gender)
                    if auto:
                        effective_voice = auto
                        prof = get_profile(auto.replace("saved:", ""))
                        if prof:
                            log.add(
                                f"Auto-matched voice: {prof.get('name')} "
                                f"({prof.get('gender', 'unknown')})"
                            )
                    else:
                        effective_voice = _auto_fallback_voice_for_speaker(speaker_gender)
                        fallback_style = effective_voice.split("preset:", 1)[1]
                        log.add(
                            f"No saved voice for speaker gender «{speaker_gender}» — "
                            f"using stable fallback style «{fallback_style}»."
                        )

                if effective_voice.startswith("saved:"):
                    prof = get_profile(effective_voice.replace("saved:", ""))
                    if prof:
                        log.add(
                            f"Using saved profile: {prof.get('name')} "
                            f"({prof.get('gender', 'unknown')})"
                        )
                elif effective_voice.startswith("preset:"):
                    key = effective_voice.split("preset:", 1)[1]
                    log.add(f"Using built-in style: {key}")

                resolved_control = control_instruction
                if ref_bytes:
                    temp_ref_path = f"data/temp_ref_{uuid.uuid4().hex}.wav"
                    os.makedirs("data", exist_ok=True)
                    with open(temp_ref_path, "wb") as f:
                        f.write(ref_bytes)
                    ref_wav_path = temp_ref_path
                    log.add(f"Reference upload: {ref_filename or 'audio'}")
                elif effective_voice != "none":
                    if effective_voice.startswith("preset:"):
                        key = effective_voice.split("preset:", 1)[1]
                        resolved_control = get_style_control(key)
                    elif effective_voice.startswith("saved:"):
                        prof_id = effective_voice.split("saved:", 1)[1]
                        ref_wav_path = get_profile_audio_path(prof_id)

                profile_gender = None
                if effective_voice.startswith("saved:"):
                    prof = get_profile(effective_voice.replace("saved:", ""))
                    profile_gender = (prof or {}).get("gender")

                resolved_control, gender_notes = merge_speaker_control(
                    resolved_control,
                    speaker_gender,
                    has_reference=bool(ref_wav_path),
                    profile_gender=profile_gender,
                )
                resolved_control = _enforce_voice_consistency(resolved_control)
                for note in gender_notes:
                    log.add(note)
                log.add("Voice consistency lock: enabled for all sentences/chunks.")
                normalized_text, removed_special_sign = _sanitize_text_for_tts(text)
                if removed_special_sign:
                    log.add("Sanitized text: removed special sign '៖' to prevent it being spoken.")
                text_chunks = _split_long_text_for_tts(normalized_text)

                plan_lines: list[str] = []
                if speaker_gender:
                    plan_lines.append(f"Speaker: {speaker_gender}")
                if effective_voice.startswith("saved:"):
                    prof = get_profile(effective_voice.replace("saved:", ""))
                    plan_lines.append(f"Voice source: saved profile ({(prof or {}).get('name', 'unknown')})")
                elif effective_voice.startswith("preset:"):
                    plan_lines.append(f"Voice source: built-in style ({effective_voice.split('preset:', 1)[1]})")
                else:
                    plan_lines.append("Voice source: adaptive / auto")
                if ref_wav_path:
                    plan_lines.append("Reference audio: enabled")
                if resolved_control.strip():
                    plan_lines.append("Style control: enabled")
                if len(text_chunks) > 1:
                    plan_lines.append(f"Long-text mode: {len(text_chunks)} chunks")
                if removed_special_sign:
                    plan_lines.append("Symbol safety: removed '៖' from input before synthesis")
                plan_lines.append(f"Timesteps: {timesteps} | CFG: {cfg_value}")
                log_queue.put({"type": "plan", "plan": "\n".join(plan_lines)})

                if len(text_chunks) > MAX_TTS_CHUNKS:
                    raise RuntimeError(
                        f"Text is too long for one request ({len(text_chunks)} chunks). "
                        f"Please shorten it or use batch mode."
                    )

                if len(text_chunks) > 1:
                    log.add(
                        f"Long text detected: split into {len(text_chunks)} chunks "
                        f"(~{MAX_TTS_CHUNK_CHARS} chars per chunk) for stability."
                    )

                final_sr: int | None = None
                pieces: list[np.ndarray] = []
                base_plan: str = ""
                locked_ref_path: str | None = None

                for idx, chunk_text in enumerate(text_chunks, start=1):
                    if len(text_chunks) > 1:
                        log.add(f"Chunk {idx}/{len(text_chunks)} started.")

                    chunk_ref_path = ref_wav_path or locked_ref_path
                    chunk_prompt_text = prompt_text if chunk_ref_path == ref_wav_path else ""
                    sr, wav, plan = demo.generate_tts_audio(
                        text_input=chunk_text,
                        control_instruction=resolved_control,
                        reference_wav_path_input=chunk_ref_path,
                        prompt_text=chunk_prompt_text,
                        cfg_value_input=cfg_value,
                        do_normalize=normalize,
                        denoise=denoise,
                        inference_timesteps=timesteps,
                        log=log,
                    )
                    if final_sr is None:
                        final_sr = sr
                    elif sr != final_sr:
                        raise RuntimeError("Sample-rate mismatch between chunks; cannot merge safely.")
                    pieces.append(np.asarray(wav, dtype=np.float32))
                    if idx == 1:
                        base_plan = plan or ""

                    # When no user reference is provided, lock later chunks to chunk-1 voice.
                    if idx == 1 and len(text_chunks) > 1 and not ref_wav_path:
                        temp_lock_ref = Path("data") / f"temp_chunk_voice_lock_{uuid.uuid4().hex}.wav"
                        temp_lock_ref.parent.mkdir(parents=True, exist_ok=True)
                        sf.write(str(temp_lock_ref), wav, sr, format="WAV", subtype="PCM_16")
                        locked_ref_path = str(temp_lock_ref)
                        log.add("Voice lock: using chunk 1 voice as reference for remaining chunks.")

                if not pieces or final_sr is None:
                    raise RuntimeError("No audio generated.")

                if len(pieces) == 1:
                    wav = pieces[0]
                else:
                    pause_samples = max(1, int(final_sr * CHUNK_PAUSE_SECONDS))
                    pause = np.zeros((pause_samples,), dtype=np.float32)
                    joined: list[np.ndarray] = []
                    for i, piece in enumerate(pieces):
                        joined.append(piece)
                        if i < len(pieces) - 1:
                            joined.append(pause)
                    wav = np.concatenate(joined)

                sr = final_sr
                plan = base_plan

                if temp_ref_path and os.path.exists(temp_ref_path):
                    os.remove(temp_ref_path)
                    temp_ref_path = None

                buffer = io.BytesIO()
                sf.write(buffer, wav, sr, format="WAV", subtype="PCM_16")
                audio_bytes = buffer.getvalue()
                duration = len(wav) / sr if sr else 0.0
                out_dir = _ensure_output_dir()
                save_name = f"sinekool_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.wav"
                save_path = out_dir / save_name
                with open(save_path, "wb") as wf:
                    wf.write(audio_bytes)

                log_queue.put(
                    {
                        "type": "done",
                        "logs": log._lines,
                        "audio_base64": base64.b64encode(audio_bytes).decode("ascii"),
                        "sample_rate": sr,
                        "duration_sec": round(duration, 2),
                        "device": demo.device,
                        "voice_used": effective_voice,
                        "plan": plan,
                        "text": normalized_text,
                        "saved_file": save_name,
                        "saved_path": str(save_path.resolve()),
                    }
                )
            except Exception as e:
                log_queue.put({"type": "error", "message": str(e)})
            finally:
                if 'locked_ref_path' in locals() and locked_ref_path and os.path.exists(locked_ref_path):
                    os.remove(locked_ref_path)
                if temp_ref_path and os.path.exists(temp_ref_path):
                    os.remove(temp_ref_path)
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                log_queue.put(None)

        threading.Thread(target=worker, daemon=True).start()

        while True:
            item = log_queue.get()
            if item is None:
                break
            yield json.dumps(item, ensure_ascii=False) + "\n"

    return StreamingResponse(
        stream(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=False)
