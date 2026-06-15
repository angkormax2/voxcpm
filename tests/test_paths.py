from pathlib import Path

from voxcpm.paths import HF_DEFAULT_VOXCPM2, resolve_default_voxcpm2_path

ROOT = Path(__file__).resolve().parents[1]


def test_resolve_local_voxcpm2_when_present():
    local = ROOT / "VoxCPM2"
    if not (local / "config.json").is_file():
        return
    assert resolve_default_voxcpm2_path(ROOT) == str(local.resolve())


def test_resolve_hf_id_when_no_local_weights():
    empty = ROOT / "tests" / "_nonexistent_model_dir"
    assert resolve_default_voxcpm2_path(empty) == HF_DEFAULT_VOXCPM2
