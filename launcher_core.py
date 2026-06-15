"""VoxCPM2 Studio — setup checks, install, and server control (no GUI)."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from studio_branding import STUDIO_NAME

from license_manager import require_valid_license

PROJECT_ROOT = Path(__file__).resolve().parent
VENV_PYTHON = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
STARTER_KIT = PROJECT_ROOT / "starter-kit"
MODEL_CONFIG = PROJECT_ROOT / "VoxCPM2" / "config.json"
TORCH_CUDA_INDEX = "https://download.pytorch.org/whl/cu126"
TORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"
WINGET_PYTHON_ID = "Python.Python.3.12"
WINGET_NODE_ID = "OpenJS.NodeJS.LTS"
HF_VOXCPM2_REPO = "openbmb/VoxCPM2"

LogFn = Callable[[str], None]


@dataclass
class CheckResult:
    key: str
    label: str
    ok: bool
    detail: str
    required: bool = True
    fix_hint: str = ""


def _run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    log: LogFn | None = None,
) -> int:
    if log:
        log(f"$ {' '.join(cmd)}")
    proc = subprocess.run(
        cmd,
        cwd=str(cwd or PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=_win_no_window(),
    )
    if log:
        if proc.stdout.strip():
            for line in proc.stdout.strip().splitlines():
                log(line)
        if proc.stderr.strip():
            for line in proc.stderr.strip().splitlines():
                log(line)
    return proc.returncode


def _which(name: str) -> str | None:
    return shutil.which(name)


def _winget_available() -> bool:
    return _which("winget") is not None


def _refresh_windows_path() -> None:
    """Prepend common winget install paths so new Python/Node are found."""
    if sys.platform != "win32":
        return
    local = os.environ.get("LOCALAPPDATA", "")
    candidates = [
        os.path.join(local, "Programs", "Python", "Python312"),
        os.path.join(local, "Programs", "Python", "Python312", "Scripts"),
        os.path.join(local, "Programs", "Python", "Python311"),
        os.path.join(local, "Programs", "Python", "Python311", "Scripts"),
        r"C:\Program Files\nodejs",
        r"C:\Program Files\Python312",
        r"C:\Program Files\Python312\Scripts",
    ]
    extras = [p for p in candidates if os.path.isdir(p)]
    if extras:
        os.environ["PATH"] = os.pathsep.join(extras + [os.environ.get("PATH", "")])


def _winget_install(package_id: str, log: LogFn) -> bool:
    if not _winget_available():
        return False
    log(f"Installing {package_id} via winget (may prompt for admin)…")
    rc = _run(
        [
            "winget",
            "install",
            "-e",
            "--id",
            package_id,
            "--accept-package-agreements",
            "--accept-source-agreements",
        ],
        log=log,
    )
    _refresh_windows_path()
    return rc == 0


def ensure_prerequisites(log: LogFn) -> bool:
    """Ensure Python and Node.js exist; on Windows try winget if missing."""
    missing_py = not _which("python")
    missing_node = not _which("node")
    if not missing_py and not missing_node:
        return True

    if sys.platform != "win32":
        if missing_py:
            log("Python not found. Install Python 3.10+ from https://www.python.org/downloads/")
            return False
        if missing_node:
            log("Node.js not found. Install from https://nodejs.org/")
            return False
        return True

    if not _winget_available():
        log("winget not found. Install Python 3.10+ and Node.js 18+ manually.")
        return False

    if missing_py and not _winget_install(WINGET_PYTHON_ID, log):
        log("Python install failed. Install from https://www.python.org/downloads/")
        return False
    if missing_py and not _which("python"):
        log("Python installed but not on PATH. Restart the launcher or log in again.")
        return False

    if missing_node and not _winget_install(WINGET_NODE_ID, log):
        log("Node.js install failed. Install from https://nodejs.org/")
        return False
    if missing_node and not _which("node"):
        log("Node.js installed but not on PATH. Restart the launcher or log in again.")
        return False

    return True


def _run_live(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    log: LogFn | None = None,
) -> int:
    if log:
        log(f"$ {' '.join(cmd)}")
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd or PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=_win_no_window(),
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        if log:
            log(line.rstrip())
    return proc.wait()


def download_voxcpm2_weights(log: LogFn) -> bool:
    """Download VoxCPM2 weights into VoxCPM2/ if not already present."""
    if MODEL_CONFIG.is_file():
        log("VoxCPM2 weights already present.")
        return True
    if not VENV_PYTHON.is_file():
        log("Cannot download model — Python venv not ready.")
        return False

    dest = PROJECT_ROOT / "VoxCPM2"
    dest.mkdir(parents=True, exist_ok=True)
    log("Downloading VoxCPM2 weights (first time only, several GB)…")
    log("This may take several minutes depending on your connection.")

    script = (
        "from huggingface_hub import snapshot_download\n"
        f"dest = r'{dest}'\n"
        f"snapshot_download(repo_id='{HF_VOXCPM2_REPO}', local_dir=dest)\n"
        "print('Download complete:', dest)\n"
    )
    rc = _run_live(
        [str(VENV_PYTHON), "-c", script],
        log=log,
    )
    if rc != 0 or not MODEL_CONFIG.is_file():
        log("Model download failed. Check your internet connection and try Setup again.")
        return False
    log("VoxCPM2 weights downloaded.")
    return True


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _win_no_window() -> int:
    if sys.platform == "win32":
        return subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    return 0


def _node_exe() -> str | None:
    return _which("node")


def _next_dev_cmd() -> list[str] | None:
    node = _node_exe()
    if not node:
        return None
    next_bin = STARTER_KIT / "node_modules" / "next" / "dist" / "bin" / "next"
    if not next_bin.is_file():
        return None
    return [node, str(next_bin), "dev", "--turbopack"]


def run_checks() -> list[CheckResult]:
    results: list[CheckResult] = []

    py = _which("python") or sys.executable
    py_ver = ""
    if py:
        try:
            py_ver = subprocess.check_output(
                [py, "--version"], text=True, encoding="utf-8", errors="replace"
            ).strip()
        except Exception:
            py_ver = "unknown"
    results.append(
        CheckResult(
            key="python",
            label="Python",
            ok=bool(py),
            detail=py_ver or "Not found",
            fix_hint="Install Python 3.10+ or run Setup",
        )
    )

    node = _which("node")
    node_ver = ""
    if node:
        try:
            node_ver = subprocess.check_output(
                ["node", "-v"], text=True, encoding="utf-8", errors="replace"
            ).strip()
        except Exception:
            node_ver = "found"
    results.append(
        CheckResult(
            key="nodejs",
            label="Node.js",
            ok=bool(node),
            detail=node_ver or "Not found",
            fix_hint="Install Node.js 18+ from nodejs.org",
        )
    )

    gpu_name = ""
    has_nvidia = False
    if _which("nvidia-smi"):
        try:
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader,nounits"],
                text=True,
                encoding="utf-8",
                errors="replace",
            ).strip()
            if out:
                has_nvidia = True
                gpu_name = out.splitlines()[0].strip()
        except Exception:
            pass
    results.append(
        CheckResult(
            key="gpu",
            label="NVIDIA GPU",
            ok=has_nvidia,
            detail=gpu_name or "Not detected (CPU mode)",
            required=False,
            fix_hint="Optional — install NVIDIA driver for GPU speed",
        )
    )

    venv_ok = VENV_PYTHON.is_file()
    results.append(
        CheckResult(
            key="venv",
            label="Python venv",
            ok=venv_ok,
            detail=str(VENV_PYTHON.parent.parent) if venv_ok else "Missing .venv",
            fix_hint="Click Run setup",
        )
    )

    torch_ok = False
    torch_detail = "Not installed"
    if venv_ok:
        try:
            code = (
                "import torch; print(torch.__version__); "
                "print('cuda' if torch.cuda.is_available() else 'cpu')"
            )
            out = subprocess.check_output(
                [str(VENV_PYTHON), "-c", code],
                text=True,
                encoding="utf-8",
                errors="replace",
            ).strip().splitlines()
            if out:
                torch_detail = f"{out[0]} ({out[1] if len(out) > 1 else '?'})"
                torch_ok = True
        except Exception as exc:
            torch_detail = str(exc)
    results.append(
        CheckResult(
            key="torch",
            label="PyTorch",
            ok=torch_ok,
            detail=torch_detail,
            fix_hint="Click Run setup",
        )
    )

    npm_ok = (STARTER_KIT / "node_modules").is_dir()
    results.append(
        CheckResult(
            key="npm",
            label="Frontend packages",
            ok=npm_ok,
            detail="node_modules present" if npm_ok else "Run npm install",
            fix_hint="Click Run setup",
        )
    )

    model_ok = MODEL_CONFIG.is_file()
    results.append(
        CheckResult(
            key="model",
            label="VoxCPM2 weights",
            ok=model_ok,
            detail="Local model found" if model_ok else "Not downloaded",
            required=False,
            fix_hint="Run Setup to download weights",
        )
    )

    api_up = _port_open(8000)
    ui_up = _port_open(3000)
    results.append(
        CheckResult(
            key="servers",
            label="Servers",
            ok=api_up and ui_up,
            detail=(
                f"API {'up' if api_up else 'down'} · UI {'up' if ui_up else 'down'}"
            ),
            required=False,
            fix_hint="Click Start Studio",
        )
    )

    return results


def required_ready(checks: list[CheckResult]) -> bool:
    return all(c.ok for c in checks if c.required)


def wait_for_servers(timeout_sec: int = 90) -> bool:
    for _ in range(timeout_sec):
        if _port_open(8000) and _port_open(3000):
            return True
        time.sleep(1)
    return False


def bootstrap_setup(manager: StudioManager) -> bool:
    """Install dependencies if needed — no license required."""
    if not ensure_prerequisites(manager.log):
        return False
    manager.log("Checking requirements…")
    checks = run_checks()
    if not required_ready(checks):
        manager.log("Running first-time setup…")
        if not manager.setup():
            manager.log("Setup failed.")
            return False
    manager.log("Setup check complete.")
    return True


def bootstrap_studio(manager: StudioManager, *, open_browser: bool = True) -> bool:
    """Setup if needed, then start servers (valid license required to start)."""
    if not bootstrap_setup(manager):
        return False
    if not manager.start(open_browser=open_browser):
        return False
    manager.log("Waiting for servers…")
    if wait_for_servers():
        manager.log(f"{STUDIO_NAME} is ready.")
        return True
    manager.log("Servers started but not fully ready yet — check the log.")
    return True


class StudioManager:
    def __init__(self, log: LogFn | None = None) -> None:
        self._log = log or (lambda _m: None)
        self._api_proc: subprocess.Popen | None = None
        self._ui_proc: subprocess.Popen | None = None

    @property
    def running(self) -> bool:
        api = self._api_proc is not None and self._api_proc.poll() is None
        ui = self._ui_proc is not None and self._ui_proc.poll() is None
        return api or ui or (_port_open(8000) and _port_open(3000))

    def _start_reader(self, proc: subprocess.Popen, prefix: str) -> None:
        import threading

        def _reader() -> None:
            if proc.stdout is None:
                return
            for line in proc.stdout:
                self.log(f"[{prefix}] {line.rstrip()}")

        threading.Thread(target=_reader, daemon=True).start()

    def _stop_proc(self, proc: subprocess.Popen | None, name: str) -> None:
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=6)
        except Exception:
            proc.kill()
        self.log(f"Stopped {name}.")

    def log(self, msg: str) -> None:
        self._log(msg)

    def stop(self) -> None:
        self._stop_proc(self._api_proc, "API")
        self._api_proc = None
        self._stop_proc(self._ui_proc, "UI")
        self._ui_proc = None

        for port, name in ((8000, "API"), (3000, "UI")):
            if not _port_open(port):
                continue
            try:
                out = subprocess.check_output(
                    ["netstat", "-ano"],
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                for line in out.splitlines():
                    if f":{port} " in line and "LISTENING" in line:
                        pid = line.split()[-1]
                        subprocess.run(
                            ["taskkill", "/F", "/PID", pid],
                            capture_output=True,
                        )
                        self.log(f"Stopped {name} on port {port} (PID {pid})")
            except Exception as exc:
                self.log(f"Could not free port {port}: {exc}")

        self.log("Servers stopped.")

    def setup(self) -> bool:
        self.log("=== Setup started ===")
        if not ensure_prerequisites(self.log):
            return False
        checks = run_checks()
        has_nvidia = next((c.ok for c in checks if c.key == "gpu"), False)

        if not VENV_PYTHON.is_file():
            self.log("Creating virtual environment…")
            py = _which("python") or sys.executable
            if _which("uv"):
                if _run(["uv", "venv", str(PROJECT_ROOT / ".venv"), "--python", py], log=self.log) != 0:
                    if _run([py, "-m", "venv", str(PROJECT_ROOT / ".venv")], log=self.log) != 0:
                        self.log("Failed to create .venv")
                        return False
            elif _run([py, "-m", "venv", str(PROJECT_ROOT / ".venv")], log=self.log) != 0:
                self.log("Failed to create .venv")
                return False

        pip = [str(VENV_PYTHON), "-m", "pip"]

        torch_ok = False
        try:
            subprocess.check_call(
                [str(VENV_PYTHON), "-c", "import torch"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            torch_ok = True
        except Exception:
            pass

        if not torch_ok:
            index = TORCH_CUDA_INDEX if has_nvidia else TORCH_CPU_INDEX
            self.log(f"Installing PyTorch ({'CUDA' if has_nvidia else 'CPU'})…")
            _run(
                pip + ["install", "torch", "torchaudio", "--index-url", index],
                log=self.log,
            )

        self.log("Installing Python package (editable)…")
        if _run(pip + ["install", "-e", "."], log=self.log) != 0:
            self.log("Python install failed.")
            return False

        if not download_voxcpm2_weights(self.log):
            return False

        if not _which("npm"):
            self.log("Node.js/npm missing — run Setup again after installing Node.js.")
            return False

        self.log("Installing frontend packages (npm)…")
        if (
            _run(
                ["npm", "install", "--no-audit", "--no-fund", "--loglevel=error"],
                cwd=STARTER_KIT,
                log=self.log,
            )
            != 0
        ):
            self.log("npm install failed.")
            return False

        self.log("=== Setup finished ===")
        return True

    def start(self, open_browser: bool = True) -> bool:
        try:
            access = require_valid_license()
            self.log(access.message)
        except RuntimeError as exc:
            self.log(f"Cannot start — {exc}")
            return False
        if self.running:
            self.log("Servers already running.")
            return True

        checks = run_checks()
        if not required_ready(checks):
            self.log("Requirements not met. Run setup first.")
            return False

        if _port_open(8000) or _port_open(3000):
            self.log("Ports 8000/3000 in use — stopping old processes…")
            self.stop()
            time.sleep(1)

        self.log("Starting API + UI (no CMD windows)…")
        flags = _win_no_window()
        child_env = os.environ.copy()
        child_env["PYTHONUTF8"] = "1"
        child_env["PYTHONIOENCODING"] = "utf-8"
        popen_kw = dict(
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=flags,
            env=child_env,
        )

        self._api_proc = subprocess.Popen(
            [str(VENV_PYTHON), str(PROJECT_ROOT / "api.py")],
            cwd=str(PROJECT_ROOT),
            **popen_kw,
        )
        self._start_reader(self._api_proc, "API")

        ui_cmd = _next_dev_cmd()
        if not ui_cmd:
            self.log("Frontend not ready — run Setup first (npm install).")
            self._stop_proc(self._api_proc, "API")
            self._api_proc = None
            return False

        self._ui_proc = subprocess.Popen(
            ui_cmd,
            cwd=str(STARTER_KIT),
            **popen_kw,
        )
        self._start_reader(self._ui_proc, "UI")

        if open_browser:
            import threading

            def _open() -> None:
                time.sleep(5)
                if _port_open(3000):
                    import webbrowser

                    webbrowser.open("http://localhost:3000/home")

            threading.Thread(target=_open, daemon=True).start()

        self.log(f"{STUDIO_NAME} starting — UI: http://localhost:3000/home")
        self.log("API: http://127.0.0.1:8000")
        return True
