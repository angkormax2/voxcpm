import os
import re
import sys
import logging
from datetime import datetime

from voxcpm.cuda_env import ensure_cuda_paths

ensure_cuda_paths()

import numpy as np
import torch
import gradio as gr
from typing import Callable, Optional, Tuple
from pathlib import Path

os.environ["TOKENIZERS_PARALLELISM"] = "false"


def _patch_windows_asyncio() -> None:
    """Suppress benign ConnectionResetError spam from Gradio on Windows."""
    if sys.platform != "win32":
        return
    import asyncio
    from asyncio.proactor_events import _ProactorBasePipeTransport

    _orig = _ProactorBasePipeTransport._call_connection_lost

    def _quiet_connection_lost(self, exc):
        try:
            _orig(self, exc)
        except ConnectionResetError:
            pass

    _ProactorBasePipeTransport._call_connection_lost = _quiet_connection_lost

    # Transport patch is enough; avoid get_event_loop() at import (deprecated on Py3.11+).


_patch_windows_asyncio()

import voxcpm
from voxcpm.paths import resolve_default_voxcpm2_path
from voxcpm.utils.text_normalize import contains_khmer, detect_tts_language
from speaking_styles import SPEAKING_STYLE_CHOICES, get_style_control
from voice_profiles import (
    delete_profile,
    get_profile,
    get_profile_audio_path,
    list_profile_choices,
    save_profile,
)
from voice_choices import (
    VOICE_CHOOSE,
    build_voice_dropdown_choices,
    choice_to_speaking_style_key,
    resolve_voice_for_synthesis,
    voice_inventory_summary,
)

DEFAULT_MODEL_ID = resolve_default_voxcpm2_path(Path(__file__).parent)


def _configure_stdio_utf8() -> None:
    """Avoid UnicodeEncodeError on Windows consoles (cp1252) when logging Khmer etc."""
    if sys.platform == "win32":
        os.environ.setdefault("PYTHONUTF8", "1")
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass


_configure_stdio_utf8()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# ---------- Inline i18n (en + zh-CN only) ----------

_USAGE_INSTRUCTIONS_EN = (
    "**VoxCPM2 — Three Modes of Speech Generation:**\n\n"
    "🎨 **Voice Design** — Create a brand-new voice  \n"
    "No reference audio required. Describe the desired voice characteristics "
    "(gender, age, tone, emotion, pace …) in **Control Instruction**, and VoxCPM2 "
    "will craft a unique voice from your description alone.\n\n"
    "🎛️ **Controllable Cloning** — Clone a voice with optional style guidance  \n"
    "Upload a reference audio clip, then use **Control Instruction** to steer "
    "emotion, speaking pace, and overall style while preserving the original timbre.\n\n"
    "🎙️ **Ultimate Cloning** — Reproduce every vocal nuance through audio continuation  \n"
    "Turn on **Ultimate Cloning Mode** and provide (or auto-transcribe) the reference audio's transcript. "
    "The model treats the reference clip as a spoken prefix and seamlessly **continues** from it, faithfully preserving every vocal detail."
    "Note: This mode will disable Control Instruction."
)

_EXAMPLES_FOOTER_EN = (
    "---\n"
    "**💡 Voice Description Examples:**  \n"
    "Try the following Control Instructions to explore different voices:  \n\n"
    "**Example 1 — Gentle & Melancholic Girl**  \n"
    '`Control Instruction`: *"A young girl with a soft, sweet voice. '
    'Speaks slowly with a melancholic, slightly tsundere tone."*  \n'
    '`Target Text`: *"I never asked you to stay… It\'s not like I care or anything. '
    'But… why does it still hurt so much now that you\'re gone?"*  \n\n'
    "**Example 2 — Laid-Back Surfer Dude**  \n"
    '`Control Instruction`: *"Relaxed young male voice, slightly nasal, '
    'lazy drawl, very casual and chill."*  \n'
    '`Target Text`: *"Dude, did you see that set? The waves out there are totally gnarly today. '
    "Just catching barrels all morning — it's like, totally righteous, you know what I mean?\"*"
)

_USAGE_INSTRUCTIONS_ZH = (
    "**VoxCPM2 — 三种语音生成方式：**\n\n"
    "🎨 **声音设计（Voice Design）**  \n"
    "无需参考音频。在 **Control Instruction** 中描述目标音色特征"
    "（性别、年龄、语气、情绪、语速等），VoxCPM2 即可为你从零创造独一无二的声音。\n\n"
    "🎛️ **可控克隆（Controllable Cloning）**  \n"
    "上传参考音频，同时可选地使用 **Control Instruction** 来指定情绪、语速、风格等表达方式，"
    "在保留原始音色的基础上灵活控制说话风格。\n\n"
    "🎙️ **极致克隆（Ultimate Cloning）**  \n"
    "开启 **极致克隆模式** 并提供参考音频的文字内容（可自动识别）。"
    "模型会将参考音频视为已说出的前文，以**音频续写**的方式完整还原参考音频中的所有声音细节。"
    "注意：该模式与可控克隆模式互斥，将禁用Control Instruction。\n\n"
)

_EXAMPLES_FOOTER_ZH = (
    "---\n"
    "**💡 声音描述示例（中英文均可）：**  \n\n"
    "**示例 1 — 深宫太后**  \n"
    '`Control Instruction`: *"中老年女性，声音低沉阴冷，语速缓慢而有力，'
    '字字深思熟虑，带有深不可测的城府与威慑感。"*  \n'
    '`Target Text`: *"哀家在这深宫待了四十年，什么风浪没见过？你以为瞒得过哀家？"*  \n\n'
    "**示例 2 — 暴躁驾校教练**  \n"
    '`Control Instruction`: *"暴躁的中年男声，语速快，充满无奈和愤怒"*  \n'
    '`Target Text`: *"踩离合！踩刹车啊！你往哪儿开呢？前面是树你看不见吗？'
    '我教了你八百遍了，打死方向盘！你是不是想把车给我开到沟里去？"*  \n\n'
    "---\n"
    "**🗣️ 方言生成指南：**  \n"
    "要生成地道的方言语音，请在 **Target Text** 中直接使用方言词汇和句式，"
    "并在 **Control Instruction** 中描述方言特征。  \n\n"
    "**示例 — 广东话**  \n"
    '`Control Instruction`: *"粤语，中年男性，语气平淡"*  \n'
    '✅ 正确（粤语表达）：*"伙計，唔該一個A餐，凍奶茶少甜！"*  \n'
    '❌ 错误（普通话原文）：*"伙计，麻烦来一个A餐，冻奶茶少甜！"*  \n\n'
    "**示例 — 河南话**  \n"
    '`Control Instruction`: *"河南话，接地气的大叔"*  \n'
    '✅ 正确（河南话表达）：*"恁这是弄啥嘞？晌午吃啥饭？"*  \n'
    '❌ 错误（普通话原文）：*"你这是在干什么呢？中午吃什么饭？"*  \n\n'
    "🤖 **小技巧：** 不知道方言怎么写？可以用豆包、DeepSeek、Kimi 等 AI 助手"
    "将普通话翻译为方言文本，再粘贴到 Target Text 中即可。  \n\n"
)

