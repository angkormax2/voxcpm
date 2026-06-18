import os
import sys
import re
import json
import tempfile
import numpy as np
from typing import Callable, Generator, Optional, Union
from huggingface_hub import snapshot_download
from .model.voxcpm import VoxCPMModel, LoRAConfig
from .model.voxcpm2 import VoxCPM2Model
from .model.utils import next_and_close
from .paths import resolve_default_voxcpm2_path

# Long passages degrade quality; synthesize sentence-by-sentence instead.
MAX_SINGLE_PASS_TARGET_TOKENS = 50
MAX_CHUNK_TARGET_TOKENS = 45
CHUNK_PAUSE_SEC = 0.15


def _parse_control_prefix(text: str) -> tuple[str, str]:
    """Split '(control)body' voice-design prefix from speakable body."""
    match = re.match(r"^(\([^)]+\)|（[^）]+）)([\s\S]*)$", text.strip())
    if match:
        return match.group(1), match.group(2).strip()
    return "", text.strip()


class VoxCPM:
    def __init__(
        self,
        voxcpm_model_path: str,
        zipenhancer_model_path: str | None = "iic/speech_zipenhancer_ans_multiloss_16k_base",
        enable_denoiser: bool = True,
        optimize: bool = True,
        device: str | None = None,
        lora_config: Optional[LoRAConfig] = None,
        lora_weights_path: Optional[str] = None,
        warmup: bool = True,
    ):
        """Initialize VoxCPM TTS pipeline.

        Args:
            voxcpm_model_path: Local filesystem path to the VoxCPM model assets
                (weights, configs, etc.). Typically the directory returned by
                a prior download step.
            zipenhancer_model_path: ModelScope acoustic noise suppression model
                id or local path. If None, denoiser will not be initialized.
            enable_denoiser: Whether to initialize the denoiser pipeline.
            optimize: Whether to optimize the model with torch.compile. True by default, but can be disabled for debugging.
            device: Runtime device. If set to ``None`` or ``"auto"``, VoxCPM
                will choose automatically (preferring CUDA, then MPS, then CPU).
                If set explicitly, that device is used or a clear error is raised.
            lora_config: LoRA configuration for fine-tuning. If lora_weights_path is
                provided without lora_config, a default config will be created.
            lora_weights_path: Path to pre-trained LoRA weights (.pth file or directory
                containing lora_weights.ckpt). If provided, LoRA weights will be loaded.
            warmup: Run a short generation pass to warm up the model after loading.
        """
        print(
            f"voxcpm_model_path: {voxcpm_model_path}, zipenhancer_model_path: {zipenhancer_model_path}, enable_denoiser: {enable_denoiser}",
            file=sys.stderr,
        )

        # If lora_weights_path is provided but no lora_config, create a default one
        if lora_weights_path is not None and lora_config is None:
            lora_config = LoRAConfig(
                enable_lm=True,
                enable_dit=True,
                enable_proj=False,
            )
            print(f"Auto-created default LoRAConfig for loading weights from: {lora_weights_path}", file=sys.stderr)

        # Determine model type from config.json architecture field
        config_path = os.path.join(voxcpm_model_path, "config.json")
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        arch = config.get("architecture", "voxcpm").lower()

        if arch == "voxcpm2":
            self.tts_model = VoxCPM2Model.from_local(
                voxcpm_model_path,
                optimize=optimize,
                device=device,
                lora_config=lora_config,
            )
            print("Loaded VoxCPM2Model", file=sys.stderr)
        elif arch == "voxcpm":
            self.tts_model = VoxCPMModel.from_local(
                voxcpm_model_path,
                optimize=optimize,
                device=device,
                lora_config=lora_config,
            )
            print("Loaded VoxCPMModel", file=sys.stderr)
        else:
            raise ValueError(f"Unsupported architecture: {arch}")

        # Load LoRA weights if path is provided
        if lora_weights_path is not None:
            print(f"Loading LoRA weights from: {lora_weights_path}", file=sys.stderr)
            loaded_keys, skipped_keys = self.tts_model.load_lora_weights(lora_weights_path)
            print(f"Loaded {len(loaded_keys)} LoRA parameters, skipped {len(skipped_keys)}", file=sys.stderr)

        self.text_normalizer = None
        self.denoiser = None
        if enable_denoiser and zipenhancer_model_path is not None:
            from .zipenhancer import ZipEnhancer

            self.denoiser = ZipEnhancer(zipenhancer_model_path)
        else:
            self.denoiser = None
        if optimize and warmup:
            self.run_warmup()

    @classmethod
    def from_pretrained(
        cls,
        hf_model_id: str | None = None,
        load_denoiser: bool = True,
        zipenhancer_model_id: str = "iic/speech_zipenhancer_ans_multiloss_16k_base",
        cache_dir: str = None,
        local_files_only: bool = False,
        optimize: bool = True,
        device: str | None = None,
        lora_config: Optional[LoRAConfig] = None,
        lora_weights_path: Optional[str] = None,
        warmup: bool = True,
        **kwargs,
    ):
        """Instantiate ``VoxCPM`` from a Hugging Face Hub snapshot.

        Args:
            hf_model_id: Explicit Hugging Face repository id (e.g. "org/repo") or local path.
            load_denoiser: Whether to initialize the denoiser pipeline.
            optimize: Whether to optimize the model with torch.compile. True by default, but can be disabled for debugging.
            zipenhancer_model_id: Denoiser model id or path for ModelScope
                acoustic noise suppression.
            cache_dir: Custom cache directory for the snapshot.
            local_files_only: If True, only use local files and do not attempt
                to download.
            device: Runtime device. Use ``None``/``"auto"`` for automatic
                fallback, or an explicit value such as ``"cpu"``, ``"mps"``,
                ``"cuda"``, or ``"cuda:0"``.
            lora_config: LoRA configuration for fine-tuning. If lora_weights_path is
                provided without lora_config, a default config will be created with
                enable_lm=True and enable_dit=True.
            lora_weights_path: Path to pre-trained LoRA weights (.pth file or directory
                containing lora_weights.ckpt). If provided, LoRA weights will be loaded
                after model initialization.
        Kwargs:
            Additional keyword arguments passed to the ``VoxCPM`` constructor.

        Returns:
            VoxCPM: Initialized instance whose ``voxcpm_model_path`` points to
            the downloaded snapshot directory.

        Raises:
            ValueError: If neither a valid ``hf_model_id`` nor a resolvable
                ``hf_model_id`` is provided.
        """
        repo_id = hf_model_id or resolve_default_voxcpm2_path()
        if not repo_id:
            raise ValueError("You must provide hf_model_id")

        # Load from local path if provided
        if os.path.isdir(repo_id):
            local_path = repo_id
        else:
            # Otherwise, try from_pretrained (Hub); exit on failure
            local_path = snapshot_download(
                repo_id=repo_id,
                cache_dir=cache_dir,
                local_files_only=local_files_only,
            )

        return cls(
            voxcpm_model_path=local_path,
            zipenhancer_model_path=zipenhancer_model_id if load_denoiser else None,
            enable_denoiser=load_denoiser,
            optimize=optimize,
            device=device,
            lora_config=lora_config,
            lora_weights_path=lora_weights_path,
            warmup=warmup,
            **kwargs,
        )

    def _count_text_tokens(self, text: str) -> int:
        return len(self.tts_model.text_tokenizer(text))

    def _preprocess_target_text(self, text: str, normalize: bool) -> str:
        from .utils.text_normalize import clean_text, detect_tts_language

        text = clean_text(text.replace("\n", " "))
        text = re.sub(r"\s+", " ", text).strip()
        lang = detect_tts_language(text)
        if normalize and lang in ("zh", "en"):
            if self.text_normalizer is None:
                from .utils.text_normalize import TextNormalizer

                self.text_normalizer = TextNormalizer(
                    tokenizer=self.tts_model.text_tokenizer.tokenizer
                )
            text = self.text_normalizer.normalize(text, split=False)
        return text

    def _split_long_target_text(self, text: str) -> list[str]:
        """Split long target text into short utterances for stable multilingual TTS."""
        from .utils.text_normalize import (
            detect_tts_language,
            refine_chunks_by_token_limit,
            split_khmer_paragraph,
            split_paragraph,
        )

        control, body = _parse_control_prefix(text)
        if not body:
            body = text

        lang = detect_tts_language(body)
        tokenize = self.tts_model.text_tokenizer

        if lang == "km":
            # Khmer: split only at ។ / ៕ (never commas or blind char windows).
            chunks = split_khmer_paragraph(body, max_chars=140, min_chars=60, merge_len=30)
            chunks = refine_chunks_by_token_limit(
                chunks, tokenize, max_tokens=MAX_CHUNK_TARGET_TOKENS, lang=lang
            )
        else:
            chunks = split_paragraph(
                body,
                tokenize,
                lang=lang,
                token_max_n=50,
                token_min_n=25,
                merge_len=12,
                comma_split=lang not in ("zh", "th"),
            )
            chunks = refine_chunks_by_token_limit(
                chunks, tokenize, max_tokens=MAX_CHUNK_TARGET_TOKENS, lang=lang
            )
        if control:
            chunks = [f"{control}{chunks[0]}"] + chunks[1:] if chunks else []
        return chunks or [text]

    def _should_split_target_text(self, text: str) -> bool:
        return self._count_text_tokens(text) > MAX_SINGLE_PASS_TARGET_TOKENS

    def prepare_synthesis_segments(self, text: str, normalize: bool = False) -> list[str]:
        """Return the exact text segments that will be spoken (for UI preview / logs)."""
        processed = self._preprocess_target_text(text, normalize=normalize)
        if self._should_split_target_text(processed):
            return self._split_long_target_text(processed)
        return [processed]

    def run_warmup(self, max_len: int = 10) -> None:
        """Run a short generation pass to warm up kernels / compiled graphs."""
        print("Warm up VoxCPMModel...", file=sys.stderr)
        self.tts_model.generate(
            target_text="Hello, this is the first test sentence.",
            max_len=max_len,
        )

    def generate(self, *args, status_callback: Callable[[str], None] | None = None, **kwargs) -> np.ndarray:
        gen = self._generate(*args, streaming=False, status_callback=status_callback, **kwargs)
        result = None
        for item in gen:
            if isinstance(item, dict) and item.get("kind") == "status":
                if status_callback:
                    status_callback(item["message"])
            else:
                result = item
        return result if result is not None else np.array([], dtype=np.float32)

    def generate_with_status(
        self, *args, **kwargs
    ) -> Generator[Union[dict, np.ndarray], None, None]:
        """Like generate() but yields ``{'kind':'status','message':...}`` before the final waveform."""
        return self._generate(*args, streaming=False, **kwargs)

    def generate_streaming(self, *args, **kwargs) -> Generator[np.ndarray, None, None]:
        return self._generate(*args, streaming=True, **kwargs)

    def _generate(
        self,
        text: str,
        prompt_wav_path: str = None,
        prompt_text: str = None,
        reference_wav_path: str = None,
        cfg_value: float = 2.0,
        inference_timesteps: int = 10,
        min_len: int = 2,
        max_len: int = 4096,
        normalize: bool = False,
        denoise: bool = False,
        retry_badcase: bool = True,
        retry_badcase_max_times: int = 3,
        retry_badcase_ratio_threshold: float = 6.0,
        streaming: bool = False,
        progress_callback=None,
        status_callback: Callable[[str], None] | None = None,
    ) -> Generator[Union[dict, np.ndarray], None, None]:
        """Synthesize speech for the given text and return a single waveform.

        Args:
            text: Input text to synthesize.
            prompt_wav_path: Path to prompt audio for continuation mode.
                Must be paired with ``prompt_text``.
            prompt_text: Text content corresponding to the prompt audio.
            reference_wav_path: Path to reference audio for voice cloning
                (structurally isolated via ref_audio tokens). Can be used
                alone or combined with ``prompt_wav_path`` + ``prompt_text``.
            cfg_value: Guidance scale for the generation model.
            inference_timesteps: Number of inference steps.
            min_len: Minimum audio length.
            max_len: Maximum token length during generation.
            normalize: Whether to run text normalization before generation.
            denoise: Whether to denoise the prompt/reference audio if a
                denoiser is available.
            retry_badcase: Whether to retry badcase.
            retry_badcase_max_times: Maximum number of times to retry badcase.
            retry_badcase_ratio_threshold: Threshold for audio-to-text ratio.
            streaming: Whether to return a generator of audio chunks.
        Returns:
            Generator of numpy.ndarray: 1D waveform array (float32) on CPU.
            Yields audio chunks for each generation step if ``streaming=True``,
            otherwise yields a single array containing the final audio.
        """
        if not isinstance(text, str) or not text.strip():
            raise ValueError("target text must be a non-empty string")

        if prompt_wav_path is not None:
            if not os.path.exists(prompt_wav_path):
                raise FileNotFoundError(f"prompt_wav_path does not exist: {prompt_wav_path}")

        if reference_wav_path is not None:
            if not os.path.exists(reference_wav_path):
                raise FileNotFoundError(f"reference_wav_path does not exist: {reference_wav_path}")

        if (prompt_wav_path is None) != (prompt_text is None):
            raise ValueError("prompt_wav_path and prompt_text must both be provided or both be None")

        is_v2 = isinstance(self.tts_model, VoxCPM2Model)
        if reference_wav_path is not None and not is_v2:
            raise ValueError("reference_wav_path is only supported with VoxCPM2 models")

        text = self._preprocess_target_text(text, normalize=normalize)
        temp_files = []

        try:
            actual_prompt_path = prompt_wav_path
            actual_ref_path = reference_wav_path

            if denoise and self.denoiser is not None:
                if prompt_wav_path is not None:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                        temp_files.append(tmp.name)
                    self.denoiser.enhance(prompt_wav_path, output_path=temp_files[-1])
                    actual_prompt_path = temp_files[-1]
                if reference_wav_path is not None:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                        temp_files.append(tmp.name)
                    self.denoiser.enhance(reference_wav_path, output_path=temp_files[-1])
                    actual_ref_path = temp_files[-1]

            if actual_prompt_path is not None or actual_ref_path is not None:
                if is_v2:
                    fixed_prompt_cache = self.tts_model.build_prompt_cache(
                        prompt_text=prompt_text,
                        prompt_wav_path=actual_prompt_path,
                        reference_wav_path=actual_ref_path,
                    )
                else:
                    fixed_prompt_cache = self.tts_model.build_prompt_cache(
                        prompt_text=prompt_text,
                        prompt_wav_path=actual_prompt_path,
                    )
            else:
                fixed_prompt_cache = None

            target_chunks = (
                self._split_long_target_text(text)
                if self._should_split_target_text(text)
                else [text]
            )
            if len(target_chunks) > 1:
                print(
                    f"Long input split into {len(target_chunks)} segments for stable synthesis.",
                    file=sys.stderr,
                )

            cache_kwargs = {}
            if progress_callback is not None and isinstance(self.tts_model, VoxCPM2Model):
                cache_kwargs["progress_callback"] = progress_callback

            sample_rate = self.tts_model.sample_rate
            pause_samples = int(CHUNK_PAUSE_SEC * sample_rate)
            segment_wavs: list[np.ndarray] = []

            n_chunks = len(target_chunks)
            rolling_cache = fixed_prompt_cache
            use_voice_continuation = n_chunks > 1 and is_v2
            if n_chunks > 1 and is_v2:
                print(
                    "Multi-segment mode: chaining audio so the same voice continues across splits.",
                    file=sys.stderr,
                )

            def _emit_status(message: str) -> None:
                if status_callback:
                    status_callback(message)
                yield {"kind": "status", "message": message}

            for chunk_idx, chunk_text in enumerate(target_chunks):
                for ev in _emit_status(
                    f"Segment {chunk_idx + 1}/{n_chunks} — synthesizing (one continuous voice)…"
                ):
                    yield ev

                chunk_cache = dict(cache_kwargs)
                if progress_callback is not None:

                    def chunk_callback(step, total, _idx=chunk_idx, _n=n_chunks):
                        if total <= 0:
                            return
                        overall_step = _idx * total + step
                        overall_total = _n * total
                        progress_callback(overall_step, overall_total)
                        if status_callback and (
                            step == 1
                            or step == total
                            or step % max(1, total // 6) == 0
                        ):
                            pct = 100.0 * overall_step / overall_total
                            status_callback(
                                f"Overall {pct:.0f}% — segment {_idx + 1}/{_n}, "
                                f"step {step}/{total}"
                            )

                    chunk_cache["progress_callback"] = chunk_callback

                prompt_for_chunk = rolling_cache if use_voice_continuation else fixed_prompt_cache

                generate_result = self.tts_model._generate_with_prompt_cache(
                    target_text=chunk_text,
                    prompt_cache=prompt_for_chunk,
                    min_len=min_len,
                    max_len=max_len,
                    inference_timesteps=inference_timesteps,
                    cfg_value=cfg_value,
                    retry_badcase=retry_badcase,
                    retry_badcase_max_times=retry_badcase_max_times,
                    retry_badcase_ratio_threshold=retry_badcase_ratio_threshold,
                    streaming=streaming,
                    **chunk_cache,
                )

                if streaming:
                    try:
                        for wav in generate_result:
                            yield wav.squeeze(0).cpu().numpy()
                    finally:
                        generate_result.close()
                    
                    if chunk_idx < n_chunks - 1 and pause_samples > 0:
                        yield np.zeros(pause_samples, dtype=np.float32)
                    continue

                wav, _, pred_audio_feat = next_and_close(generate_result)
                segment = wav.squeeze(0).cpu().numpy()
                segment_wavs.append(segment)

                if (
                    use_voice_continuation
                    and chunk_idx < n_chunks - 1
                    and isinstance(self.tts_model, VoxCPM2Model)
                ):
                    rolling_cache = self.tts_model.merge_prompt_cache(
                        rolling_cache,
                        chunk_text,
                        pred_audio_feat,
                    )
                    for ev in _emit_status(
                        f"Segment {chunk_idx + 1}/{n_chunks} done — carrying voice into next part…"
                    ):
                        yield ev

                if chunk_idx < n_chunks - 1 and pause_samples > 0:
                    segment_wavs.append(np.zeros(pause_samples, dtype=segment.dtype))

            if not streaming:
                for ev in _emit_status("All segments complete — decoding final audio…"):
                    yield ev
                yield np.concatenate(segment_wavs) if segment_wavs else np.array([], dtype=np.float32)

        finally:
            for tmp_path in temp_files:
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass

    # ------------------------------------------------------------------ #
    # LoRA Interface (delegated to VoxCPMModel)
    # ------------------------------------------------------------------ #
    def load_lora(self, lora_weights_path: str) -> tuple:
        """Load LoRA weights from a checkpoint file.

        Args:
            lora_weights_path: Path to LoRA weights (.pth file or directory
                containing lora_weights.ckpt).

        Returns:
            tuple: (loaded_keys, skipped_keys) - lists of loaded and skipped parameter names.

        Raises:
            RuntimeError: If model was not initialized with LoRA config.
        """
        if self.tts_model.lora_config is None:
            raise RuntimeError(
                "Cannot load LoRA weights: model was not initialized with LoRA config. "
                "Please reinitialize with lora_config or lora_weights_path parameter."
            )
        return self.tts_model.load_lora_weights(lora_weights_path)

    def unload_lora(self):
        """Unload LoRA by resetting all LoRA weights to initial state (effectively disabling LoRA)."""
        self.tts_model.reset_lora_weights()

    def set_lora_enabled(self, enabled: bool):
        """Enable or disable LoRA layers without unloading weights.

        Args:
            enabled: If True, LoRA layers are active; if False, only base model is used.
        """
        self.tts_model.set_lora_enabled(enabled)

    def get_lora_state_dict(self) -> dict:
        """Get current LoRA parameters state dict.

        Returns:
            dict: State dict containing all LoRA parameters (lora_A, lora_B).
        """
        return self.tts_model.get_lora_state_dict()

    @property
    def lora_enabled(self) -> bool:
        """Check if LoRA is currently configured."""
        return self.tts_model.lora_config is not None
