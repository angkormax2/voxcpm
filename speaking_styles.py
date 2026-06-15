"""Preset speaking styles for VoxCPM2 voice design (Control Instruction)."""

from __future__ import annotations

# Each preset maps to the text placed in Control Instruction (voice design mode).
SPEAKING_STYLE_PRESETS: dict[str, str] = {
    "custom": "",
    "neutral": (
        "Clear neutral narrator, natural pace, balanced tone, easy to understand"
    ),
    "news": (
        "Professional news anchor reading the headlines, crisp articulation, "
        "authoritative and objective tone, steady measured pace, same voice for "
        "Khmer and English words in the script"
    ),
    "story": (
        "Engaging storyteller narrating a story, warm expressive voice, "
        "natural dramatic pacing with gentle emphasis on key moments"
    ),
    "sad": (
        "Emotional sad storytelling voice, soft and melancholic tone, "
        "slower pace, gentle sadness and vulnerability"
    ),
    "happy": (
        "Cheerful upbeat voice, bright and friendly tone, "
        "lively pace with a smiling delivery"
    ),
    "laugh": (
        "Humorous voice with natural laughter in the delivery, "
        "playful amused tone, relaxed pace, light chuckles between phrases"
    ),
    "excited": (
        "Highly excited energetic announcer, fast enthusiastic pace, "
        "strong emphasis, celebratory tone"
    ),
    "calm": (
        "Calm soothing voice, slow relaxed pace, soft gentle tone, "
        "meditation-like peaceful delivery"
    ),
    "whisper": (
        "Soft intimate whisper, very quiet breathy tone, "
        "slow careful pace, close-mic ASMR style"
    ),
    "angry": (
        "Intense angry voice, sharp firm tone, forceful stressed delivery, "
        "faster pace with strong emphasis"
    ),
    "romantic": (
        "Romantic gentle voice, tender and affectionate tone, "
        "slow warm pace, intimate emotional delivery"
    ),
    "horror": (
        "Dark suspenseful horror narrator, low tense tone, "
        "slow ominous pace, eerie quiet intensity"
    ),
    "documentary": (
        "Documentary narrator voice, deep thoughtful tone, "
        "measured pace, informative and cinematic gravitas"
    ),
    "podcast": (
        "Casual podcast host, conversational friendly tone, "
        "natural relaxed pace, informal and approachable"
    ),
    "teacher": (
        "Patient teacher explaining a lesson, clear friendly tone, "
        "moderate pace, encouraging and easy to follow"
    ),
    "announcer": (
        "Event hype announcer, bold powerful voice, "
        "dynamic pace, grand exciting stadium energy"
    ),
    "customer_service": (
        "Polite customer service representative, warm professional tone, "
        "clear friendly pace, helpful and reassuring"
    ),
    "elderly": (
        "Wise elderly storyteller, warm slightly raspy voice, "
        "slow gentle pace, kind and reflective"
    ),
    "child": (
        "Playful young child voice, cute lively tone, "
        "bouncy pace, innocent and cheerful"
    ),
}

# Dropdown labels (English UI; Gradio i18n can wrap the field label, not each choice).
SPEAKING_STYLE_CHOICES: list[tuple[str, str]] = [
    ("custom", "✏️ Custom (edit below)"),
    ("neutral", "🎙️ Neutral narrator"),
    ("news", "📰 Reading news"),
    ("story", "📖 Read story"),
    ("sad", "😢 Sad / emotional story"),
    ("happy", "😊 Happy / cheerful"),
    ("laugh", "😂 Laugh / humorous"),
    ("excited", "🎉 Excited / hype"),
    ("calm", "🧘 Calm / relaxing"),
    ("whisper", "🤫 Whisper / ASMR"),
    ("angry", "😠 Angry / intense"),
    ("romantic", "💕 Romantic / gentle"),
    ("horror", "👻 Horror / suspense"),
    ("documentary", "🎬 Documentary"),
    ("podcast", "🎧 Podcast / casual"),
    ("teacher", "👩‍🏫 Teacher / explain"),
    ("announcer", "📣 Announcer / event"),
    ("customer_service", "💼 Customer service"),
    ("elderly", "👴 Elderly / wise"),
    ("child", "🧒 Child / playful"),
]

SPEAKING_STYLE_KEYS = [key for key, _ in SPEAKING_STYLE_CHOICES]


def get_style_control(style_key: str) -> str:
    return SPEAKING_STYLE_PRESETS.get(style_key, "")
