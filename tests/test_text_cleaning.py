"""Regression tests for the speakable-text cleaning pipeline.

Covers `remove_unspeakable_symbols` and `has_speakable_content` — the guards
that strip signs the TTS model can't voice (e.g. Khmer ៖, markdown `*`, runs
like `?....`) while preserving sentence terminators and the (control) prefix.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TN_PATH = ROOT / "src" / "voxcpm" / "utils" / "text_normalize.py"

spec = importlib.util.spec_from_file_location("voxcpm.utils.text_normalize", TN_PATH)
tn = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(tn)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("ខ្ញុំចង់និយាយ៖ សួស្តី", "ខ្ញុំចង់និយាយ សួស្តី"),  # Khmer colon removed
        ("តើអ្នកសុខសប្បាយទេ?....", "តើអ្នកសុខសប្បាយទេ?"),       # ?.... -> ?
        ("Hello... world", "Hello. world"),                      # ellipsis run -> .
        ("Wait!!! Really???", "Wait! Really?"),                  # collapse runs
        ("This is **bold** and _italic_", "This is bold and italic"),
        ("Price #1 ~approx~ |pipe|", "Price 1 approx pipe"),
        ("A → B ← C", "A B C"),                                   # arrows removed
    ],
)
def test_removes_unspeakable_signs(raw, expected):
    assert tn.remove_unspeakable_symbols(raw) == expected


def test_preserves_control_prefix():
    # The (control) voice-design prefix MUST survive — the speaker system depends on it.
    out = tn.remove_unspeakable_symbols("(warm male voice)សួស្តីបង")
    assert out.startswith("(warm male voice)")


def test_keeps_speakable_punctuation():
    text = "Normal sentence, keep this: yes; ok."
    assert tn.remove_unspeakable_symbols(text) == text


def test_keeps_khmer_terminators_and_collapses_repeats():
    assert tn.remove_unspeakable_symbols("ល្អ។។ បាទ៕") == "ល្អ។ បាទ៕"


def test_drops_leading_punctuation_and_attaches_floating_comma():
    assert tn.remove_unspeakable_symbols(", hello") == "hello"
    # A floating comma attaches to the preceding word (natural pause), not deleted.
    assert tn.remove_unspeakable_symbols("word , word") == "word, word"


def test_empty_and_none_safe():
    assert tn.remove_unspeakable_symbols("") == ""
    assert tn.remove_unspeakable_symbols(None) is None


@pytest.mark.parametrize(
    "text, speakable",
    [
        ("hello", True),
        ("សួស្តី", True),     # Khmer letters
        ("123", True),          # digits count
        ("###...", False),      # symbols only
        ("៖៖៖", False),        # Khmer punctuation only
        ("   ", False),
        ("", False),
    ],
)
def test_has_speakable_content(text, speakable):
    assert tn.has_speakable_content(text) is speakable