_I18N_TRANSLATIONS = {
    "en": {
        "reference_audio_label": "🎤 Reference Audio (optional — upload for cloning)",
        "show_prompt_text_label": "🎙️ Ultimate Cloning Mode (transcript-guided cloning)",
        "show_prompt_text_info": "Auto-transcribes reference audio for every vocal nuance reproduced. Control Instruction will be disabled when active.",
        "prompt_text_label": "Transcript of Reference Audio (auto-filled via ASR, editable)",
        "prompt_text_placeholder": "The transcript of your reference audio will appear here …",
        "voice_library_title": "💾 Saved voice library",
        "voice_select_label": "🎤 Voice",
        "voice_select_info": "Built-in styles (20) or your saved clones — or choose «Choose voice…» and upload reference below",
        "saved_voice_label": "Use saved cloned voice",
        "saved_voice_info": "Clone once, reuse every time — no need to re-upload reference audio",
        "profile_name_label": "Name for new voice",
        "profile_gender_label": "Voice type",
        "save_voice_btn": "💾 Save current reference as voice",
        "delete_voice_btn": "🗑️ Delete selected voice",
        "dubbing_roadmap_title": "🎬 Video dubbing (planned)",
        "khmer_tips_title": "🇰🇭 Khmer pronunciation tips",
        "speaking_style_label": "🎭 Speaking style (auto-fills Control Instruction)",
        "speaking_style_info": "Pick a preset, or choose Custom to write your own below",
        "control_label": "🎛️ Control Instruction (optional — supports Chinese & English)",
        "control_placeholder": "e.g. A warm young woman / 年轻女性，温柔甜美 / Excited and fast-paced",
        "target_text_label": "✍️ Target Text — the content to speak",
        "generate_btn": "🔊 Generate Speech",
        "generated_audio_label": "Generated Audio",
        "status_log_label": "📋 Process log",
        "status_log_info": "Live status while loading models, warming up, and synthesizing speech",
        "synthesis_preview_label": "📝 What will be spoken (auto-split for long text)",
        "synthesis_preview_info": "Each numbered line is synthesized separately, then joined into one audio file",
        "advanced_settings_title": "⚙️ Advanced Settings",
        "ref_denoise_label": "Reference audio enhancement",
        "ref_denoise_info": "Apply ZipEnhancer denoising to the reference audio before cloning",
        "normalize_label": "Text normalization",
        "normalize_info": "Normalize numbers, dates, and abbreviations via wetext",
        "cfg_label": "CFG (guidance scale)",
        "cfg_info": "Higher → closer to the prompt / reference; lower → more creative variation",
        "dit_steps_label": "LocDiT flow-matching steps",
        "dit_steps_info": "LocDiT flow-matching steps — more steps → maybe better audio quality, but slower",
        "usage_instructions": _USAGE_INSTRUCTIONS_EN,
        "examples_footer": _EXAMPLES_FOOTER_EN,
    },
    "zh-CN": {
        "reference_audio_label": "🎤 参考音频（可选 — 上传后用于克隆）",
        "show_prompt_text_label": "🎙️ 极致克隆模式（基于文本引导的极致克隆）",
        "show_prompt_text_info": "自动识别参考音频文本，完整还原音色、节奏、情感等全部声音细节。开启后 Control Instruction 将暂时禁用",
        "prompt_text_label": "参考音频内容文本（ASR 自动填充，可手动编辑）",
        "prompt_text_placeholder": "参考音频的文字内容将自动识别并显示在此处 …",
        "voice_library_title": "💾 已保存的声音库",
        "saved_voice_label": "使用已保存的克隆声音",
        "saved_voice_info": "克隆一次，永久复用，无需重复上传参考音频",
        "profile_name_label": "新声音名称",
        "profile_gender_label": "声音类型",
        "save_voice_btn": "💾 保存当前参考音频为声音",
        "delete_voice_btn": "🗑️ 删除所选声音",
        "dubbing_roadmap_title": "🎬 视频配音（规划中）",
        "khmer_tips_title": "🇰🇭 高棉语发音提示",
        "speaking_style_label": "🎭 说话风格（自动填入 Control Instruction）",
        "speaking_style_info": "选择预设风格，或选「自定义」在下方手动填写",
        "control_label": "🎛️ Control Instruction（可选 — 支持中英文描述）",
        "control_placeholder": "如：年轻女性，温柔甜美 / A warm young woman / 暴躁老哥，语速飞快",
        "target_text_label": "✍️ Target Text — 要合成的目标文本",
        "generate_btn": "🔊 开始生成",
        "generated_audio_label": "生成结果",
        "status_log_label": "📋 处理日志",
        "status_log_info": "加载模型、预热与合成语音时的实时状态",
        "synthesis_preview_label": "📝 实际朗读内容（长文本会自动分段）",
        "synthesis_preview_info": "每一行单独合成后再拼接为完整音频，便于核对发音内容",
        "advanced_settings_title": "⚙️ 高级设置",
        "ref_denoise_label": "参考音频降噪增强",
        "ref_denoise_info": "克隆前使用 ZipEnhancer 对参考音频进行降噪处理",
        "normalize_label": "文本规范化",
        "normalize_info": "自动规范化数字、日期及缩写（基于 wetext）",
        "cfg_label": "CFG（引导强度）",
        "cfg_info": "数值越高 → 越贴合提示/参考音色；数值越低 → 生成风格更自由",
        "dit_steps_label": "LocDiT 流匹配迭代步数",
        "dit_steps_info": "LocDiT 流匹配生成迭代步数 — 步数越多 → 可能生成更好的音频质量，但速度变慢",
        "usage_instructions": _USAGE_INSTRUCTIONS_ZH,
        "examples_footer": _EXAMPLES_FOOTER_ZH,
    },
    "zh-Hans": None,  # alias, filled below
    "zh": None,       # alias, filled below
}
_I18N_TRANSLATIONS["zh-Hans"] = _I18N_TRANSLATIONS["zh-CN"]
_I18N_TRANSLATIONS["zh"] = _I18N_TRANSLATIONS["zh-CN"]

for _d in _I18N_TRANSLATIONS.values():
    if _d is not None:
        for _k, _v in _I18N_TRANSLATIONS["en"].items():
            _d.setdefault(_k, _v)

I18N = gr.I18n(**_I18N_TRANSLATIONS)

DEFAULT_TARGET_TEXT = (
    "VoxCPM2 is a creative multilingual TTS model from ModelBest, "
    "designed to generate highly realistic speech."
)

