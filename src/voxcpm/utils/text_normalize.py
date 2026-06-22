# some functions are copied from https://github.com/FunAudioLLM/CosyVoice/blob/main/cosyvoice/utils/frontend_utils.py
import re
import regex
import inflect
from wetext import Normalizer

chinese_char_pattern = re.compile(r"[\u4e00-\u9fff]+")
khmer_char_pattern = re.compile(r"[\u1780-\u17ff]")
thai_char_pattern = re.compile(r"[\u0e00-\u0e7f]")


# whether contain chinese character
def contains_chinese(text):
    return bool(chinese_char_pattern.search(text))


def contains_khmer(text: str) -> bool:
    return bool(khmer_char_pattern.search(text))


def detect_tts_language(text: str) -> str:
    """Best-effort script detection for splitting / normalization."""
    if contains_chinese(text):
        return "zh"
    if contains_khmer(text):
        return "km"
    if thai_char_pattern.search(text):
        return "th"
    return "en"


def count_text_tokens(text: str, tokenize) -> int:
    try:
        ids = tokenize(text)
        return len(ids) if isinstance(ids, (list, tuple)) else len(list(ids))
    except Exception:
        return len(text)


# replace special symbol
def replace_corner_mark(text):
    text = text.replace("²", "平方")
    text = text.replace("³", "立方")
    text = text.replace("√", "根号")
    text = text.replace("≈", "约等于")
    text = text.replace("<", "小于")
    return text


# remove meaningless symbol
def remove_bracket(text):
    text = text.replace("（", " ").replace("）", " ")
    text = text.replace("【", " ").replace("】", " ")
    text = text.replace("`", "").replace("`", "")
    text = text.replace("——", " ")
    return text


# spell Arabic numerals
def spell_out_number(text: str, inflect_parser):
    new_text = []
    st = None
    for i, c in enumerate(text):
        if not c.isdigit():
            if st is not None:
                num_str = inflect_parser.number_to_words(text[st:i])
                new_text.append(num_str)
                st = None
            new_text.append(c)
        else:
            if st is None:
                st = i
    if st is not None and st < len(text):
        num_str = inflect_parser.number_to_words(text[st:])
        new_text.append(num_str)
    return "".join(new_text)


# split paragrah logic：
# 1. per sentence max len token_max_n, min len token_min_n, merge if last sentence len less than merge_len
# 2. cal sentence len according to lang
# 3. split sentence according to puncatation
def split_paragraph(text: str, tokenize, lang="zh", token_max_n=80, token_min_n=60, merge_len=20, comma_split=False):
    def calc_utt_length(_text: str):
        if lang in ("zh", "km", "th"):
            return len(_text.strip())
        return count_text_tokens(_text, tokenize)

    def should_merge(_text: str):
        if lang in ("zh", "km", "th"):
            return len(_text.strip()) < merge_len
        return count_text_tokens(_text, tokenize) < merge_len

    if lang == "zh":
        pounc = ["。", "？", "！", "；", "：", "、", ".", "?", "!", ";"]
    elif lang == "km":
        pounc = ["។", "៕", "?", "!", ".", ";", ":", "၊", "၊", "…"]
    elif lang == "th":
        pounc = [".", "?", "!", ";", ":", "ๆ"]
    else:
        pounc = [".", "?", "!", ";", ":"]
    if comma_split:
        pounc.extend(["，", ","])
    st = 0
    utts = []
    for i, c in enumerate(text):
        if c in pounc:
            if len(text[st:i]) > 0:
                utts.append(text[st:i] + c)
            if i + 1 < len(text) and text[i + 1] in ['"', "”"]:
                tmp = utts.pop(-1)
                utts.append(tmp + text[i + 1])
                st = i + 2
            else:
                st = i + 1
    if len(utts) == 0:
        if lang == "zh":
            utts.append(text + "。")
        elif lang == "km":
            utts.append(text + "។")
        else:
            utts.append(text + ".")
    final_utts = []
    cur_utt = ""
    for utt in utts:
        if calc_utt_length(cur_utt + utt) > token_max_n and calc_utt_length(cur_utt) > token_min_n:
            final_utts.append(cur_utt)
            cur_utt = ""
        cur_utt = cur_utt + utt
    if len(cur_utt) > 0:
        if should_merge(cur_utt) and len(final_utts) != 0:
            final_utts[-1] = final_utts[-1] + cur_utt
        else:
            final_utts.append(cur_utt)

    return final_utts


