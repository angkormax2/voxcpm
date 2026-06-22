"""Regression tests for the voice/speaker/style selection system.

Covers the seeded designed-speaker bank and `resolve_voice_for_synthesis`, which
combines WHO speaks (voice dropdown) with HOW (style dropdown) and decides the
reproducibility seed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import speaker_bank as sb  # noqa: E402
import voice_choices as vc  # noqa: E402


# ----------------------------- speaker bank ------------------------------- #


def test_speaker_bank_has_balanced_roster():
    assert sb.speaker_count() == 12
    males = [s for s in sb.SPEAKERS if s["gender"] == "male"]
    females = [s for s in sb.SPEAKERS if s["gender"] == "female"]
    assert len(males) == 6
    assert len(females) == 6


def test_speaker_ids_and_seeds_are_unique():
    ids = [s["id"] for s in sb.SPEAKERS]
    seeds = [s["seed"] for s in sb.SPEAKERS]
    assert len(set(ids)) == len(ids)
    assert len(set(seeds)) == len(seeds)


def test_default_speaker_resolvable():
    assert sb.get_speaker(sb.DEFAULT_SPEAKER_ID) is not None
    assert sb.default_speaker_seed() == sb.get_speaker(sb.DEFAULT_SPEAKER_ID)["seed"]


def test_unknown_speaker_is_none():
    assert sb.get_speaker("nope") is None
    assert sb.get_speaker_seed("nope") is None


# -------------------------- voice resolution ------------------------------ #


def _resolve(voice, style="custom", manual="", ref=None, use_prompt_text=False):
    return vc.resolve_voice_for_synthesis(
        voice, ref, manual, style, use_prompt_text=use_prompt_text
    )


def test_designed_speaker_uses_its_own_seed_and_identity():
    ref, control, seed = _resolve("designed:sovann")
    assert ref is None
    assert seed == sb.get_speaker_seed("sovann")
    assert "male" in control.lower()


def test_speaker_plus_style_combine_in_order():
    ref, control, seed = _resolve("designed:sovann", style="news")
    # Identity first, then the delivery style.
    assert control.lower().index("masculine") < control.lower().index("news anchor")
    assert seed == sb.get_speaker_seed("sovann")


def test_manual_notes_appended():
    _, control, _ = _resolve("designed:vichea", style="story", manual="speak slowly")
    assert control.endswith("speak slowly")


def test_uploaded_reference_overrides_designed_speaker():
    # Explicit clone intent wins; speaker description is dropped.
    ref, control, seed = _resolve("designed:dara", ref="C:/clip.wav")
    assert ref == "C:/clip.wav"
    assert "masculine" not in control.lower()
    assert seed == sb.default_speaker_seed()


def test_none_choice_falls_back_to_default_seed():
    ref, control, seed = _resolve("none", style="happy")
    assert seed == sb.default_speaker_seed()
    assert "cheerful" in control.lower()


def test_ultimate_cloning_drops_control_and_style():
    ref, control, seed = _resolve(
        "designed:dara", style="news", manual="loud", use_prompt_text=True
    )
    assert control == ""


def test_join_controls_dedupes_and_skips_blanks():
    assert vc._join_controls("a", "", "  ", "a", "b") == "a, b"


def test_dropdowns_are_split_who_vs_how():
    voices = dict(vc.build_voice_dropdown_choices()).values()
    # No style presets leak into the voice (WHO) dropdown anymore.
    assert not any(v.startswith("preset:") for v in voices)
    assert any(v.startswith("designed:") for v in voices)
    styles = [val for _, val in vc.build_style_dropdown_choices()]
    assert "news" in styles and "custom" in styles