_CUSTOM_CSS = """
/* ═══════════════════════════════════════════════════════════════
   VoxCPM2 — Materio MUI Premium Dark Theme
   ═══════════════════════════════════════════════════════════════ */

@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

:root {
    --vox-bg-deep: #0F1117;
    --vox-bg-card: #1A1D2E;
    --vox-bg-card-hover: #1E2235;
    --vox-bg-surface: #242840;
    --vox-bg-input: #161928;
    --vox-border: rgba(99, 115, 175, 0.15);
    --vox-border-hover: rgba(124, 77, 255, 0.35);
    --vox-text-primary: #E7E9F0;
    --vox-text-secondary: #9DA4BF;
    --vox-text-muted: #6B7294;
    --vox-accent-1: #7C4DFF;
    --vox-accent-2: #536DFE;
    --vox-accent-3: #448AFF;
    --vox-gradient: linear-gradient(135deg, #7C4DFF 0%, #536DFE 50%, #448AFF 100%);
    --vox-gradient-glow: linear-gradient(135deg, #9C6FFF 0%, #738FFE 50%, #64A0FF 100%);
    --vox-success: #66BB6A;
    --vox-warning: #FFA726;
    --vox-error: #EF5350;
    --vox-radius: 12px;
    --vox-radius-lg: 16px;
    --vox-shadow: 0 4px 24px rgba(0, 0, 0, 0.3);
    --vox-shadow-glow: 0 0 30px rgba(124, 77, 255, 0.15);
    --vox-transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

/* ── Global Overrides ── */
body, .gradio-container {
    background: var(--vox-bg-deep) !important;
    color: var(--vox-text-primary) !important;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
}

.gradio-container {
    max-width: 1400px !important;
}

/* ── Header ── */
.vox-header {
    background: linear-gradient(180deg, rgba(124,77,255,0.08) 0%, transparent 100%);
    border-bottom: 1px solid var(--vox-border);
    padding: 1.25rem 2rem;
    margin: -1rem -1rem 1.5rem -1rem;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 1rem;
}
.vox-header img {
    height: 52px;
    width: auto;
    filter: drop-shadow(0 0 12px rgba(124,77,255,0.3));
    transition: var(--vox-transition);
}
.vox-header img:hover {
    filter: drop-shadow(0 0 20px rgba(124,77,255,0.5));
    transform: scale(1.05);
}
.vox-header-text {
    display: flex;
    flex-direction: column;
    gap: 2px;
}
.vox-header-title {
    font-size: 1.6rem;
    font-weight: 700;
    background: var(--vox-gradient);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    letter-spacing: -0.02em;
}
.vox-header-subtitle {
    font-size: 0.82rem;
    color: var(--vox-text-muted);
    font-weight: 400;
    letter-spacing: 0.02em;
}
.vox-badge {
    background: var(--vox-gradient);
    color: white;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    margin-left: 4px;
}

/* ── Card Sections ── */
.vox-card {
    background: var(--vox-bg-card) !important;
    border: 1px solid var(--vox-border) !important;
    border-radius: var(--vox-radius-lg) !important;
    padding: 1.25rem !important;
    margin-bottom: 1rem !important;
    transition: var(--vox-transition);
    box-shadow: var(--vox-shadow);
}
.vox-card:hover {
    border-color: var(--vox-border-hover) !important;
    box-shadow: var(--vox-shadow), var(--vox-shadow-glow);
}

.vox-card-title {
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--vox-accent-1);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 0.75rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid var(--vox-border);
}

/* ── Inputs ── */
.gradio-container input[type="text"],
.gradio-container textarea,
.gradio-container select {
    background: var(--vox-bg-input) !important;
    border: 1px solid var(--vox-border) !important;
    border-radius: var(--vox-radius) !important;
    color: var(--vox-text-primary) !important;
    transition: var(--vox-transition);
    font-family: 'Inter', sans-serif !important;
}
.gradio-container input[type="text"]:focus,
.gradio-container textarea:focus {
    border-color: var(--vox-accent-1) !important;
    box-shadow: 0 0 0 3px rgba(124, 77, 255, 0.15) !important;
    outline: none !important;
}

/* ── Dropdown ── */
.gradio-container .wrap .wrap-inner {
    background: var(--vox-bg-input) !important;
    border-color: var(--vox-border) !important;
}

/* ── Labels ── */
.gradio-container label span {
    color: var(--vox-text-primary) !important;
    font-weight: 500 !important;
    font-size: 0.88rem !important;
}
.gradio-container .info {
    color: var(--vox-text-muted) !important;
}

/* ── Toggle Switch ── */
.switch-toggle {
    padding: 8px 12px;
    border-radius: var(--vox-radius);
    background: var(--vox-bg-surface);
    border: 1px solid var(--vox-border);
    transition: var(--vox-transition);
}
.switch-toggle:hover {
    border-color: var(--vox-border-hover);
}
.switch-toggle input[type="checkbox"] {
    appearance: none;
    -webkit-appearance: none;
    width: 44px;
    height: 24px;
    background: #3A3F5C;
    border-radius: 12px;
    position: relative;
    cursor: pointer;
    transition: background 0.3s ease;
    flex-shrink: 0;
}
.switch-toggle input[type="checkbox"]::after {
    content: "";
    position: absolute;
    top: 2px;
    left: 2px;
    width: 20px;
    height: 20px;
    background: var(--vox-text-secondary);
    border-radius: 50%;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    box-shadow: 0 2px 6px rgba(0,0,0,0.3);
}
.switch-toggle input[type="checkbox"]:checked {
    background: var(--vox-accent-1);
}
.switch-toggle input[type="checkbox"]:checked::after {
    transform: translateX(20px);
    background: white;
}

/* ── Buttons ── */
.gradio-container button.primary {
    background: var(--vox-gradient) !important;
    border: none !important;
    color: white !important;
    font-weight: 600 !important;
    font-size: 1rem !important;
    padding: 14px 28px !important;
    border-radius: var(--vox-radius) !important;
    transition: var(--vox-transition);
    box-shadow: 0 4px 15px rgba(124, 77, 255, 0.3) !important;
    text-transform: none !important;
    letter-spacing: 0.02em;
    position: relative;
    overflow: hidden;
}
.gradio-container button.primary::before {
    content: '';
    position: absolute;
    top: 0; left: -100%;
    width: 100%; height: 100%;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,0.15), transparent);
    transition: left 0.5s ease;
}
.gradio-container button.primary:hover {
    background: var(--vox-gradient-glow) !important;
    box-shadow: 0 6px 25px rgba(124, 77, 255, 0.45) !important;
    transform: translateY(-2px);
}
.gradio-container button.primary:hover::before {
    left: 100%;
}
.gradio-container button.primary:active {
    transform: translateY(0);
}

.gradio-container button.secondary {
    background: var(--vox-bg-surface) !important;
    border: 1px solid var(--vox-border) !important;
    color: var(--vox-text-primary) !important;
    border-radius: var(--vox-radius) !important;
    transition: var(--vox-transition);
}
.gradio-container button.secondary:hover {
    border-color: var(--vox-accent-1) !important;
    background: var(--vox-bg-card-hover) !important;
}

.gradio-container button.stop {
    background: rgba(239, 83, 80, 0.1) !important;
    border: 1px solid rgba(239, 83, 80, 0.3) !important;
    color: var(--vox-error) !important;
    border-radius: var(--vox-radius) !important;
    transition: var(--vox-transition);
}
.gradio-container button.stop:hover {
    background: rgba(239, 83, 80, 0.2) !important;
    border-color: var(--vox-error) !important;
}

/* ── Sliders ── */
.gradio-container input[type="range"] {
    accent-color: var(--vox-accent-1) !important;
}

/* ── Accordion ── */
.gradio-container .accordion {
    background: var(--vox-bg-surface) !important;
    border: 1px solid var(--vox-border) !important;
    border-radius: var(--vox-radius) !important;
    overflow: hidden;
    transition: var(--vox-transition);
}
.gradio-container .accordion:hover {
    border-color: var(--vox-border-hover) !important;
}
.gradio-container .label-wrap {
    background: transparent !important;
    padding: 12px 16px !important;
}

/* ── Audio Player ── */
.gradio-container .audio-player {
    background: var(--vox-bg-surface) !important;
    border: 1px solid var(--vox-border) !important;
    border-radius: var(--vox-radius) !important;
}

/* ── Status Log (terminal-style) ── */
#status-log {
    background: var(--vox-bg-input) !important;
    border: 1px solid var(--vox-border) !important;
    border-radius: var(--vox-radius) !important;
}
#status-log textarea {
    font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace !important;
    font-size: 0.8rem !important;
    line-height: 1.5 !important;
    color: var(--vox-success) !important;
    background: transparent !important;
}

/* ── Progress Status ── */
#progress-status {
    background: var(--vox-bg-surface) !important;
    border: 1px solid var(--vox-border) !important;
    border-radius: var(--vox-radius) !important;
    padding: 12px 16px !important;
    font-weight: 500;
}

/* ── Markdown / Info sections ── */
.vox-info-panel {
    background: linear-gradient(135deg, rgba(124,77,255,0.05) 0%, rgba(83,109,254,0.05) 100%) !important;
    border: 1px solid rgba(124,77,255,0.15) !important;
    border-radius: var(--vox-radius-lg) !important;
    padding: 1.25rem !important;
}
.vox-info-panel h3, .vox-info-panel strong {
    color: var(--vox-accent-1) !important;
}

.gradio-container .prose {
    color: var(--vox-text-secondary) !important;
}
.gradio-container .prose strong {
    color: var(--vox-text-primary) !important;
}
.gradio-container .prose code {
    background: var(--vox-bg-surface) !important;
    color: var(--vox-accent-3) !important;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 0.85em;
}

/* ── Examples Footer ── */
.vox-examples {
    background: var(--vox-bg-card) !important;
    border: 1px solid var(--vox-border) !important;
    border-radius: var(--vox-radius-lg) !important;
    padding: 1.25rem !important;
    margin-top: 1rem !important;
}

/* ── Scrollbar ── */
::-webkit-scrollbar {
    width: 6px;
    height: 6px;
}
::-webkit-scrollbar-track {
    background: var(--vox-bg-deep);
}
::-webkit-scrollbar-thumb {
    background: var(--vox-bg-surface);
    border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
    background: var(--vox-accent-1);
}

/* ── Row / Column spacing ── */
.gradio-container .contain > .gap {
    gap: 1rem !important;
}

/* ── Tabs (if any) ── */
.gradio-container .tab-nav button {
    color: var(--vox-text-muted) !important;
    border: none !important;
    transition: var(--vox-transition);
}
.gradio-container .tab-nav button.selected {
    color: var(--vox-accent-1) !important;
    border-bottom: 2px solid var(--vox-accent-1) !important;
}

/* ── Output card ── */
.vox-output-card {
    background: var(--vox-bg-card) !important;
    border: 1px solid var(--vox-border) !important;
    border-radius: var(--vox-radius-lg) !important;
    padding: 1.5rem !important;
    box-shadow: var(--vox-shadow);
    position: sticky;
    top: 1rem;
}

/* ── Generate button wrapper ── */
.vox-generate-wrap {
    margin-top: 0.5rem !important;
    margin-bottom: 0.5rem !important;
}
.vox-generate-wrap button {
    width: 100% !important;
    padding: 16px 28px !important;
    font-size: 1.05rem !important;
}

/* ── Responsive ── */
@media (max-width: 768px) {
    .vox-header {
        flex-direction: column;
        text-align: center;
        padding: 1rem;
    }
    .vox-header-title {
        font-size: 1.3rem;
    }
}

/* ── Animations ── */
@keyframes fadeInUp {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
}
.gradio-container .block {
    animation: fadeInUp 0.4s ease forwards;
}

/* Legacy logo-container hide (we use vox-header now) */
.logo-container { display: none; }
"""