# Khmer sentence / clause punctuation (keep ។ attached to the phrase before it).
_KHMER_SENTENCE_BREAK = regex.compile(
    r"(?<=[។៕])\s*|(?<=[!?])(?=\s+[\u1780-\u17ff])|(?:\r?\n)+"
)
_KHMER_CLAUSE_BREAK = regex.compile(r"(?<=[៖])\s*")


def _khmer_grapheme_chunks(text: str, max_chars: int) -> list[str]:
    """Last resort: split by Unicode grapheme clusters, never inside a combining mark."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    graphemes = regex.findall(r"\X", text)
    chunks: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for g in graphemes:
        g_len = len(g)
        if cur and cur_len + g_len > max_chars:
            chunks.append("".join(cur))
            cur = [g]
            cur_len = g_len
        else:
            cur.append(g)
            cur_len += g_len
    if cur:
        chunks.append("".join(cur))
    return chunks


def split_khmer_paragraph(
    text: str,
    max_chars: int = 140,
    min_chars: int = 60,
    merge_len: int = 30,
) -> list[str]:
    """
    Split Khmer text only at sentence boundaries (។ ៕ …) and safe clause breaks.
    Avoids comma / fixed-width cuts that break words and combining marks.
    """
    text = text.strip()
    if not text:
        return []

    # Normalize stray spaces around Khmer punctuation
    text = regex.sub(r"\s*([។៕])\s*", r"\1", text)
    text = regex.sub(r"\s+", " ", text).strip()

    sentences: list[str] = []
    start = 0
    for match in _KHMER_SENTENCE_BREAK.finditer(text):
        end = match.end()
        piece = text[start:end].strip()
        if piece:
            sentences.append(piece)
        start = end
    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
    if not sentences:
        sentences = [text]

    merged: list[str] = []
    cur = ""
    for sent in sentences:
        if not sent:
            continue
        if len(sent) > max_chars:
            if cur:
                if len(cur) >= merge_len or not merged:
                    merged.append(cur)
                else:
                    merged[-1] = merged[-1] + cur
                cur = ""
            merged.extend(_split_khmer_oversized_clause(sent, max_chars, min_chars))
            continue

        trial = cur + sent
        if len(trial) <= max_chars:
            cur = trial
            continue

        if len(cur) >= min_chars:
            merged.append(cur)
            cur = sent
        elif merged:
            merged[-1] = merged[-1] + cur + sent
            cur = ""
        else:
            cur = trial

    if cur:
        if len(cur) < merge_len and merged:
            merged[-1] = merged[-1] + cur
        else:
            merged.append(cur)

    return [m.strip() for m in merged if m.strip()]


def _split_khmer_oversized_clause(clause: str, max_chars: int, min_chars: int) -> list[str]:
    """Split a long Khmer clause without breaking ។ or graphemes."""
    parts: list[str] = []
    start = 0
    for match in _KHMER_CLAUSE_BREAK.finditer(clause):
        end = match.end()
        piece = clause[start:end].strip()
        if piece:
            parts.append(piece)
        start = end
    tail = clause[start:].strip()
    if tail:
        parts.append(tail)
    if not parts:
        parts = [clause]

    out: list[str] = []
    for part in parts:
        if len(part) <= max_chars:
            out.append(part)
        elif " " in part:
            buf = ""
            for word in part.split():
                trial = f"{buf} {word}".strip() if buf else word
                if len(trial) > max_chars and buf:
                    out.append(buf)
                    buf = word
                else:
                    buf = trial
            if buf:
                if len(buf) > max_chars:
                    out.extend(_khmer_grapheme_chunks(buf, max_chars))
                else:
                    out.append(buf)
        else:
            out.extend(_khmer_grapheme_chunks(part, max_chars))

    merged: list[str] = []
    cur = ""
    for piece in out:
        if len(piece) > max_chars:
            if cur:
                merged.append(cur)
                cur = ""
            merged.extend(_khmer_grapheme_chunks(piece, max_chars))
            continue
        if len(cur) + len(piece) <= max_chars:
            cur += piece
        else:
            if cur:
                merged.append(cur)
            cur = piece
    if cur:
        merged.append(cur)
    return merged


def _char_window_for_lang(lang: str, max_tokens: int) -> int:
    return {"km": 36, "th": 42, "zh": 48}.get(lang, max(32, max_tokens * 2))


def refine_chunks_by_token_limit(
    chunks: list[str],
    tokenize,
    max_tokens: int = 45,
    lang: str = "en",
) -> list[str]:
    """Ensure every chunk is short enough for stable TTS (especially Khmer / long passages)."""
    if lang == "km":
        max_chars = min(160, max(100, max_tokens * 3))
        refined: list[str] = []
        for chunk in chunks:
            chunk = chunk.strip()
            if not chunk:
                continue
            if count_text_tokens(chunk, tokenize) <= max_tokens and len(chunk) <= max_chars:
                refined.append(chunk)
            else:
                refined.extend(split_khmer_paragraph(chunk, max_chars=max_chars))
        return refined

    refined: list[str] = []
    char_window = _char_window_for_lang(lang, max_tokens)

    def _push_piece(piece: str) -> None:
        piece = piece.strip()
        if not piece:
            return
        if count_text_tokens(piece, tokenize) <= max_tokens:
            refined.append(piece)
            return
        for sub in _split_by_char_windows(piece, char_window):
            if count_text_tokens(sub, tokenize) <= max_tokens:
                refined.append(sub)
            else:
                half = max(16, char_window // 2)
                refined.extend(_split_by_char_windows(sub, half))

    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        if count_text_tokens(chunk, tokenize) <= max_tokens:
            refined.append(chunk)
            continue

        if re.search(r"\s", chunk):
            words = chunk.split()
            buf = ""
            for word in words:
                trial = f"{buf} {word}".strip() if buf else word
                if count_text_tokens(trial, tokenize) > max_tokens and buf:
                    _push_piece(buf)
                    buf = word
                else:
                    buf = trial
            if buf:
                _push_piece(buf)
            continue

        _push_piece(chunk)

    return [c for c in refined if c.strip()]


def _split_by_char_windows(text: str, window: int) -> list[str]:
    text = text.strip()
    if not text:
        return []
    return [text[i : i + window] for i in range(0, len(text), window)]


# remove blank between chinese character
def replace_blank(text: str):
    out_str = []
    for i, c in enumerate(text):
        if c == " ":
            if (text[i + 1].isascii() and text[i + 1] != " ") and (text[i - 1].isascii() and text[i - 1] != " "):
                out_str.append(c)
        else:
            out_str.append(c)
    return "".join(out_str)


def clean_markdown(md_text: str) -> str:
    # 去除代码块 ``` ```（包括多行）
    md_text = re.sub(r"```.*?```", "", md_text, flags=re.DOTALL)

    # 去除内联代码 `code`
    md_text = re.sub(r"`[^`]*`", "", md_text)

    # 去除图片语法 ![alt](url)
    md_text = re.sub(r"!\[[^\]]*\]\([^\)]+\)", "", md_text)

    # 去除链接但保留文本 [text](url) -> text
    md_text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", md_text)

    # 替换无序列表符号
    md_text = re.sub(r"^(\s*)-\s+", r"\1", md_text, flags=re.MULTILINE)

    # 去除HTML标签
    md_text = re.sub(r"<[^>]+>", "", md_text)

    # 去除标题符号（#）
    md_text = re.sub(r"^#{1,6}\s*", "", md_text, flags=re.MULTILINE)

    # 去除多余空格和空行
    md_text = re.sub(r"\n\s*\n", "\n", md_text)  # 多余空行
    md_text = md_text.strip()

    return md_text


# Signs the TTS model cannot pronounce — they produce wrong/garbled voice or
# silence. Replaced with a space. Sentence terminators (. , ! ? ; : ។ ៕) and the
# (control) prefix parentheses are deliberately preserved.
_UNSPEAKABLE_CHARS = (
    "៖ៗ៘៙៚៛"            # Khmer decorative / non-lexical signs (keep ។ ៕)
    "*#^~|\\_=+<>[]{}@`"   # ASCII symbols with no spoken form
    "§©®™°•·●○■◆◇★☆※‣◦…"  # misc decorative glyphs + ellipsis handled below
    "→←↑↓⇒⇐↔«»"           # arrows and guillemets
)
_UNSPEAKABLE_TABLE = {ord(c): " " for c in _UNSPEAKABLE_CHARS if c != "…"}


def _collapse_punct_run(run: str) -> str:
    """Pick the strongest terminator from a run like '?....' or '!!!'."""
    if "?" in run:
        return "?"
    if "!" in run:
        return "!"
    return "."


def remove_unspeakable_symbols(text: str) -> str:
    """Strip signs the TTS model can't voice (e.g. ៖, *, #) and tidy punctuation.

    Should run *after* language-specific normalization so symbol expansion
    (e.g. Chinese math signs) is left untouched. Sentence terminators and the
    ``(control)`` prefix parentheses are preserved.
    """
    if not text:
        return text
    # Ellipsis -> period so the run-collapse below can fold "?…" / "?...." -> "?".
    text = text.replace("…", ".")
    text = text.translate(_UNSPEAKABLE_TABLE)
    # Collapse repeated end punctuation: "?....", "...", "!!!" -> a single mark.
    text = re.sub(r"[.?!]{2,}", lambda m: _collapse_punct_run(m.group()), text)
    # Collapse repeated commas / Khmer terminators left by paste or edits.
    text = re.sub(r",{2,}", ",", text)
    text = re.sub(r"។{2,}", "។", text)
    text = re.sub(r"៕{2,}", "៕", text)
    # Tidy spaces created by the removals: attach a floating mark to the word
    # before it ("word , word" -> "word, word") so it reads as a natural pause.
    text = re.sub(r"\s+([.,!?;:])", r"\1", text)
    # Drop leading orphan punctuation, but never the (control) prefix paren.
    text = re.sub(r"^[\s,.;:!?]+", "", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text


# Any letter or number in any script — used to tell speakable text from a paste
# of only symbols / punctuation (which would make the model emit garbage).
_SPEAKABLE_RE = regex.compile(r"[\p{L}\p{N}]")


def has_speakable_content(text: str) -> bool:
    """True if the text contains at least one letter or digit to actually voice."""
    return bool(_SPEAKABLE_RE.search(text or ""))


def clean_text(text):
    # 去除 Markdown 语法
    text = clean_markdown(text)
    # 匹配并移除表情符号
    text = regex.compile(r"\p{Emoji_Presentation}|\p{Emoji}\uFE0F", flags=regex.UNICODE).sub("", text)
    # 去除换行符
    text = text.replace("\n", " ")
    text = text.replace("\t", " ")
    text = text.replace("“", '"').replace("”", '"')
    return text


class TextNormalizer:
    def __init__(self, tokenizer=None):
        self.tokenizer = tokenizer
        self.zh_tn_model = Normalizer(lang="zh", operator="tn", remove_erhua=True)
        self.en_tn_model = Normalizer(lang="en", operator="tn")
        self.inflect_parser = inflect.engine()

    def normalize(self, text, split=False):
        # 去除 Markdown 语法，去除表情符号，去除换行符
        lang = detect_tts_language(text)
        text = clean_text(text)
        # wetext TN only supports zh/en; other scripts keep cleaned raw text
        if lang not in ("zh", "en"):
            if split is False:
                return text
            tokenize = self.tokenizer if self.tokenizer is not None else (lambda t: list(t))
            return split_paragraph(
                text,
                tokenize,
                lang=lang,
                token_max_n=50,
                token_min_n=25,
                merge_len=12,
                comma_split=True,
            )
        if lang == "zh":
            text = text.replace(
                "=", "等于"
            )  # 修复 ”550 + 320 等于 870 千卡。“ 被错误正则为 ”五百五十加三百二十等于八七十千卡.“
            if re.search(r"([\d$%^*_+≥≤≠×÷?=])", text):  # 避免 英文连字符被错误正则为减
                text = re.sub(r"(?<=[a-zA-Z0-9])-(?=\d)", " - ", text)  # 修复 x-2 被正则为 x负2
            text = self.zh_tn_model.normalize(text)
            text = replace_blank(text)
            text = replace_corner_mark(text)
            text = remove_bracket(text)
        else:
            text = self.en_tn_model.normalize(text)
            text = spell_out_number(text, self.inflect_parser)
        if split is False:
            return text
        tokenize = self.tokenizer if self.tokenizer is not None else (lambda t: list(t))
        return split_paragraph(
            text,
            tokenize,
            lang=lang,
            token_max_n=50,
            token_min_n=25,
            merge_len=12,
            comma_split=True,
        )
