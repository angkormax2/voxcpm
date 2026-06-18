"""VoxCPM2 Studio — setup checks, install, and server control (no GUI)."""

from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import tempfile
import urllib.request
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
PYTHON_312_INSTALLER_URL = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
WINGET_UNSUPPORTED_PYTHON_IDS = tuple(f"Python.Python.3.{minor}" for minor in range(13, 20))
WINGET_LEGACY_NODE_IDS = tuple(f"OpenJS.NodeJS.{minor}" for minor in range(10, 18))

_DL_BAR_RE = re.compile(
    r"[#=\-\.█▇▆▅▄▃▂▁]+\s+([\d.]+)\s*/\s*([\d.]+)\s*(MB|KB|GB|B)",
    re.I,
)
_WINGET_DL_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(KB|MB|GB)\s*/\s*(\d+(?:\.\d+)?)\s*(KB|MB|GB)",
    re.I,
)
_PCT_RE = re.compile(r"(\d{1,3})%")
HF_VOXCPM2_REPO = "openbmb/VoxCPM2"
STUDIO_PYTHON_MIN = (3, 10)
STUDIO_PYTHON_MAX = (3, 12)
STUDIO_NODE_MIN = (18, 0)
STUDIO_PACKAGE_VERSION = "2.0.0"

LogFn = Callable[[str], None]


def center_tk_window(
    window,
    *,
    width: int | None = None,
    height: int | None = None,
    parent=None,
) -> None:
    """Place a Tk window at the center of the screen or over a parent window."""
    window.update_idletasks()
    w = width if width is not None else window.winfo_width()
    h = height if height is not None else window.winfo_height()
    if w <= 1:
        w = window.winfo_reqwidth()
    if h <= 1:
        h = window.winfo_reqheight()
    if parent is not None:
        parent.update_idletasks()
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - w) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - h) // 2)
    else:
        sw = window.winfo_screenwidth()
        sh = window.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
    window.geometry(f"{w}x{h}+{x}+{y}")


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
    env: dict[str, str] | None = None,
) -> int:
    if log:
        log(f"$ {' '.join(cmd)}")
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd or PROJECT_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=run_env,
            **_subprocess_hide_kwargs(),
        )
    except OSError as exc:
        if log:
            log(f"Failed to run command: {exc}")
        return 127
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


def _find_node_exe() -> str | None:
    """Full path to node.exe — prefer newest supported version (Windows-safe)."""
    _refresh_windows_path()
    local = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    candidates = [
        _which("node"),
        os.path.join(program_files, "nodejs", "node.exe"),
        os.path.join(program_files_x86, "nodejs", "node.exe"),
        r"C:\Program Files\nodejs\node.exe",
        os.path.join(local, "Programs", "nodejs", "node.exe"),
    ]
    seen: set[str] = set()
    best: str | None = None
    best_ver: tuple[int, int] | None = None
    for exe in candidates:
        if not exe:
            continue
        path = str(Path(exe).resolve())
        if path in seen or not Path(path).is_file():
            continue
        seen.add(path)
        ver = _node_version_tuple(path)
        if not _node_supported(ver):
            continue
        if best is None or (ver and best_ver and ver > best_ver):
            best = path
            best_ver = ver
    return best


def _progress_bar(pct: float, width: int = 20) -> str:
    pct = max(0.0, min(100.0, pct))
    filled = int(width * pct / 100)
    return "#" * filled + "-" * (width - filled)


def _try_parse_download_progress(line: str) -> tuple[int, str] | None:
    line = line.strip()
    if not line:
        return None

    m = _DL_BAR_RE.search(line) or _WINGET_DL_RE.search(line)
    if m:
        done_s, total_s, unit = m.group(1), m.group(2), m.group(3).upper()
        done, total = float(done_s), float(total_s)
        if total > 0:
            pct = min(99, int(100 * done / total))
            bar = _progress_bar(pct)
            return pct, f"{bar} {done_s}/{total_s} {unit} | {line[:48]}"

    if any(x in line.lower() for x in ("download", "mb", "kb", "gb", "extract", "installing", "reify")):
        m = _PCT_RE.search(line)
        if m:
            pct = min(99, int(m.group(1)))
            bar = _progress_bar(pct)
            short = line if len(line) <= 64 else line[:61] + "…"
            return pct, f"{bar} {short}"
    return None


