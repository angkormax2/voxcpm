"""Resolve default VoxCPM2 model locations (local weights vs Hugging Face)."""

from __future__ import annotations

from pathlib import Path

HF_DEFAULT_VOXCPM2 = "openbmb/VoxCPM2"


def _is_voxcpm2_model_dir(path: Path) -> bool:
    return (path / "config.json").is_file()


def resolve_default_voxcpm2_path(*search_roots: Path | str | None) -> str:
    """Return the first usable local VoxCPM2 directory, else the HF repo id."""
    roots: list[Path] = []
    for root in search_roots:
        if root is None:
            continue
        roots.append(Path(root))

    if not roots:
        roots.append(Path.cwd())

    seen: set[Path] = set()
    for root in roots:
        root = root.resolve()
        for candidate in (
            root / "VoxCPM2",
            root / "pretrained_models" / "VoxCPM2",
            root / "models" / "openbmb__VoxCPM2",
        ):
            key = candidate.resolve()
            if key in seen:
                continue
            seen.add(key)
            if _is_voxcpm2_model_dir(key):
                return str(key)
    return HF_DEFAULT_VOXCPM2
