"""Unified voice picker: built-in presets + saved clones."""

from __future__ import annotations

from typing import Optional

from speaking_styles import SPEAKING_STYLE_CHOICES, get_style_control
from voice_profiles import get_profile, get_profile_audio_path, list_profile_choices

# Default when user has not picked a built-in or saved voice.
VOICE_CHOOSE = "none"


def builtin_voice_count() -> int:
    return len(SPEAKING_STYLE_CHOICES)


def saved_voice_count() -> int:
    return sum(1 for _, profile_id in list_profile_choices() if profile_id)


def voice_inventory_summary() -> str:
    n_builtin = builtin_voice_count()
    n_saved = saved_voice_count()
    saved_line = (
        f"**{n_saved} saved clone(s)**"
        if n_saved
        else "**0 saved clones** (upload reference audio and click Save)"
    )
    return (
        f"**{n_builtin} built-in voices** (voice design, no reference file) + {saved_line}. "
        "Pick one from the list, or leave **— Choose voice… —** and upload reference audio below."
    )


def build_voice_dropdown_choices() -> list[tuple[str, str]]:
    """Gradio dropdown: (label, value). Value is `none`, `preset:<key>`, or `saved:<id>`."""
    choices: list[tuple[str, str]] = [
        ("— Choose voice… (no clone / use reference below) —", VOICE_CHOOSE),
    ]
    for key, label in SPEAKING_STYLE_CHOICES:
        choices.append((f"Built-in · {label}", f"preset:{key}"))
    for label, profile_id in list_profile_choices():
        if profile_id:
            choices.append((f"Saved · {label}", f"saved:{profile_id}"))
    return choices


def resolve_voice_for_synthesis(
    voice_choice: str,
    uploaded_ref: Optional[str],
    control_instruction: str,
    *,
    use_prompt_text: bool,
) -> tuple[Optional[str], str]:
    """
    Return (reference_wav_path, control_instruction) for TTS.
    """
    if use_prompt_text:
        ref = _reference_from_choice(voice_choice, uploaded_ref)
        return ref, ""

    choice = voice_choice or VOICE_CHOOSE
    manual_control = (control_instruction or "").strip()

    if choice.startswith("saved:"):
        profile_id = choice[6:]
        ref = get_profile_audio_path(profile_id) or uploaded_ref
        profile = get_profile(profile_id)
        style_key = (profile or {}).get("speaking_style", "custom")
        style_control = get_style_control(style_key) if style_key != "custom" else ""
        control = manual_control or style_control
        return ref, control

    if choice.startswith("preset:"):
        style_key = choice[7:]
        style_control = get_style_control(style_key) if style_key != "custom" else ""
        control = manual_control or style_control
        return uploaded_ref or None, control

    # Choose / none — reference upload optional; control from text box only.
    return uploaded_ref or None, manual_control


def _reference_from_choice(voice_choice: str, uploaded_ref: Optional[str]) -> Optional[str]:
    if voice_choice.startswith("saved:"):
        profile_id = voice_choice[6:]
        return get_profile_audio_path(profile_id) or uploaded_ref
    return uploaded_ref or None


def choice_to_speaking_style_key(voice_choice: str) -> str:
    """For saving a profile — map current picker value to speaking_style metadata."""
    if voice_choice.startswith("preset:"):
        return voice_choice[7:]
    if voice_choice.startswith("saved:"):
        profile_id = voice_choice[6:]
        profile = get_profile(profile_id)
        return (profile or {}).get("speaking_style", "custom")
    return "custom"