def _node_version_tuple(node_exe: str) -> tuple[int, int] | None:
    try:
        out = subprocess.check_output(
            [node_exe, "-v"],
            text=True,
            encoding="utf-8",
            errors="replace",
            **_subprocess_hide_kwargs(),
        ).strip()
        match = re.match(r"v?(\d+)\.(\d+)", out)
        if match:
            return int(match.group(1)), int(match.group(2))
    except Exception:
        pass
    return None


def _node_supported(ver: tuple[int, int] | None) -> bool:
    if ver is None:
        return False
    return ver >= STUDIO_NODE_MIN


def _npm_env() -> dict[str, str]:
    """PATH for npm child processes (postinstall scripts spawn npm again on Windows)."""
    env = os.environ.copy()
    node = _find_node_exe()
    if not node:
        return env
    node_dir = str(Path(node).parent)
    prepend: list[str] = [node_dir]
    npm_bin = Path(node_dir) / "node_modules" / "npm" / "bin"
    if npm_bin.is_dir():
        prepend.append(str(npm_bin))
    starter_bin = STARTER_KIT / "node_modules" / ".bin"
    if starter_bin.is_dir():
        prepend.append(str(starter_bin))
    path = env.get("PATH", "")
    env["PATH"] = os.pathsep.join(prepend) + (os.pathsep + path if path else "")
    return env


def _npm_command(*args: str) -> list[str] | None:
    """Build npm argv that works with CREATE_NO_WINDOW on Windows."""
    node = _find_node_exe()
    if not node:
        return None
    node_dir = Path(node).parent
    npm_cli = node_dir / "node_modules" / "npm" / "bin" / "npm-cli.js"
    if npm_cli.is_file():
        return [node, str(npm_cli), *args]
    for name in ("npm.cmd", "npm.exe"):
        script = node_dir / name
        if script.is_file():
            if sys.platform == "win32" and name.endswith(".cmd"):
                return ["cmd.exe", "/d", "/c", str(script), *args]
            return [str(script), *args]
    if sys.platform == "win32":
        npm = _which("npm")
        if npm and (npm.lower().endswith(".cmd") or Path(npm).suffix.lower() == ".cmd"):
            return ["cmd.exe", "/d", "/c", npm, *args]
        npm_cmd = node_dir / "npm.cmd"
        if npm_cmd.is_file():
            return ["cmd.exe", "/d", "/c", str(npm_cmd), *args]
        return None
    npm = _which("npm")
    if npm:
        return [npm, *args]
    return None


def _run_npm(*args: str, cwd: Path | None = None, log: LogFn | None = None) -> int:
    cmd = _npm_command(*args)
    if not cmd:
        if log:
            log("npm not found — install Node.js LTS and run Setup again.")
        return 127
    return _run_live(
        cmd,
        cwd=cwd or STARTER_KIT,
        log=log,
        env=_npm_env(),
        parse_progress=True,
    )


def _node_exe() -> str | None:
    return _find_node_exe()


def _python_version_tuple(exe: str) -> tuple[int, int] | None:
    try:
        out = subprocess.check_output(
            [exe, "-c", "import sys; print(sys.version_info[0], sys.version_info[1])"],
            text=True,
            encoding="utf-8",
            errors="replace",
            **_subprocess_hide_kwargs(),
        ).strip()
        major, minor = out.split()[:2]
        return int(major), int(minor)
    except Exception:
        return None


def _python_supported(ver: tuple[int, int] | None) -> bool:
    if ver is None:
        return False
    return STUDIO_PYTHON_MIN <= ver <= STUDIO_PYTHON_MAX


def _python_label(exe: str) -> str:
    ver = _python_version_tuple(exe)
    if ver:
        return f"Python {ver[0]}.{ver[1]} ({exe})"
    return exe


def _py_launcher_exe(version: str) -> str | None:
    py = _which("py")
    if not py:
        return None
    try:
        out = subprocess.check_output(
            [py, f"-{version}", "-c", "import sys; print(sys.executable)"],
            text=True,
            encoding="utf-8",
            errors="replace",
            **_subprocess_hide_kwargs(),
        ).strip()
        if out and Path(out).is_file():
            return out
    except Exception:
        pass
    return None