_APP_THEME = gr.themes.Base(
    primary_hue=gr.themes.Color(
        c50="#F3EEFF", c100="#E1D5FF", c200="#C9ADFF", c300="#B085FF",
        c400="#9C6FFF", c500="#7C4DFF", c600="#6B3FE8", c700="#5A31D1",
        c800="#4923BA", c900="#3815A3", c950="#270A8C",
    ),
    secondary_hue=gr.themes.Color(
        c50="#F0F2F8", c100="#D8DCE8", c200="#B0B8D0",  c300="#8890B0",
        c400="#6B7294", c500="#535A78", c600="#3A3F5C", c700="#2B3148",
        c800="#1E2235", c900="#1A1D2E", c950="#0F1117",
    ),
    neutral_hue=gr.themes.Color(
        c50="#F5F6FA", c100="#E7E9F0", c200="#CCD0DE", c300="#B0B5C9",
        c400="#9DA4BF", c500="#6B7294", c600="#535A78", c700="#3A3F5C",
        c800="#242840", c900="#1A1D2E", c950="#0F1117",
    ),
    font=[gr.themes.GoogleFont("Inter"), "system-ui", "sans-serif"],
).set(
    body_background_fill="#0F1117",
    body_background_fill_dark="#0F1117",
    body_text_color="#E7E9F0",
    body_text_color_dark="#E7E9F0",
    block_background_fill="#1A1D2E",
    block_background_fill_dark="#1A1D2E",
    block_border_color="rgba(99, 115, 175, 0.15)",
    block_border_color_dark="rgba(99, 115, 175, 0.15)",
    block_label_background_fill="#242840",
    block_label_background_fill_dark="#242840",
    block_label_text_color="#E7E9F0",
    block_label_text_color_dark="#E7E9F0",
    block_title_text_color="#E7E9F0",
    block_title_text_color_dark="#E7E9F0",
    block_radius="12px",
    input_background_fill="#161928",
    input_background_fill_dark="#161928",
    input_border_color="rgba(99, 115, 175, 0.15)",
    input_border_color_dark="rgba(99, 115, 175, 0.15)",
    input_placeholder_color="#6B7294",
    button_primary_background_fill="linear-gradient(135deg, #7C4DFF 0%, #536DFE 50%, #448AFF 100%)",
    button_primary_background_fill_dark="linear-gradient(135deg, #7C4DFF 0%, #536DFE 50%, #448AFF 100%)",
    button_primary_text_color="white",
    button_secondary_background_fill="#242840",
    button_secondary_background_fill_dark="#242840",
    button_secondary_text_color="#E7E9F0",
    border_color_primary="rgba(124, 77, 255, 0.35)",
    border_color_primary_dark="rgba(124, 77, 255, 0.35)",
    shadow_drop="0 4px 24px rgba(0, 0, 0, 0.3)",
    checkbox_background_color="#242840",
    checkbox_background_color_dark="#242840",
    slider_color="#7C4DFF",
    slider_color_dark="#7C4DFF",
)


# ---------- Model ----------

ZIPENHANCER_MODEL_ID = "iic/speech_zipenhancer_ans_multiloss_16k_base"


