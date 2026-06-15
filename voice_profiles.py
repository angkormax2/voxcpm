"""Saved voice clone profiles for the VoxCPM web UI."""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
PROFILES_DIR = PROJECT_ROOT / "data" / "voice_profiles"
AUDIO_DIR = PROFILES_DIR / "audio"
INDEX_FILE = PROFILES_DIR / "profiles.json"

NONE_CHOICE = "— No saved voice —"

GENDER_OPTIONS: list[tuple[str, str]] = [
    ("Unknown", "unknown"),
    ("Male", "male"),
    ("Female", "female"),
    ("Child", "child"),
    ("Neutral", "neutral"),
]

# Who is speaking at synthesis time — must be a concrete type for auto-match.
SPEAKER_GENDER_OPTIONS: list[tuple[str, str]] = [
    (label, value) for label, value in GENDER_OPTIONS if value != "unknown"
]

GENDER_LABELS = {value: label for label, value in GENDER_OPTIONS}

# Voice-design hints when no clone reference is used (or to reinforce speaker choice).
SPEAKER_GENDER_CONTROLS: dict[str, str] = {
    "male": (
        "Adult male speaker with a natural masculine voice, clear articulation, "
        "steady natural delivery"
    ),
    "female": (
        "Adult female speaker with a natural feminine voice, clear articulation, "
        "steady natural delivery"
    ),
    "child": (
        "Young child speaker, cute lively voice, innocent cheerful delivery, "
        "higher pitch appropriate for a child"
    ),
    "neutral": (
        "Clear neutral narrator, natural pace, balanced tone, easy to understand"
    ),
}


def speaker_gender_control(gender: str) -> str:
    return SPEAKER_GENDER_CONTROLS.get((gender or "").strip().lower(), "")


def merge_speaker_control(
    control_instruction: str,
    speaker_gender: str,
    *,
    has_reference: bool,
    profile_gender: str | None = None,
) -> tuple[str, list[str]]:
    """
    Blend speaker gender into control instruction for voice-design mode.
    Returns (control, log_notes).
    """
    notes: list[str] = []
    manual = (control_instruction or "").strip()
    gender_ctrl = speaker_gender_control(speaker_gender)
    want = (speaker_gender or "").strip().lower()

    if profile_gender and want and profile_gender.lower() not in (want, "unknown"):
        notes.append(
            f"Note: saved clone is tagged «{profile_gender}» but Speaker is «{want}» — "
            "clone audio overrides voice design."
        )

    if has_reference:
        notes.append(
            "Reference/clone audio defines the voice — pick a matching saved profile "
            "or clear the upload to use Speaker gender (voice design)."
        )
        if manual:
            return manual, notes
        return manual, notes

    if not gender_ctrl:
        return manual, notes

    if manual:
        merged = f"{gender_ctrl}, {manual}"
        notes.append(f"Applied speaker control for {GENDER_LABELS.get(want, want)}.")
        return merged, notes

    notes.append(f"Voice design using {GENDER_LABELS.get(want, want)} speaker (no clone reference).")
    return gender_ctrl, notes


def list_profiles() -> list[dict[str, Any]]:
    return list(_load_index().get("profiles", []))


def find_profile_by_gender(gender: str) -> dict[str, Any] | None:
    """Pick the most recently saved profile matching speaker gender."""
    want = (gender or "").strip().lower()
    if not want or want in {"unknown", "auto", "none"}:
        return None
    matches = [
        p for p in list_profiles() if (p.get("gender") or "unknown").lower() == want
    ]
    return matches[-1] if matches else None


def resolve_auto_voice(speaker_gender: str) -> str | None:
    """Return `saved:<id>` for auto speaker matching, or None."""
    profile = find_profile_by_gender(speaker_gender)
    if profile:
        return f"saved:{profile['id']}"
    return None


def _ensure_dirs() -> None:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)


def _load_index() -> dict[str, Any]:
    _ensure_dirs()
    if not INDEX_FILE.exists():
        return {"profiles": []}
    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_index(data: dict[str, Any]) -> None:
    _ensure_dirs()
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def list_profile_choices() -> list[tuple[str, str]]:
    """Gradio dropdown choices: (label, profile_id)."""
    data = _load_index()
    choices: list[tuple[str, str]] = [(NONE_CHOICE, "")]
    for p in data.get("profiles", []):
        label = p.get("name", "Unnamed")
        gender = p.get("gender", "")
        if gender and gender != "unknown":
            label = f"{label} ({GENDER_LABELS.get(gender, gender)})"
        choices.append((label, p["id"]))
    return choices


def get_profile(profile_id: str) -> dict[str, Any] | None:
    if not profile_id:
        return None
    for p in _load_index().get("profiles", []):
        if p["id"] == profile_id:
            return p
    return None


def get_profile_audio_path(profile_id: str) -> str | None:
    profile = get_profile(profile_id)
    if not profile:
        return None
    path = PROJECT_ROOT / profile["audio_file"]
    return str(path) if path.is_file() else None


def save_profile(
    *,
    name: str,
    audio_path: str,
    gender: str = "",
    language: str = "",
    speaking_style: str = "custom",
    transcript: str = "",
    notes: str = "",
) -> tuple[str, str]:
    """
    Copy reference audio into the library and register metadata.
    Returns (profile_id, message).
    """
    name = (name or "").strip()
    if not name:
        raise ValueError("Voice name is required.")
    if not audio_path or not Path(audio_path).is_file():
        raise ValueError("Upload reference audio before saving a voice.")

    _ensure_dirs()
    profile_id = uuid.uuid4().hex[:12]
    dest = AUDIO_DIR / f"{profile_id}.wav"
    shutil.copy2(audio_path, dest)

    entry = {
        "id": profile_id,
        "name": name,
        "gender": gender or "unknown",
        "language": language or "",
        "speaking_style": speaking_style or "custom",
        "transcript": (transcript or "").strip(),
        "notes": (notes or "").strip(),
        "audio_file": str(dest.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "created": datetime.now(timezone.utc).isoformat(),
    }

    data = _load_index()
    data.setdefault("profiles", []).append(entry)
    _save_index(data)
    return profile_id, f"Saved voice «{name}». Select it from the dropdown anytime."


def delete_profile(profile_id: str) -> str:
    if not profile_id:
        return "No voice selected."
    data = _load_index()
    profiles = data.get("profiles", [])
    kept = []
    removed = None
    for p in profiles:
        if p["id"] == profile_id:
            removed = p
        else:
            kept.append(p)
    if removed is None:
        return "Voice not found."
    audio = PROJECT_ROOT / removed["audio_file"]
    if audio.is_file():
        audio.unlink()
    data["profiles"] = kept
    _save_index(data)
    return f"Deleted voice «{removed.get('name', profile_id)}»."