def _iter_python_candidates() -> list[str]:
    seen: set[str] = set()
    candidates: list[str] = []

    def add(exe: str | None) -> None:
        if not exe:
            return
        exe = str(Path(exe).resolve())
        if exe in seen or not Path(exe).is_file():
            return
        seen.add(exe)
        candidates.append(exe)

    if sys.platform == "win32":
        for tag in ("3.12", "3.11", "3.10"):
            add(_py_launcher_exe(tag))
        local = os.environ.get("LOCALAPPDATA", "")
        for rel in (
            r"Programs\Python\Python312\python.exe",
            r"Programs\Python\Python311\python.exe",
            r"Programs\Python\Python310\python.exe",
        ):
            add(os.path.join(local, rel))
        for rel in (
            r"C:\Program Files\Python312\python.exe",
            r"C:\Program Files\Python311\python.exe",
            r"C:\Program Files\Python310\python.exe",
        ):
            add(rel)

    py_default = _which("python")
    if py_default and _python_supported(_python_version_tuple(py_default)):
        add(py_default)
    if sys.executable:
        exe = str(Path(sys.executable).resolve())
        if _python_supported(_python_version_tuple(exe)):
            add(exe)
    return candidates


def _find_studio_python(log: LogFn | None = None) -> str | None:
    for exe in _iter_python_candidates():
        if _python_supported(_python_version_tuple(exe)):
            if log:
                log(f"Using {_python_label(exe)}")
            return exe
    return None


def _ensure_studio_python(log: LogFn) -> str | None:
    py = _find_studio_python(log)
    if py:
        return py

    current = _which("python") or sys.executable
    ver = _python_version_tuple(current) if current else None
    if ver and not _python_supported(ver):
        log(
            f"Python {ver[0]}.{ver[1]} is not supported for Studio "
            f"(need {STUDIO_PYTHON_MIN[0]}.{STUDIO_PYTHON_MIN[1]}–"
            f"{STUDIO_PYTHON_MAX[0]}.{STUDIO_PYTHON_MAX[1]})."
        )
    elif ver is None:
        log("Supported Python (3.10–3.12) was not found on this PC.")

    if sys.platform == "win32":
        log("Studio will install Python 3.12 automatically — please wait…")
        log("PHASE|12|Installing Python 3.12")
        if _install_studio_python_windows(log):
            py = _wait_for_studio_python(log)
            if py:
                _remove_unsupported_winget_python(log)
                return py
        log(
            "Automatic Python install did not finish. "
            "Close Studio, reopen VoxCPM Studio.bat, then click Run setup again."
        )
        return None

    log(
        f"Install Python {STUDIO_PYTHON_MIN[0]}.{STUDIO_PYTHON_MIN[1]}–"
        f"{STUDIO_PYTHON_MAX[0]}.{STUDIO_PYTHON_MAX[1]} from https://www.python.org/downloads/"
    )
    return None


def _winget_list_has(package_id: str) -> bool:
    if not _winget_available():
        return False
    try:
        proc = subprocess.run(
            ["winget", "list", "-e", "--id", package_id],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            **_subprocess_hide_kwargs(),
        )
        if proc.returncode != 0:
            return False
        return package_id.lower() in proc.stdout.lower()
    except Exception:
        return False


def _winget_uninstall(package_id: str, log: LogFn) -> bool:
    if not _winget_available():
        return False
    log(f"Removing {package_id} via winget…")
    rc = _run(
        [
            "winget",
            "uninstall",
            "-e",
            "--id",
            package_id,
            "--accept-source-agreements",
            "--disable-interactivity",
        ],
        log=log,
    )
    _refresh_windows_path()
    return rc == 0


def _remove_legacy_winget_node(log: LogFn) -> None:
    """Remove outdated winget Node.js builds after LTS is available."""
    if sys.platform != "win32" or not _winget_list_has(WINGET_NODE_ID):
        return
    for package_id in WINGET_LEGACY_NODE_IDS:
        if not _winget_list_has(package_id):
            continue
        log(f"Removing outdated {package_id} (Studio uses Node.js LTS)…")
        _winget_uninstall(package_id, log)
    _refresh_windows_path()


