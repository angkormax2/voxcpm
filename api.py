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
import queue
import threading
from contextlib import asynccontextmanager
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

                if effective_voice in ("none", "auto") and speaker_gender:
                    auto = resolve_auto_voice(speaker_gender)
                    if auto:
                        effective_voice = auto
                        prof = get_profile(auto.replace("saved:", ""))
                        if prof:
                            log.add(
                                f"Auto-matched voice: {prof.get('name')} "
                                f"({prof.get('gender', 'unknown')})"
                            )
                    elif effective_voice == "auto":
                        log.add(
                            f"No saved voice for speaker gender «{speaker_gender}» — "
                            "using voice design."
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
                for note in gender_notes:
                    log.add(note)

                sr, wav, plan = demo.generate_tts_audio(
                    text_input=text,
                    control_instruction=resolved_control,
                    reference_wav_path_input=ref_wav_path,
                    prompt_text=prompt_text,
                    cfg_value_input=cfg_value,
                    do_normalize=normalize,
                    denoise=denoise,
                    inference_timesteps=timesteps,
                    log=log,
                )

                if temp_ref_path and os.path.exists(temp_ref_path):
                    os.remove(temp_ref_path)
                    temp_ref_path = None

                buffer = io.BytesIO()
                sf.write(buffer, wav, sr, format="WAV", subtype="PCM_16")
                audio_bytes = buffer.getvalue()
                duration = len(wav) / sr if sr else 0.0

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
                        "text": text.strip(),
                    }
                )
            except Exception as e:
                log_queue.put({"type": "error", "message": str(e)})
            finally:
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
