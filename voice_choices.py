"""Unified voice picker: designed speakers + built-in styles + saved clones."""

from __future__ import annotations

from typing import Optional

from speaking_styles import SPEAKING_STYLE_CHOICES, get_style_control
from speaker_bank import (
    default_speaker_seed,
    get_speaker,
    get_speaker_control,
    get_speaker_seed,
    speaker_count,
    speaker_dropdown_choices,
)
from voice_profiles import get_profile, get_profile_audio_path, list_profile_choices

# Default when user has not picked a built-in or saved voice.
VOICE_CHOOSE = "none"


def builtin_voice_count() -> int:
    return len(SPEAKING_STYLE_CHOICES)


def saved_voice_count() -> int:
    return sum(1 for _, profile_id in list_profile_choices() if profile_id)


def voice_inventory_summary() -> str:
    n_speakers = speaker_count()
    n_styles = builtin_voice_count()
    n_saved = saved_voice_count()
    saved_line = (
        f"**{n_saved} saved clone(s)**"
        if n_saved
        else "**0 saved clones** (upload reference audio and click Save)"
    )
    return (
        f"**{n_speakers} designed speakers** (consistent voices, no reference file) + "
        f"{saved_line}. Pick *who* speaks here, then choose *how* they speak in "
        f"**Speaking style** ({n_styles} styles), or upload reference audio to clone."
    )


def build_voice_dropdown_choices() -> list[tuple[str, str]]:
    """Gradio voice dropdown (WHO speaks): (label, value).

    Value is ``none``, ``designed:<id>``, or ``saved:<id>``. Delivery styles live
    in their own dropdown (``build_style_dropdown_choices``).
    """
    choices: list[tuple[str, str]] = [
        ("— Choose voice… (no clone / use reference below) —", VOICE_CHOOSE),
    ]
    # Designed speakers first — these are the consistent, repeatable voices.
    choices.extend(speaker_dropdown_choices())
    for label, profile_id in list_profile_choices():
        if profile_id:
            choices.append((f"Saved · {label}", f"saved:{profile_id}"))
    return choices


def build_style_dropdown_choices() -> list[tuple[str, str]]:
    """Gradio style dropdown (HOW they speak): (label, value). Value is a style key."""
    return [(label, key) for key, label in SPEAKING_STYLE_CHOICES]


def _join_controls(*parts: str) -> str:
    """Combine voice-design control fragments, dropping blanks/duplicates."""
    seen: list[str] = []
    for part in parts:
        piece = (part or "").strip().strip(",").strip()
        if piece and piece not in seen:
            seen.append(piece)
    return ", ".join(seen)


def resolve_voice_for_synthesis(
    voice_choice: str,
    uploaded_ref: Optional[str],
    control_instruction: str,
    style_choice: str = "custom",
    *,
    use_prompt_text: bool,
) -> tuple[Optional[str], str, Optional[int]]:
    """
    Return (reference_wav_path, control_instruction, seed) for TTS.

    Identity comes from ``voice_choice`` (WHO), delivery from ``style_choice`` (HOW),
    plus any free-text ``control_instruction``. ``seed`` is the voice's natural
    seed (fixed for designed speakers, the house default otherwise); the caller
    may override it (manual seed / random toggle).
    """
    default_seed = default_speaker_seed()
    manual_control = (control_instruction or "").strip()
    style_control = (
        get_style_control(style_choice)
        if style_choice and style_choice != "custom"
        else ""
    )

    if use_prompt_text:
        # Ultimate cloning continues from the reference audio — no control/style.
        ref = _reference_from_choice(voice_choice, uploaded_ref)
        return ref, "", default_seed

    choice = voice_choice or VOICE_CHOOSE

    if choice.startswith("designed:"):
        # Uploading reference audio is an explicit clone intent — let it win over
        # the designed speaker's voice description (which is for pure voice design).
        if uploaded_ref:
            return uploaded_ref, _join_controls(style_control, manual_control), default_seed
        speaker_id = choice[len("designed:"):]
        base = get_speaker_control(speaker_id)
        seed = get_speaker_seed(speaker_id) or default_seed
        # WHO (speaker identity) + HOW (style) + extra notes.
        return None, _join_controls(base, style_control, manual_control), seed

    if choice.startswith("saved:"):
        profile_id = choice[6:]
        ref = get_profile_audio_path(profile_id) or uploaded_ref
        # Identity comes from the clone audio; style + notes steer delivery.
        return ref, _join_controls(style_control, manual_control), default_seed

    if choice.startswith("preset:"):
        # Backward-compat: a style picked via the old voice dropdown.
        key = choice[7:]
        legacy = get_style_control(key) if key != "custom" else ""
        control = _join_controls(legacy, style_control, manual_control)
        return uploaded_ref or None, control, default_seed

    # Choose / none — reference upload optional; control = style + manual notes.
    return uploaded_ref or None, _join_controls(style_control, manual_control), default_seed


def _reference_from_choice(voice_choice: str, uploaded_ref: Optional[str]) -> Optional[str]:
    if voice_choice.startswith("saved:"):
        profile_id = voice_choice[6:]
        return get_profile_audio_path(profile_id) or uploaded_ref
    return uploaded_ref or None


def choice_to_speaking_style_key(voice_choice: str) -> str:
    """For saving a profile — map current picker value to speaking_style metadata."""
    if voice_choice.startswith("preset:"):
        return voice_choice[7:]
    if voice_choice.startswith("designed:"):
        return "custom"
    if voice_choice.startswith("saved:"):
        profile_id = voice_choice[6:]
        profile = get_profile(profile_id)
        return (profile or {}).get("speaking_style", "custom")
    return "custom"