def _remove_unsupported_winget_python(log: LogFn) -> None:
    """Remove winget-managed Python 3.13+ so `python` does not point at unsupported builds."""
    if sys.platform != "win32":
        return
    for package_id in WINGET_UNSUPPORTED_PYTHON_IDS:
        if not _winget_list_has(package_id):
            continue
        ver = package_id.rsplit(".", 1)[-1]
        log(f"Removing unsupported Python 3.{ver} (Studio uses Python 3.12)…")
        _winget_uninstall(package_id, log)
    _refresh_windows_path()


def _install_studio_python_windows(log: LogFn) -> bool:
    if not _winget_available():
        log("winget is not available — trying direct Python installer download…")
        return _install_python_312_direct_windows(log)

    log("Installing Python 3.12 via winget (may prompt for admin approval)…")
    if _winget_install(WINGET_PYTHON_ID, log):
        return True

    if _winget_list_has(WINGET_PYTHON_ID):
        log("Python 3.12 is already installed via winget — refreshing PATH…")
        _refresh_windows_path()
        return True

    log("Retrying Python 3.12 install via winget upgrade…")
    if _winget_upgrade(WINGET_PYTHON_ID, log):
        return True

    return _winget_list_has(WINGET_PYTHON_ID)


def _install_python_312_direct_windows(log: LogFn) -> bool:
    installer_path = ""
    try:
        fd, temp_path = tempfile.mkstemp(prefix="sinekool_py312_", suffix=".exe")
        os.close(fd)
        installer_path = temp_path
        log("Downloading Python 3.12 installer from python.org…")
        with urllib.request.urlopen(PYTHON_312_INSTALLER_URL, timeout=120) as resp, open(installer_path, "wb") as out:
            out.write(resp.read())

        log("Running Python 3.12 installer silently (per-user)…")
        rc = _run_live(
            [
                installer_path,
                "/quiet",
                "InstallAllUsers=0",
                "PrependPath=1",
                "Include_test=0",
                "Shortcuts=0",
                "Include_launcher=1",
            ],
            log=log,
        )
        _refresh_windows_path()
        if rc == 0:
            return True
        log(f"Direct installer exited with code {rc}.")
        return False
    except Exception as exc:
        log(f"Direct Python installer failed: {exc}")
        return False
    finally:
        if installer_path and os.path.isfile(installer_path):
            try:
                os.remove(installer_path)
            except Exception:
                pass


