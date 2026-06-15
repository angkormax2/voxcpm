"""Windows CUDA PATH helpers — call before importing torch."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _prepend_path(path: str, env: dict[str, str]) -> None:
    if not path or not os.path.isdir(path):
        return
    current = env.get("PATH", "")
    prefix = f"{path};"
    if path.lower() not in current.lower():
        env["PATH"] = prefix + current


def ensure_cuda_paths() -> None:
    """Ensure Windows can load the NVIDIA driver DLLs for PyTorch."""
    if sys.platform != "win32":
        return

    env = os.environ
    system_root = env.get("SystemRoot", r"C:\Windows")
    _prepend_path(os.path.join(system_root, "System32"), env)
    _prepend_path(os.path.join(system_root, "SysWOW64"), env)

    for base in (
        Path(r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA"),
        Path(r"C:\Program Files\NVIDIA Corporation\NVSMI"),
    ):
        if not base.is_dir():
            continue
        if base.name == "CUDA":
            for cuda_home in sorted(base.iterdir(), reverse=True):
                _prepend_path(str(cuda_home / "bin"), env)
        else:
            _prepend_path(str(base), env)


def describe_cuda_status() -> dict[str, object]:
    """Return a small CUDA diagnostics dict (imports torch)."""
    import torch

    info: dict[str, object] = {
        "pytorch_version": torch.__version__,
        "cuda_available": torch.cuda.is_available(),
        "device_count": torch.cuda.device_count(),
    }
    if torch.cuda.is_available():
        info["device_name"] = torch.cuda.get_device_name(0)
    else:
        err = getattr(torch.cuda, "_lazy_init_error", None)
        if err is not None:
            info["cuda_error"] = str(err)
    return info