class ProcessLog:
    """Timestamped log buffer for the Gradio process log panel."""

    def __init__(
        self,
        initial: str = "",
        on_line: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._lines: list[str] = []
        self._on_line = on_line
        if initial.strip():
            self._lines = initial.strip().splitlines()

    def add(self, message: str) -> str:
        stamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{stamp}] {message}"
        self._lines.append(line)
        logger.info(message)
        if self._on_line is not None:
            self._on_line(line)
        return self.text()

    def text(self) -> str:
        return "\n".join(self._lines)


class VoxCPMDemo:
    def __init__(self, model_id: str = DEFAULT_MODEL_ID) -> None:
        self.device = self._detect_device()
        logger.info(f"Running on device: {self.device}")

        self.asr_model_id = "iic/SenseVoiceSmall"
        self.asr_model = None
        self._zipenhancer_model_id = ZIPENHANCER_MODEL_ID

        self.voxcpm_model: Optional[voxcpm.VoxCPM] = None
        self._model_id = model_id

    @staticmethod
    def _detect_device() -> str:
        return "cuda" if torch.cuda.is_available() else "cpu"

    def refresh_device(self) -> str:
        """Re-check CUDA availability (e.g. after fixing PATH on Windows)."""
        self.device = self._detect_device()
        logger.info(f"Running on device: {self.device}")
        return self.device

    def _get_asr_model(self):
        if self.asr_model is None:
            from funasr import AutoModel

            logger.info(f"Loading ASR model: {self.asr_model_id}")
            self.asr_model = AutoModel(
                model=self.asr_model_id,
                vad_model="fsmn-vad",
                vad_kwargs={"max_single_segment_time": 30000},
                disable_update=True,
                log_level="WARNING",
                device="cuda:0" if self.device == "cuda" else "cpu",
            )
        return self.asr_model

    def get_or_load_voxcpm(self, log: Optional[ProcessLog] = None) -> voxcpm.VoxCPM:
        if self.voxcpm_model is not None:
            if log:
                log.add("VoxCPM2 model already loaded — skipping reload.")
            return self.voxcpm_model

        self.refresh_device()

        if log:
            log.add(f"Loading VoxCPM2 from: {self._model_id}")
            log.add("Reading weights (first run may take 1–2 minutes)…")
        else:
            logger.info(f"Loading model: {self._model_id}")

        self.voxcpm_model = voxcpm.VoxCPM.from_pretrained(
            self._model_id,
            optimize=True,
            load_denoiser=False,
            warmup=False,
            device="cuda" if self.device == "cuda" else None,
        )
        if log:
            log.add("Weights loaded. Running warmup (short test generation)…")
        self.voxcpm_model.run_warmup()
        if log:
            log.add("Warmup complete. Model is ready.")
        else:
            logger.info("Model loaded successfully.")
        return self.voxcpm_model

    def _ensure_denoiser(self, model: voxcpm.VoxCPM, log: Optional[ProcessLog] = None) -> None:
        if model.denoiser is not None:
            return
        from voxcpm.zipenhancer import ZipEnhancer

        if log:
            log.add(f"Loading denoiser (ZipEnhancer): {self._zipenhancer_model_id}")
        else:
            logger.info(f"Loading denoiser: {self._zipenhancer_model_id}")
        model.denoiser = ZipEnhancer(self._zipenhancer_model_id)
        if log:
            log.add("Denoiser ready.")

    @staticmethod
    def _parse_sensevoice_results(res: list) -> str:
        try:
            from funasr.utils.postprocess_utils import rich_transcription_postprocess
        except ImportError:
            rich_transcription_postprocess = None

        parts: list[str] = []
        for item in res:
            raw = (item.get("text") or "").strip()
            if not raw:
                continue
            if rich_transcription_postprocess is not None:
                try:
                    parts.append(rich_transcription_postprocess(raw))
                    continue
                except Exception:
                    pass
            parts.append(raw.split("|>")[-1].strip())
        return " ".join(p for p in parts if p).strip()

    def prompt_wav_recognition(
        self,
        prompt_wav: Optional[str],
        log: Optional[ProcessLog] = None,
        *,
        language: str = "auto",
    ) -> str:
        if prompt_wav is None:
            return ""
        if log:
            log.add("Loading ASR model (SenseVoice + VAD)…")
        self._get_asr_model()
        if log:
            log.add(f"Transcribing reference audio (language={language})…")
        res = self._get_asr_model().generate(
            input=prompt_wav,
            cache={},
            language=language or "auto",
            use_itn=True,
            batch_size_s=60,
            merge_vad=True,
            merge_length_s=15,
        )
        text = self._parse_sensevoice_results(res)
        if log:
            preview = text[:120] + ("…" if len(text) > 120 else "")
            log.add(f"ASR finished: {preview or '(empty)'}")
        return text

    @staticmethod
    def format_synthesis_plan(segments: list[str]) -> str:
        if not segments:
            return ""
        if len(segments) == 1:
            return f"1. {segments[0]}"
        lines = []
        for i, seg in enumerate(segments, 1):
            preview = seg.replace("\n", " ")
            if len(preview) > 220:
                preview = preview[:220] + "…"
            lines.append(f"{i}. {preview}")
        return "\n".join(lines)

    def _build_generate_kwargs(
        self,
        *,
        final_text: str,
        audio_path: Optional[str],
        prompt_text_clean: Optional[str],
        cfg_value_input: float,
        do_normalize: bool,
        denoise: bool,
        inference_timesteps: int = 10,
    ) -> dict:
        generate_kwargs = dict(
            text=final_text,
            reference_wav_path=audio_path,
            cfg_value=float(cfg_value_input),
            inference_timesteps=inference_timesteps,
            normalize=do_normalize,
            denoise=denoise,
        )
        if prompt_text_clean and audio_path:
            generate_kwargs["prompt_wav_path"] = audio_path
            generate_kwargs["prompt_text"] = prompt_text_clean
        return generate_kwargs

    def prepare_tts_request(
        self,
        text_input: str,
        control_instruction: str = "",
        reference_wav_path_input: Optional[str] = None,
        prompt_text: str = "",
        cfg_value_input: float = 2.0,
        do_normalize: bool = True,
        denoise: bool = True,
        inference_timesteps: int = 10,
        log: Optional[ProcessLog] = None,
    ) -> Tuple[voxcpm.VoxCPM, dict, str, list[str]]:
        """Load model, build kwargs, and return synthesis plan before audio generation."""
        current_model = self.get_or_load_voxcpm(log)
        if denoise:
            self._ensure_denoiser(current_model, log)

        text = (text_input or "").strip()
        if len(text) == 0:
            raise ValueError("Please input text to synthesize.")

        control = (control_instruction or "").strip()
        control = re.sub(r"[()（）]", "", control).strip()
        final_text = f"({control}){text}" if control else text

        audio_path = reference_wav_path_input if reference_wav_path_input else None
        prompt_text_clean = (prompt_text or "").strip() or None

        if audio_path and prompt_text_clean:
            mode = "Ultimate cloning (audio continuation + reference)"
        elif audio_path:
            mode = "Controllable cloning (reference audio)"
        else:
            mode = "Voice design (control instruction only)"
        if log:
            log.add(f"Mode: {mode}")
            if control_instruction and not reference_wav_path_input:
                ctrl_preview = control_instruction[:120] + (
                    "…" if len(control_instruction) > 120 else ""
                )
                log.add(f"Speaking style / control: {ctrl_preview}")
            log.add("Preparing text and audio prompts…")
            if do_normalize:
                log.add("Text normalization enabled.")
            if denoise and audio_path:
                log.add("Reference audio denoising enabled.")

        generate_kwargs = self._build_generate_kwargs(
            final_text=final_text,
            audio_path=audio_path,
            prompt_text_clean=prompt_text_clean,
            cfg_value_input=cfg_value_input,
            do_normalize=do_normalize,
            denoise=denoise,
            inference_timesteps=inference_timesteps,
        )

        segments = current_model.prepare_synthesis_segments(final_text, normalize=do_normalize)
        synthesis_plan = self.format_synthesis_plan(segments)

        if log:
            lang = detect_tts_language(final_text)
            if lang == "km" or contains_khmer(final_text):
                log.add(
                    "Khmer detected - splits only at Khmer full stop (U+17D4 / U+17D5). "
                    "Add full stops between ideas for natural pauses; avoid comma-only breaks."
                )
                if "។" not in final_text and "៕" not in final_text:
                    log.add(
                        "Tip: no Khmer full stop found - insert them between sentences "
                        "so the model reads complete phrases, not broken fragments."
                    )
            preview = final_text[:80] + ("..." if len(final_text) > 80 else "")
            log.add(f"Target: {preview}")
            if len(segments) > 1:
                log.add(f"Long text -> {len(segments)} segments (listed in preview panel).")
            log.add(f"LocDiT steps: {inference_timesteps}, CFG: {cfg_value_input}")
            log.add("Ready to synthesize — see numbered lines in the preview panel.")

        return current_model, generate_kwargs, synthesis_plan, segments

    def run_tts_synthesis(
        self,
        current_model: voxcpm.VoxCPM,
        generate_kwargs: dict,
        *,
        log: Optional[ProcessLog] = None,
        progress: Optional[Callable[[float, str], None]] = None,
        n_segments: int = 1,
        on_status: Optional[Callable[[str], None]] = None,
    ) -> Tuple[int, np.ndarray]:
        last_logged_step = -1

        def on_synthesis_progress(step: int, total: int) -> None:
            nonlocal last_logged_step
            if progress is not None and total > 0:
                progress(
                    step / total,
                    f"Synthesizing segment(s)… {step}/{total}",
                )
            if log is not None and (
                step == 1 or step == total or step - last_logged_step >= max(1, total // 12)
            ):
                log.add(f"Synthesizing… step {step}/{total}")
                last_logged_step = step

        if log:
            if n_segments > 1:
                log.add(
                    f"Running synthesis ({n_segments} segments, one chained voice)…"
                )
            else:
                log.add("Running synthesis…")

        wav = None
        for item in current_model.generate_with_status(
            **generate_kwargs, progress_callback=on_synthesis_progress
        ):
            if isinstance(item, dict) and item.get("kind") == "status":
                msg = item["message"]
                if log:
                    log.add(msg)
                if on_status:
                    on_status(msg)
            else:
                wav = item
        if wav is None:
            wav = np.array([], dtype=np.float32)

        if log:
            log.add("Decoding audio (48 kHz)…")
        sr = current_model.tts_model.sample_rate
        duration = len(wav) / sr if sr else 0.0
        if log:
            log.add(f"Done — duration {duration:.2f}s, sample rate {sr} Hz")
        return sr, wav

    def generate_tts_audio(
        self,
        text_input: str,
        control_instruction: str = "",
        reference_wav_path_input: Optional[str] = None,
        prompt_text: str = "",
        cfg_value_input: float = 2.0,
        do_normalize: bool = True,
        denoise: bool = True,
        inference_timesteps: int = 10,
        log: Optional[ProcessLog] = None,
        progress: Optional[Callable[[float, str], None]] = None,
    ) -> Tuple[int, np.ndarray, str]:
        model, kwargs, plan, segments = self.prepare_tts_request(
            text_input=text_input,
            control_instruction=control_instruction,
            reference_wav_path_input=reference_wav_path_input,
            prompt_text=prompt_text,
            cfg_value_input=cfg_value_input,
            do_normalize=do_normalize,
            denoise=denoise,
            inference_timesteps=inference_timesteps,
            log=log,
        )
        sr, wav = self.run_tts_synthesis(
            model,
            kwargs,
            log=log,
            progress=progress,
            n_segments=len(segments),
        )
        return sr, wav, plan


# ---------- UI ----------

_KHMER_TIPS_MD = (
    "**Khmer is not a core VoxCPM2 training language** — some words may be misread.\n\n"
    "- Fix the **written text** first (ASR/typo errors cause wrong speech).\n"
    "- Use **។** between sentences; avoid comma-only breaks.\n"
    "- Use **Saved voice** + **Reading news** style for stable tone.\n"
    "- For critical scripts, short sentences work best.\n"
    "- Future: video dubbing with per-character voices — see accordion below."
)

_DUBBING_ROADMAP_MD = (
    "**Planned:** Video → transcript with timestamps → **who said what** → "
    "**character voice** (male/female + saved clone) → TTS per line → "
    "**timeline dubbing** (silence + speech like the original).\n\n"
    "Details: `docs/DUBBING_ROADMAP.md` in the project folder."
)

def create_demo_interface(demo: VoxCPMDemo):
    gr.set_static_paths(paths=[Path.cwd().absolute() / "assets"])

    def _generate(
        text: str,
        voice_choice: str,
        control_instruction: str,
        ref_wav: Optional[str],
        use_prompt_text: bool,
        prompt_text_value: str,
        cfg_value: float,
        do_normalize: bool,
        denoise: bool,
        dit_steps: int,
        progress=gr.Progress(),
    ):
        """Stream updates to audio / synthesis preview / log separately."""
        log = ProcessLog()
        keep_preview = gr.update()
        try:
            log.add("Job started.")
            yield None, keep_preview, log.text(), "⏳ Starting…"

            actual_prompt_text = prompt_text_value.strip() if use_prompt_text else ""
            effective_ref, actual_control = resolve_voice_for_synthesis(
                voice_choice,
                ref_wav,
                control_instruction,
                use_prompt_text=use_prompt_text,
            )

            if not (text or "").strip():
                log.add("Error: Target Text is empty.")
                yield None, keep_preview, log.text(), "❌ No text"
                raise ValueError("Please input text to synthesize.")

            log.add("Validating inputs…")
            yield None, keep_preview, log.text(), "⏳ Validating…"

            progress_state = {"text": ""}

            def report_progress(fraction: float, desc: str = "Processing…") -> None:
                progress(fraction, desc=desc)
                progress_state["text"] = desc

            def on_status(msg: str) -> None:
                progress_state["text"] = msg

            model, generate_kwargs, synthesis_plan, segments = demo.prepare_tts_request(
                text_input=text,
                control_instruction=actual_control,
                reference_wav_path_input=effective_ref,
                prompt_text=actual_prompt_text,
                cfg_value_input=cfg_value,
                do_normalize=do_normalize,
                denoise=denoise,
                inference_timesteps=int(dit_steps),
                log=log,
            )
            # Show segment list in preview only (not duplicated on audio/log panels).
            yield None, synthesis_plan, log.text(), "⏳ Preparing synthesis…"

            last_logged_step = -1

            def on_synthesis_progress(step: int, total: int) -> None:
                nonlocal last_logged_step
                if total > 0:
                    report_progress(
                        step / total,
                        f"Synthesizing… {step}/{total}",
                    )
                if (
                    step == 1
                    or step == total
                    or step - last_logged_step >= max(1, total // 8)
                ):
                    log.add(f"Synthesizing… step {step}/{total}")
                    last_logged_step = step

            wav_np = None
            for item in model.generate_with_status(
                **generate_kwargs, progress_callback=on_synthesis_progress
            ):
                if isinstance(item, dict) and item.get("kind") == "status":
                    msg = item["message"]
                    log.add(msg)
                    on_status(msg)
                    yield None, synthesis_plan, log.text(), msg
                else:
                    wav_np = item

            if wav_np is None:
                wav_np = np.array([], dtype=np.float32)

            log.add("Decoding audio (48 kHz)…")
            yield None, synthesis_plan, log.text(), "⏳ Finalizing audio…"

            sr = model.tts_model.sample_rate
            duration = len(wav_np) / sr if sr else 0.0
            log.add(f"Done — duration {duration:.2f}s, sample rate {sr} Hz")
            progress(1.0, desc="Complete")
            final_status = progress_state["text"] or "✅ Complete"
            yield (sr, wav_np), synthesis_plan, log.text(), final_status
        except Exception as exc:
            log.add(f"Failed: {exc}")
            yield None, keep_preview, log.text(), f"❌ {exc}"
            raise

    def _on_toggle_instant(checked, voice_choice):
        """Instant UI toggle — no ASR, no blocking."""
        if checked:
            return (
                gr.update(visible=True, value="", placeholder="Recognizing reference audio..."),
                gr.update(interactive=False),
                gr.update(interactive=False),
            )
        return (
            gr.update(visible=False),
            gr.update(interactive=True),
            gr.update(interactive=True),
        )

    def _on_voice_select(voice_choice: str, uploaded_path: Optional[str], ultimate_mode: bool):
        if ultimate_mode:
            return gr.update(), gr.update(), ""
        if not voice_choice or voice_choice == VOICE_CHOOSE:
            return (
                gr.update(),
                gr.update(interactive=True),
                "No voice selected — upload **Reference audio** or pick a built-in / saved voice.",
            )
        if voice_choice.startswith("saved:"):
            profile_id = voice_choice[6:]
            path = get_profile_audio_path(profile_id)
            if not path:
                return (
                    gr.update(),
                    gr.update(interactive=True),
                    "⚠️ Saved audio file missing. Re-save this voice.",
                )
            profile = get_profile(profile_id) or {}
            style = profile.get("speaking_style", "custom")
            ctrl = get_style_control(style) if style and style != "custom" else ""
            msg = f"Saved clone **{profile.get('name', '')}** ({profile.get('gender', '')})."
            transcript = (profile.get("transcript") or "").strip()
            if transcript:
                msg += f" Transcript on file ({len(transcript)} chars)."
            return gr.update(value=path), gr.update(value=ctrl, interactive=style == "custom"), msg
        if voice_choice.startswith("preset:"):
            key = voice_choice[7:]
            ctrl = get_style_control(key) if key != "custom" else ""
            label = dict(SPEAKING_STYLE_CHOICES).get(key, key)
            return (
                gr.update(),
                gr.update(value=ctrl, interactive=key == "custom"),
                f"Built-in voice: **{label}** — no reference file needed.",
            )
        return gr.update(), gr.update(interactive=True), ""

    def _on_save_voice(name, gender, voice_choice, uploaded_path, prompt_text_val, use_prompt):
        try:
            transcript_val = prompt_text_val.strip() if use_prompt else ""
            style_key = choice_to_speaking_style_key(voice_choice)
            profile_id, msg = save_profile(
                name=name,
                audio_path=uploaded_path or "",
                gender=gender,
                speaking_style=style_key,
                transcript=transcript_val,
            )
            choices = build_voice_dropdown_choices()
            return (
                gr.update(choices=choices, value=f"saved:{profile_id}"),
                msg,
                voice_inventory_summary(),
            )
        except Exception as e:
            return gr.update(), f"❌ {e}", gr.update()

    def _on_delete_voice(voice_choice: str):
        profile_id = voice_choice[6:] if voice_choice.startswith("saved:") else ""
        msg = delete_profile(profile_id)
        return (
            gr.update(choices=build_voice_dropdown_choices(), value=VOICE_CHOOSE),
            msg,
            voice_inventory_summary(),
        )

    def _run_asr_if_needed(checked, audio_path, prior_log: str):
        """Run ASR after the UI has updated. Only when toggled ON."""
        log = ProcessLog(prior_log)
        if not checked or not audio_path:
            return gr.update(), log.text()
        try:
            asr_text = demo.prompt_wav_recognition(audio_path, log=log)
            return gr.update(value=asr_text), log.text()
        except Exception as e:
            log.add(f"ASR failed: {e}")
            logger.warning(f"ASR recognition failed: {e}")
            return gr.update(value=""), log.text()

    with gr.Blocks() as interface:
        # ── Premium Header ──
        gr.HTML(
            '<div class="vox-header">'
            '<img src="/gradio_api/file=assets/voxcpm_logo.png" alt="VoxCPM Logo">'
            '<div class="vox-header-text">'
            '<div class="vox-header-title">VoxCPM2 Studio By BONG Pisith <span class="vox-badge">v2.0</span></div>'
            '<div class="vox-header-subtitle">Creative Multilingual Text-to-Speech · Voice Design · Voice Cloning</div>'
            '</div>'
            '</div>'
        )

        # ── Collapsible usage guide ──
        with gr.Accordion("📖 How to Use — Voice Design, Cloning & Ultimate Mode", open=False, elem_classes=["vox-info-panel"]):
            gr.Markdown(I18N("usage_instructions"))

        with gr.Row():
            # ═══════════════════════════════════════
            #  LEFT COLUMN — Controls
            # ═══════════════════════════════════════
            with gr.Column(scale=5):

                # ── Card: Voice Selection ──
                with gr.Group(elem_classes=["vox-card"]):
                    gr.HTML('<div class="vox-card-title">🎤 Voice Selection</div>')
                    voice_select = gr.Dropdown(
                        choices=build_voice_dropdown_choices(),
                        value=VOICE_CHOOSE,
                        label=I18N("voice_select_label"),
                        info=I18N("voice_select_info"),
                    )
                    voice_inventory_md = gr.Markdown(voice_inventory_summary())

                    with gr.Accordion(I18N("voice_library_title"), open=False):
                        with gr.Row():
                            profile_name = gr.Textbox(
                                label=I18N("profile_name_label"),
                                placeholder="e.g. News Host Male / អ្នកអានព័ត៌មាន",
                            )
                            profile_gender = gr.Dropdown(
                                choices=[
                                    ("Unknown", "unknown"),
                                    ("Male", "male"),
                                    ("Female", "female"),
                                    ("Child", "child"),
                                    ("Neutral", "neutral"),
                                ],
                                value="unknown",
                                label=I18N("profile_gender_label"),
                            )
                        with gr.Row():
                            save_voice_btn = gr.Button(I18N("save_voice_btn"), variant="secondary")
                            delete_voice_btn = gr.Button(I18N("delete_voice_btn"), variant="stop")
                        voice_library_status = gr.Markdown("")

                # ── Card: Audio Input ──
                with gr.Group(elem_classes=["vox-card"]):
                    gr.HTML('<div class="vox-card-title">🎙️ Audio Input</div>')
                    reference_wav = gr.Audio(
                        sources=["upload", "microphone"],
                        type="filepath",
                        label=I18N("reference_audio_label"),
                    )
                    show_prompt_text = gr.Checkbox(
                        value=False,
                        label=I18N("show_prompt_text_label"),
                        info=I18N("show_prompt_text_info"),
                        elem_classes=["switch-toggle"],
                    )
                    prompt_text = gr.Textbox(
                        value="",
                        label=I18N("prompt_text_label"),
                        placeholder=I18N("prompt_text_placeholder"),
                        lines=2,
                        visible=False,
                    )

                # ── Card: Style & Text ──
                with gr.Group(elem_classes=["vox-card"]):
                    gr.HTML('<div class="vox-card-title">🎛️ Style & Text</div>')
                    control_instruction = gr.Textbox(
                        value="",
                        label=I18N("control_label"),
                        placeholder=I18N("control_placeholder"),
                        lines=2,
                    )
                    text = gr.Textbox(
                        value=DEFAULT_TARGET_TEXT,
                        label=I18N("target_text_label"),
                        lines=3,
                    )

                # ── Card: Advanced Settings ──
                with gr.Group(elem_classes=["vox-card"]):
                    with gr.Accordion(I18N("advanced_settings_title"), open=False):
                        DoDenoisePromptAudio = gr.Checkbox(
                            value=False,
                            label=I18N("ref_denoise_label"),
                            elem_classes=["switch-toggle"],
                            info=I18N("ref_denoise_info"),
                        )
                        DoNormalizeText = gr.Checkbox(
                            value=False,
                            label=I18N("normalize_label"),
                            elem_classes=["switch-toggle"],
                            info=I18N("normalize_info"),
                        )
                        cfg_value = gr.Slider(
                            minimum=1.0,
                            maximum=3.0,
                            value=2.0,
                            step=0.1,
                            label=I18N("cfg_label"),
                            info=I18N("cfg_info"),
                        )
                        dit_steps = gr.Slider(
                            minimum=1,
                            maximum=50,
                            value=10,
                            step=1,
                            label=I18N("dit_steps_label"),
                            info=I18N("dit_steps_info"),
                        )

                # ── Generate Button (full-width gradient) ──
                with gr.Group(elem_classes=["vox-generate-wrap"]):
                    run_btn = gr.Button(I18N("generate_btn"), variant="primary", size="lg")

                # ── Extra info panels ──
                with gr.Accordion(I18N("khmer_tips_title"), open=False):
                    gr.Markdown(_KHMER_TIPS_MD)
                with gr.Accordion(I18N("dubbing_roadmap_title"), open=False):
                    gr.Markdown(_DUBBING_ROADMAP_MD)

            # ═══════════════════════════════════════
            #  RIGHT COLUMN — Output
            # ═══════════════════════════════════════
            with gr.Column(scale=5):
                with gr.Group(elem_classes=["vox-output-card"]):
                    gr.HTML('<div class="vox-card-title">🔊 Output</div>')
                    audio_output = gr.Audio(label=I18N("generated_audio_label"))
                    progress_status = gr.Markdown(
                        "Ready — click **Generate Speech** to start.",
                        elem_id="progress-status",
                    )
                    synthesis_preview = gr.Textbox(
                        label=I18N("synthesis_preview_label"),
                        info=I18N("synthesis_preview_info"),
                        lines=8,
                        max_lines=16,
                        interactive=False,
                        elem_classes=["status-log"],
                        placeholder="Segment list appears here after you click Generate…",
                    )
                    status_log = gr.Textbox(
                        label=I18N("status_log_label"),
                        info=I18N("status_log_info"),
                        lines=14,
                        max_lines=24,
                        interactive=False,
                        elem_id="status-log",
                        elem_classes=["status-log"],
                        placeholder="Click Generate to see loading, warmup, and synthesis steps here…",
                    )

                # ── Examples footer ──
                with gr.Group(elem_classes=["vox-examples"]):
                    gr.Markdown(I18N("examples_footer"))

        voice_select.change(
            fn=_on_voice_select,
            inputs=[voice_select, reference_wav, show_prompt_text],
            outputs=[reference_wav, control_instruction, voice_library_status],
        )

        save_voice_btn.click(
            fn=_on_save_voice,
            inputs=[
                profile_name,
                profile_gender,
                voice_select,
                reference_wav,
                prompt_text,
                show_prompt_text,
            ],
            outputs=[voice_select, voice_library_status, voice_inventory_md],
        )

        delete_voice_btn.click(
            fn=_on_delete_voice,
            inputs=[voice_select],
            outputs=[voice_select, voice_library_status, voice_inventory_md],
        )

        show_prompt_text.change(
            fn=_on_toggle_instant,
            inputs=[show_prompt_text, voice_select],
            outputs=[prompt_text, control_instruction, voice_select],
        ).then(
            fn=_run_asr_if_needed,
            inputs=[show_prompt_text, reference_wav, status_log],
            outputs=[prompt_text, status_log],
        )

        run_btn.click(
            fn=_generate,
            inputs=[
                text,
                voice_select,
                control_instruction,
                reference_wav,
                show_prompt_text,
                prompt_text,
                cfg_value,
                DoNormalizeText,
                DoDenoisePromptAudio,
                dit_steps,
            ],
            outputs=[audio_output, synthesis_preview, status_log, progress_status],
            show_progress=False,
            api_name="generate",
        )

    return interface

def run_demo(
    server_name: str | None = None,
    server_port: int = 8808,
    show_error: bool = True,
    model_id: str = DEFAULT_MODEL_ID,
):
    if server_name is None:
        server_name = "127.0.0.1" if sys.platform == "win32" else "0.0.0.0"
    demo = VoxCPMDemo(model_id=model_id)
    interface = create_demo_interface(demo)
    project_root = Path.cwd().absolute()
    interface.queue(max_size=10, default_concurrency_limit=1).launch(
        server_name=server_name,
        server_port=server_port,
        show_error=show_error,
        i18n=I18N,
        theme=_APP_THEME,
        css=_CUSTOM_CSS,
        allowed_paths=[str(project_root / "data"), str(project_root / "assets")],
    )


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model-id", type=str, default=DEFAULT_MODEL_ID,
        help=f"Local path or HuggingFace repo ID (default: {DEFAULT_MODEL_ID})",
    )
    parser.add_argument("--port", type=int, default=8808, help="Server port")
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Server host (default: 127.0.0.1 on Windows, 0.0.0.0 elsewhere)",
    )
    args = parser.parse_args()
    run_demo(model_id=args.model_id, server_port=args.port, server_name=args.host)