def _wait_for_studio_python(log: LogFn, *, seconds: int = 90) -> str | None:
    for _ in range(max(1, seconds // 2)):
        _refresh_windows_path()
        py = _find_studio_python()
        if py:
            log(f"Python ready: {_python_label(py)}")
            return py
        time.sleep(2)
    return None


def _pip_env() -> dict[str, str]:
    return {
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "SETUPTOOLS_SCM_PRETEND_VERSION_FOR_VOXCPM": STUDIO_PACKAGE_VERSION,
    }


def _venv_pip_works() -> bool:
    if not VENV_PYTHON.is_file():
        return False
    try:
        subprocess.check_call(
            [str(VENV_PYTHON), "-m", "pip", "--version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **_subprocess_hide_kwargs(),
        )
        return True
    except Exception:
        return False


def _repair_venv_pip(log: LogFn) -> bool:
    if _venv_pip_works():
        return True
    if not VENV_PYTHON.is_file():
        return False
    log("Repairing pip in .venv…")
    if _run([str(VENV_PYTHON), "-m", "ensurepip", "--upgrade"], log=log) != 0:
        return False
    return _venv_pip_works()


def _pip_bootstrap(pip: list[str], log: LogFn) -> bool:
    if not _repair_venv_pip(log):
        return False
    return (
        _run_live(
            pip + ["install", "--upgrade", "pip", "setuptools", "wheel"],
            log=log,
            env=_pip_env(),
            parse_progress=True,
        )
        == 0
    )


def _pip_install_project(pip: list[str], log: LogFn) -> bool:
    env = _pip_env()
    attempts = (
        pip + ["install", "-e", "."],
        pip + ["install", "."],
    )
    for cmd in attempts:
        label = "editable" if "-e" in cmd else "standard"
        log(f"Installing VoxCPM package ({label})…")
        if _run_live(cmd, log=log, env=env, parse_progress=True) != 0:
            continue
        if (
            _run(
                [str(VENV_PYTHON), "-c", "import voxcpm; print('voxcpm', voxcpm.__version__ if hasattr(voxcpm, '__version__') else 'ok')"],
                log=log,
            )
            == 0
        ):
            return True
    return False


def _ensure_venv(py_exe: str, log: LogFn) -> bool:
    venv_path = PROJECT_ROOT / ".venv"
    if VENV_PYTHON.is_file():
        venv_ver = _python_version_tuple(str(VENV_PYTHON))
        if _python_supported(venv_ver) and _venv_pip_works():
            return True
        if _python_supported(venv_ver) and _repair_venv_pip(log):
            return True
        shown = f"{venv_ver[0]}.{venv_ver[1]}" if venv_ver else "unknown"
        if _python_supported(venv_ver):
            log("Removing broken .venv (pip missing)…")
        else:
            log(f"Removing old .venv (Python {shown} is not supported)…")
        log("PHASE|20|Recreating Python environment")
        shutil.rmtree(venv_path, ignore_errors=True)

    log("Creating virtual environment…")
    venv_args = [py_exe, "-m", "venv", str(venv_path)]
    py_ver = _python_version_tuple(py_exe)
    if py_ver and py_ver >= (3, 12):
        venv_args.append("--upgrade-deps")
    if _which("uv") and not venv_path.is_dir():
        if _run(["uv", "venv", str(venv_path), "--python", py_exe], log=log) == 0 and _repair_venv_pip(log):
            return VENV_PYTHON.is_file()
    if _run(venv_args, log=log) != 0:
        log("Failed to create .venv")
        return False
    if not _repair_venv_pip(log):
        log("Failed to bootstrap pip in .venv")
        return False
    return VENV_PYTHON.is_file()


def _winget_available() -> bool:
    return _which("winget") is not None


def _refresh_windows_path() -> None:
    """Prepend common winget install paths so new Python/Node are found."""
    if sys.platform != "win32":
        return
    local = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    candidates = [
        os.path.join(local, "Programs", "Python", "Python312"),
        os.path.join(local, "Programs", "Python", "Python312", "Scripts"),
        os.path.join(local, "Programs", "Python", "Python311"),
        os.path.join(local, "Programs", "Python", "Python311", "Scripts"),
        os.path.join(program_files, "nodejs"),
        os.path.join(program_files_x86, "nodejs"),
        r"C:\Program Files\nodejs",
        os.path.join(local, "Programs", "nodejs"),
        os.path.join(program_files, "Python312"),
        os.path.join(program_files, "Python312", "Scripts"),
    ]
    extras = [p for p in candidates if os.path.isdir(p)]
    if extras:
        os.environ["PATH"] = os.pathsep.join(extras + [os.environ.get("PATH", "")])


def _winget_install(package_id: str, log: LogFn) -> bool:
    if not _winget_available():
        return False
    log(f"Installing {package_id} via winget (may prompt for admin)…")
    rc = _run_live(
        [
            "winget",
            "install",
            "-e",
            "--id",
            package_id,
            "--accept-package-agreements",
            "--accept-source-agreements",
            "--disable-interactivity",
        ],
        log=log,
        parse_progress=True,
    )
    _refresh_windows_path()
    return rc == 0


def _winget_upgrade(package_id: str, log: LogFn) -> bool:
    if not _winget_available():
        return False
    log(f"Upgrading {package_id} via winget…")
    rc = _run_live(
        [
            "winget",
            "upgrade",
            "-e",
            "--id",
            package_id,
            "--accept-package-agreements",
            "--accept-source-agreements",
            "--disable-interactivity",
        ],
        log=log,
        parse_progress=True,
    )
    _refresh_windows_path()
    return rc == 0


def _wait_for_node(log: LogFn, *, seconds: int = 30) -> str | None:
    for _ in range(max(1, seconds // 2)):
        _refresh_windows_path()
        node = _find_node_exe()
        if node and _npm_command("--version"):
            ver = _node_version_tuple(node)
            if _node_supported(ver):
                if ver:
                    log(f"Using Node.js {ver[0]}.{ver[1]} ({node})")
                return node
        time.sleep(2)
    return None


def _ensure_node_js(log: LogFn) -> bool:
    """Ensure Node.js LTS + npm — auto-install via winget on Windows."""
    node = _find_node_exe()
    if node:
        ver = _node_version_tuple(node)
        if _node_supported(ver) and _npm_command("--version"):
            log(f"Using Node.js {ver[0]}.{ver[1]} ({node})")
            _remove_legacy_winget_node(log)
            return True
        if ver:
            log(f"Node.js {ver[0]}.{ver[1]} is not suitable — installing LTS…")
        else:
            log("Node.js found but npm is missing — reinstalling LTS…")

    if sys.platform != "win32":
        log("Node.js LTS not found. Install from https://nodejs.org/")
        return False

    if not _winget_available():
        log("Node.js LTS not found and winget is unavailable. Install from https://nodejs.org/")
        return False

    log("PHASE|15|Installing Node.js LTS")
    log("Installing Node.js LTS automatically (winget)…")
    if not _winget_install(WINGET_NODE_ID, log):
        log("Trying Node.js LTS upgrade via winget…")
        _winget_upgrade(WINGET_NODE_ID, log)

    node = _wait_for_node(log, seconds=60)
    if node:
        _remove_legacy_winget_node(log)
        return True

    log(
        "Node.js LTS was installed but is not visible yet.\n"
        "Close and reopen VoxCPM Studio.bat, then click Run setup again."
    )
    return False


def ensure_prerequisites(log: LogFn) -> bool:
    """Ensure supported Python and Node.js exist; on Windows try winget if missing."""
    if not _ensure_studio_python(log):
        return False
    return _ensure_node_js(log)


def _run_live(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    log: LogFn | None = None,
    env: dict[str, str] | None = None,
    parse_progress: bool = False,
) -> int:
    if log:
        log(f"$ {' '.join(cmd)}")
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd or PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=run_env,
            **_subprocess_hide_kwargs(),
        )
    except OSError as exc:
        if log:
            log(f"Failed to run command: {exc}")
        return 127
    assert proc.stdout is not None
    for line in proc.stdout:
        s = line.rstrip()
        if parse_progress and log:
            parsed = _try_parse_download_progress(s)
            if parsed:
                log(f"PROGRESS|{parsed[0]}|{parsed[1]}")
        if log and s:
            log(s)
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
    log("PHASE|58|Downloading VoxCPM2 model")
    log("Downloading VoxCPM2 weights (first time only, several GB)…")
    log("This may take several minutes depending on your connection.")

    script = (
        "from huggingface_hub import snapshot_download\n"
        "from tqdm.auto import tqdm\n\n"
        "def _fmt_bytes(n):\n"
        "    n = float(n)\n"
        "    if n >= 1024 ** 3:\n"
        "        return f'{n / 1024 ** 3:.1f}GB'\n"
        "    if n >= 1024 ** 2:\n"
        "        return f'{n / 1024 ** 2:.1f}MB'\n"
        "    if n >= 1024:\n"
        "        return f'{n / 1024:.1f}KB'\n"
        "    return f'{int(n)}B'\n\n"
        "class ProgressTqdm(tqdm):\n"
        "    def update(self, n=1):\n"
        "        super().update(n)\n"
        "        if self.total:\n"
        "            pct = min(100, int(100 * self.n / self.total))\n"
        "            width = 20\n"
        "            filled = int(width * self.n / self.total)\n"
        "            bar = '#' * filled + '-' * (width - filled)\n"
        "            label = self.desc or 'Downloading model files'\n"
        "            detail = f'{bar} {_fmt_bytes(self.n)}/{_fmt_bytes(self.total)} | {label}'\n"
        "            print(f'PROGRESS|{pct}|{detail}', flush=True)\n\n"
        f"dest = r'{dest}'\n"
        f"snapshot_download(repo_id='{HF_VOXCPM2_REPO}', local_dir=dest, tqdm_class=ProgressTqdm)\n"
        "print('Download complete:', dest)\n"
    )
    rc = _run_live(
        [str(VENV_PYTHON), "-c", script],
        log=log,
    )
    if rc != 0 or not MODEL_CONFIG.is_file():
        log("Model download failed. Check your internet connection and try Setup again.")
        return False
    log("PHASE|72|Model download complete")
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


def _subprocess_hide_kwargs() -> dict:
    """Hide console windows for child processes on Windows."""
    if sys.platform != "win32":
        return {}
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0
    return {
        "creationflags": subprocess.CREATE_NO_WINDOW,
        "startupinfo": si,
    }


def _next_dev_cmd() -> list[str] | None:
    node = _node_exe()
    if not node:
        return None
    next_bin = STARTER_KIT / "node_modules" / "next" / "dist" / "bin" / "next"
    if not next_bin.is_file():
        return None
    return [node, str(next_bin), "dev", "--turbopack", "-p", "3000"]


def run_checks() -> list[CheckResult]:
    results: list[CheckResult] = []
    hide = _subprocess_hide_kwargs()

    py = _find_studio_python() or _which("python") or sys.executable
    py_ver = ""
    py_ok = False
    if py:
        ver = _python_version_tuple(py)
        if ver:
            py_ver = f"Python {ver[0]}.{ver[1]}"
            py_ok = _python_supported(ver)
        else:
            py_ver = "unknown"
    results.append(
        CheckResult(
            key="python",
            label="Python",
            ok=py_ok,
            detail=py_ver or "Not found",
            fix_hint="Setup installs Python 3.12 automatically on Windows",
        )
    )

    node = _find_node_exe()
    node_ver = ""
    node_ok = False
    if node:
        ver = _node_version_tuple(node)
        if ver:
            node_ver = f"Node.js {ver[0]}.{ver[1]}"
            node_ok = _node_supported(ver) and bool(_npm_command("--version"))
        else:
            node_ver = "found"
    results.append(
        CheckResult(
            key="nodejs",
            label="Node.js LTS",
            ok=node_ok,
            detail=node_ver or "Not found",
            fix_hint="Setup installs Node.js LTS automatically on Windows",
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
                **hide,
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

    venv_ok = VENV_PYTHON.is_file() and _venv_pip_works()
    results.append(
        CheckResult(
            key="venv",
            label="Python venv",
            ok=venv_ok,
            detail=str(VENV_PYTHON.parent.parent) if VENV_PYTHON.is_file() else "Missing .venv",
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
                **hide,
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

    pkg_ok = False
    pkg_detail = "Not installed"
    if venv_ok:
        try:
            subprocess.check_call(
                [str(VENV_PYTHON), "-c", "import voxcpm; import cryptography"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **hide,
            )
            pkg_ok = True
            pkg_detail = "import ok"
        except Exception as exc:
            pkg_detail = str(exc)
    results.append(
        CheckResult(
            key="voxcpm",
            label="VoxCPM package",
            ok=pkg_ok,
            detail=pkg_detail,
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
            required=True,
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


def _studio_environment_ready() -> bool:
    """True when the requirements grid is all green (except optional GPU/servers)."""
    return required_ready(run_checks())


def wait_for_servers(timeout_sec: int = 90) -> bool:
    for _ in range(timeout_sec):
        if _port_open(8000) and _port_open(3000):
            return True
        time.sleep(1)
    return False


def bootstrap_setup(manager: StudioManager) -> bool:
    """Install dependencies if needed — no license required."""
    manager.log("PHASE|8|Checking prerequisites")
    if not ensure_prerequisites(manager.log):
        return False
    manager.log("Checking requirements…")
    if not _studio_environment_ready():
        manager.log("Running first-time setup (one click — please wait)…")
        if not manager.setup():
            manager.log("Setup failed. Open setup log for details, then click Run setup again.")
            return False
    manager.log("PHASE|100|Setup check complete")
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
        self._setup_lock = threading.Lock()

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
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, **_subprocess_hide_kwargs())
            else:
                proc.terminate()
                proc.wait(timeout=6)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        self.log(f"Stopped {name}.")

    def log(self, msg: str) -> None:
        self._log(msg)

    def stop(self) -> None:
        self._stop_proc(self._api_proc, "API")
        self._api_proc = None
        self._stop_proc(self._ui_proc, "UI")
        self._ui_proc = None

        for port, name in ((8000, "API"), (3000, "UI"), (3001, "UI"), (3002, "UI")):
            if not _port_open(port):
                continue
            try:
                out = subprocess.check_output(
                    ["netstat", "-ano"],
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    **_subprocess_hide_kwargs(),
                )
                for line in out.splitlines():
                    if f":{port} " in line and "LISTENING" in line:
                        pid = line.split()[-1]
                        subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", pid],
                            capture_output=True,
                            **_subprocess_hide_kwargs(),
                        )
                        self.log(f"Stopped {name} on port {port} (PID {pid})")
            except Exception as exc:
                self.log(f"Could not free port {port}: {exc}")

        self.log("Servers stopped.")

    def setup(self) -> bool:
        if not self._setup_lock.acquire(blocking=False):
            self.log("Setup already in progress — please wait.")
            return False
        try:
            return self._setup_impl()
        finally:
            self._setup_lock.release()

    def _setup_impl(self) -> bool:
        if _studio_environment_ready():
            self.log("=== Setup started ===")
            self.log("Everything is already installed — nothing to do.")
            self.log("PHASE|100|Already up to date")
            self.log("=== Setup finished ===")
            return True

        self.log("=== Setup started ===")
        self.log("PHASE|10|Checking prerequisites")
        if not ensure_prerequisites(self.log):
            return False

        self.log("PHASE|18|Preparing Python environment")
        py_exe = _find_studio_python() or _ensure_studio_python(self.log)
        if not py_exe:
            return False
        if not _ensure_venv(py_exe, self.log):
            return False

        checks = run_checks()
        has_nvidia = next((c.ok for c in checks if c.key == "gpu"), False)

        pip = [str(VENV_PYTHON), "-m", "pip"]
        if not _pip_bootstrap(pip, self.log):
            self.log("Python environment repair failed — retrying with a fresh .venv…")
            shutil.rmtree(PROJECT_ROOT / ".venv", ignore_errors=True)
            if not _ensure_venv(py_exe, self.log) or not _pip_bootstrap(pip, self.log):
                self.log("Python install failed.")
                return False

        torch_ok = False
        try:
            subprocess.check_call(
                [str(VENV_PYTHON), "-c", "import torch"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **_subprocess_hide_kwargs(),
            )
            torch_ok = True
        except Exception:
            pass

        if not torch_ok:
            index = TORCH_CUDA_INDEX if has_nvidia else TORCH_CPU_INDEX
            self.log("PHASE|32|Installing PyTorch")
            self.log(f"Installing PyTorch ({'CUDA' if has_nvidia else 'CPU'})…")
            _run_live(
                pip + ["install", "torch", "torchaudio", "--index-url", index],
                log=self.log,
                env=_pip_env(),
                parse_progress=True,
            )

        self.log("PHASE|45|Installing Python packages")
        if not _pip_install_project(pip, self.log):
            self.log("Python install failed.")
            return False

        if not download_voxcpm2_weights(self.log):
            return False

        self.log("PHASE|78|Installing frontend packages")
        if not _ensure_node_js(self.log):
            return False
        self.log("Installing frontend packages (npm)…")
        npm_args = ("install", "--no-audit", "--no-fund", "--loglevel=warn")
        if _run_npm(*npm_args, log=self.log) != 0:
            node_modules = STARTER_KIT / "node_modules"
            if node_modules.is_dir():
                self.log("Cleaning broken frontend install and retrying npm…")
                shutil.rmtree(node_modules, ignore_errors=True)
            if _run_npm(*npm_args, log=self.log) != 0:
                self.log("npm install failed.")
                return False

        self.log("PHASE|100|Setup finished")
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
        child_env = os.environ.copy()
        child_env["PYTHONUTF8"] = "1"
        child_env["PYTHONIOENCODING"] = "utf-8"
        popen_kw = dict(
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=child_env,
            **_subprocess_hide_kwargs(),
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
