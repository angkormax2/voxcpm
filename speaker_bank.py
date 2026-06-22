"""Seeded designed-speaker bank for VoxCPM2 voice design.

Each speaker is a *reproducible* voice: a fixed random seed plus a base
voice-design description. Because the only source of voice randomness during
inference is the diffusion initial noise (``torch.randn`` in the CFM sampler),
locking the seed makes the same speaker sound identical every time — no
reference audio file required.

Pick a speaker -> always that voice. Toggle "random voice" -> seed is ignored
and you get a fresh voice each generation (the legacy behaviour).
"""

from __future__ import annotations

from typing import Optional, TypedDict


class Speaker(TypedDict):
    id: str
    name: str
    gender: str  # "male" | "female"
    tag: str  # short tone descriptor for the dropdown label
    seed: int
    control: str  # base voice-design description


# 6 male + 6 female. Distinct seeds + distinct descriptions => distinct voices.
SPEAKERS: list[Speaker] = [
    # ── Male ──
    {
        "id": "dara",
        "name": "Dara",
        "gender": "male",
        "tag": "warm",
        "seed": 110101,
        "control": (
            "Adult male speaker, warm natural masculine voice, medium-low pitch, "
            "clear articulation, steady friendly delivery"
        ),
    },
    {
        "id": "sovann",
        "name": "Sovann",
        "gender": "male",
        "tag": "deep, authoritative",
        "seed": 110202,
        "control": (
            "Adult male speaker, deep resonant masculine voice, low pitch, "
            "authoritative confident tone, measured news-anchor delivery"
        ),
    },
    {
        "id": "rithy",
        "name": "Rithy",
        "gender": "male",
        "tag": "bright, youthful",
        "seed": 110303,
        "control": (
            "Young adult male speaker, bright energetic voice, medium-high pitch, "
            "lively upbeat tone, natural quick pace"
        ),
    },
    {
        "id": "visal",
        "name": "Visal",
        "gender": "male",
        "tag": "calm, gentle",
        "seed": 110404,
        "control": (
            "Adult male speaker, calm soft masculine voice, gentle soothing tone, "
            "slow relaxed pace, mellow delivery"
        ),
    },
    {
        "id": "makara",
        "name": "Makara",
        "gender": "male",
        "tag": "mature, cinematic",
        "seed": 110505,
        "control": (
            "Mature male speaker, rich resonant voice, deep cinematic tone, "
            "thoughtful measured pace, documentary gravitas"
        ),
    },
    {
        "id": "vichea",
        "name": "Vichea",
        "gender": "male",
        "tag": "clear, neutral",
        "seed": 110606,
        "control": (
            "Adult male speaker, clear neutral masculine voice, balanced pitch, "
            "professional even tone, natural easy-to-understand pace"
        ),
    },
    # ── Female ──
    {
        "id": "sophea",
        "name": "Sophea",
        "gender": "female",
        "tag": "warm, gentle",
        "seed": 120101,
        "control": (
            "Adult female speaker, warm gentle feminine voice, medium pitch, "
            "clear articulation, friendly natural delivery"
        ),
    },
    {
        "id": "channary",
        "name": "Channary",
        "gender": "female",
        "tag": "bright, cheerful",
        "seed": 120202,
        "control": (
            "Young adult female speaker, bright cheerful voice, higher pitch, "
            "lively friendly tone, smiling upbeat delivery"
        ),
    },
    {
        "id": "bopha",
        "name": "Bopha",
        "gender": "female",
        "tag": "soft, soothing",
        "seed": 120303,
        "control": (
            "Adult female speaker, soft soothing feminine voice, calm gentle tone, "
            "slow relaxed pace, warm intimate delivery"
        ),
    },
    {
        "id": "maly",
        "name": "Maly",
        "gender": "female",
        "tag": "clear, professional",
        "seed": 120404,
        "control": (
            "Adult female speaker, clear professional feminine voice, balanced pitch, "
            "crisp articulate tone, steady news-presenter pace"
        ),
    },
    {
        "id": "sreyneang",
        "name": "Sreyneang",
        "gender": "female",
        "tag": "youthful, sweet",
        "seed": 120505,
        "control": (
            "Young female speaker, sweet light voice, higher pitch, "
            "soft pleasant tone, gentle natural pace"
        ),
    },
    {
        "id": "kanha",
        "name": "Kanha",
        "gender": "female",
        "tag": "mature, expressive",
        "seed": 120606,
        "control": (
            "Mature female speaker, expressive warm voice, medium-low pitch, "
            "rich storyteller tone, natural dramatic pacing"
        ),
    },
]

# Fixed house voice used out of the box (reproducible by default).
DEFAULT_SPEAKER_ID = "vichea"

_BY_ID: dict[str, Speaker] = {s["id"]: s for s in SPEAKERS}


def speaker_count() -> int:
    return len(SPEAKERS)


def get_speaker(speaker_id: str) -> Optional[Speaker]:
    return _BY_ID.get((speaker_id or "").strip())


def default_speaker() -> Speaker:
    return _BY_ID[DEFAULT_SPEAKER_ID]


def default_speaker_seed() -> int:
    return default_speaker()["seed"]


def speaker_dropdown_label(speaker: Speaker) -> str:
    gender = speaker["gender"].capitalize()
    return f"Designed · {speaker['name']} ({gender}, {speaker['tag']})"


def speaker_dropdown_choices() -> list[tuple[str, str]]:
    """(label, value) pairs; value is ``designed:<id>``."""
    return [
        (speaker_dropdown_label(s), f"designed:{s['id']}")
        for s in SPEAKERS
    ]


def get_speaker_control(speaker_id: str) -> str:
    s = get_speaker(speaker_id)
    return s["control"] if s else ""


def get_speaker_seed(speaker_id: str) -> Optional[int]:
    s = get_speaker(speaker_id)
    return s["seed"] if s else None
