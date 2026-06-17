"""VoxCPM2 Studio — NiceGUI premium launcher."""

from __future__ import annotations

import json
import queue
import sys
import threading
import time
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from license_manager import (
    LicenseStatus,
    activate_license_key,
    current_license_status,
    get_machine_id,
)
from studio_branding import (
    LICENSE_CONTACT_HINT,
    LICENSE_CONTACT_LABEL,
    LICENSE_CONTACT_URL,
    STUDIO_LAUNCHER_ICO,
    STUDIO_LOGO_ICON,
    STUDIO_LOGO_TEXT,
    STUDIO_NAME,
    STUDIO_SLOGAN,
    get_studio_release_version,
)
from studio_log import LogEvent, parse_log_message
from studio_update import UpdateStatus, apply_git_update, check_for_updates
from launcher_core import (
    PROJECT_ROOT,
    StudioManager,
    _port_open,
    bootstrap_setup,
    run_checks,
    wait_for_servers,
)

LAUNCHER_PORT = 8765
LAUNCHER_WIDTH = 720
LAUNCHER_HEIGHT = 680
MAX_LOG_LINES = 400

STUDIO_CSS = """
<style>
  body, .nicegui-content {
    background: radial-gradient(900px 400px at 10% -10%, #1a2744 0%, transparent 55%),
                radial-gradient(700px 350px at 100% 0%, #2a1848 0%, transparent 50%),
                #080a0f !important;
    font-family: 'Segoe UI', system-ui, sans-serif !important;
    font-size: 13px;
    overflow: hidden !important;
  }
  .studio-shell { max-width: 720px; margin: 0 auto; padding: 6px 8px 8px; }
  .studio-hero {
    background: linear-gradient(135deg, rgba(79,140,255,0.12), rgba(124,92,255,0.06));
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 8px;
    padding: 6px 10px;
    margin-bottom: 6px;
  }
  .studio-card {
    background: rgba(18, 20, 28, 0.92) !important;
    border: 1px solid rgba(255,255,255,0.06) !important;
    border-radius: 8px !important;
    box-shadow: none !important;
  }
  .studio-shell .q-card__section { padding: 6px 8px !important; }
  .studio-section-title {
    font-size: 0.62rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #8b949e;
    font-weight: 600;
    margin-bottom: 4px;
  }
  .studio-subtitle { color: #9aa4b2; font-size: 0.72rem; }
  .studio-slogan { color: #8b949e; font-size: 0.65rem; line-height: 1.2; margin-top: 2px; }
  .studio-hero-logo { max-height: 2.25rem; width: auto; object-fit: contain; }
  .studio-version {
    background: rgba(255,255,255,0.05);
    border-radius: 999px;
    padding: 1px 7px;
    font-size: 0.65rem;
    color: #c9d1d9;
  }
  .status-pill {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 2px 8px;
    border-radius: 999px;
    font-weight: 600;
    font-size: 0.72rem;
  }
  .status-pill.running { background: rgba(63,185,80,0.12); color: #3fb950; }
  .status-pill.ready { background: rgba(67,164,255,0.14); color: #79c0ff; }
  .status-pill.notready { background: rgba(139,148,158,0.1); color: #8b949e; }
  .status-dot { width: 5px; height: 5px; border-radius: 50%; background: currentColor; }
  .req-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 4px 10px;
    width: 100%;
  }
  .req-row {
    display: flex;
    align-items: flex-start;
    gap: 4px;
    padding: 3px 6px;
    line-height: 1.2;
    font-size: 0.72rem;
    border-radius: 8px;
    border: 1px solid rgba(255,255,255,0.06);
    background: rgba(255,255,255,0.02);
  }
  .req-row.ok .req-name { color: #3fb950; }
  .req-row.warn .req-name { color: #d29922; }
  .req-row.fail .req-name { color: #f85149; }
  .req-row.checking .req-name { color: #9aa4b2; }
  .req-row.ok { border-color: rgba(63,185,80,0.18); background: rgba(63,185,80,0.05); }
  .req-row.warn { border-color: rgba(210,153,34,0.18); background: rgba(210,153,34,0.05); }
  .req-row.fail { border-color: rgba(248,81,73,0.18); background: rgba(248,81,73,0.05); }
  .req-row.checking { border-color: rgba(255,255,255,0.08); background: rgba(255,255,255,0.02); }
  .req-name { font-weight: 600; min-width: 78px; flex-shrink: 0; }
  .req-detail { color: #8b949e; word-break: break-all; }
  .log-panel {
    display: block;
    width: 100%;
    box-sizing: border-box;
    background: #0b0e14;
    border: 1px solid rgba(255,255,255,0.05);
    border-radius: 6px;
    font-family: Consolas, 'Cascadia Mono', monospace;
    font-size: 0.65rem;
    user-select: text !important;
    -webkit-user-select: text !important;
    cursor: text;
    overflow-y: auto;
    overflow-x: hidden;
    height: 7.5rem;
    max-height: 7.5rem;
    scroll-behavior: auto;
    overscroll-behavior: contain;
  }
  .log-body, .log-line {
    line-height: 1.25;
    padding: 0;
    user-select: text !important;
    -webkit-user-select: text !important;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .studio-log-expansion .q-item { min-height: 26px !important; padding: 2px 8px !important; }
  .studio-log-expansion .q-expansion-item__content {
    padding: 2px 8px 6px !important;
    transition: none !important;
  }
  .studio-log-body { gap: 4px !important; }
  .studio-log-status { min-height: 0; }
  .req-loading { font-size: 0.72rem; color: #9aa4b2; }
  .studio-shell .q-btn {
    min-height: 26px !important;
    font-size: 0.72rem !important;
    padding: 0 8px !important;
  }
  .studio-shell .q-btn .q-icon { font-size: 0.9rem !important; }
  .license-big { font-size: 0.95rem; font-weight: 700; line-height: 1.15; }
  .studio-shell .q-expansion-item__container { min-height: 26px; }
  .compact-pad { padding: 6px 8px !important; }
  .studio-shell .gap-2 { gap: 4px !important; }
</style>
"""

LOG_STYLE = {
    "info": "color:#e6edf3",
    "ok": "color:#3fb950",
    "warn": "color:#d29922",
    "err": "color:#f85149",
    "cmd": "color:#79c0ff",
    "dim": "color:#8b949e",
    "title": "color:#a371f7;font-weight:600",
}


def _run_tk_fallback(reason: str) -> None:
    print(reason, file=sys.stderr)
    from launcher_tk import main as tk_main

    tk_main()


def _ensure_nicegui() -> bool:
    try:
        import nicegui  # noqa: F401

        return True
    except ImportError:
        pass
    try:
        import subprocess

        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "nicegui>=2.0.0", "pywebview>=5.0", "-q"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        import nicegui  # noqa: F401

        return True
    except Exception:
        return False


@dataclass
class LauncherState:
    log_queue: queue.Queue[LogEvent] = field(default_factory=queue.Queue)
    manager: StudioManager = field(default_factory=lambda: StudioManager())
    checks_busy: bool = False
    ui_tasks: queue.Queue[Callable[[], None]] = field(default_factory=queue.Queue)
    checks_results: queue.Queue[list] = field(default_factory=queue.Queue)
    log_lines: list[tuple[str, str]] = field(default_factory=list)
    activity_text: str = "Idle"
    progress_pct: float = 0.0
    progress_detail: str = ""
    progress_indeterminate: bool = False
    servers_up: bool = False
    update_status: UpdateStatus | None = None
    update_snoozed: bool = False
    setup_started: bool = False
    setup_busy: bool = False
    start_busy: bool = False
    last_progress_log_pct: int = -1
    checks_cache: list = field(default_factory=list)
    last_checks_refresh_at: float = 0.0
    checks_refresh_pending: bool = False
    last_action_sig: tuple | None = None
    servers_running_cached: bool = False

    def __post_init__(self) -> None:
        self.manager = StudioManager(log=self.enqueue_log)

    def enqueue_log(self, msg: str) -> None:
        self.log_queue.put(parse_log_message(msg))


state = LauncherState()


def _license_tone(status: LicenseStatus) -> tuple[str, str]:
    if not status.ok:
        return "negative", "Not activated"
    if status.expires == "dev":
        return "positive", "Active"
    if status.remaining_label == "Expired":
        return "negative", "Expired"
    days = status.remaining_days if status.remaining_days is not None else 999
    if days <= 7:
        return "warning", "Active"
    return "positive", "Active"


def _append_log_line(text: str, level: str) -> None:
    state.log_lines.append((level, text))
    if len(state.log_lines) > MAX_LOG_LINES:
        state.log_lines = state.log_lines[-MAX_LOG_LINES:]


def _apply_log_event(event: LogEvent) -> None:
    if event.progress is not None:
        state.progress_indeterminate = False
        state.progress_pct = max(0.0, min(100.0, event.progress))
        shown = event.progress_detail or event.progress_text or event.text
        if shown:
            state.progress_detail = shown
            state.activity_text = shown if len(shown) <= 80 else shown[:77] + "…"
            step = int(state.progress_pct // 10) * 10
            if step > state.last_progress_log_pct or state.progress_pct >= 100:
                state.last_progress_log_pct = step
                _append_log_line(shown, "dim")
    elif event.level == "title":
        lower = event.text.lower()
        if "started" in lower:
            state.progress_indeterminate = True
            state.activity_text = event.text
        elif "finished" in lower or "complete" in lower:
            state.progress_indeterminate = False
            state.progress_pct = 100.0
            state.activity_text = "Ready"
    elif event.level in ("warn", "cmd", "info", "ok", "err") and state.progress_indeterminate:
        short = event.text if len(event.text) <= 80 else event.text[:77] + "…"
        if short and not short.startswith("$ "):
            state.activity_text = short
    if event.text:
        _append_log_line(event.text, event.level)


def _escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _schedule_ui(fn: Callable[[], None]) -> None:
    state.ui_tasks.put(fn)


def _render_checks_html(checks: list) -> str:
    if not checks:
        # Show an immediate neutral skeleton so the UI doesn't look empty
        # while the background thread is still running.
        skeleton = [
            ("Python", True),
            ("Node.js LTS", True),
            ("NVIDIA GPU", False),
            ("Python venv", True),
            ("PyTorch", True),
            ("VoxCPM package", True),
            ("Frontend packages", True),
            ("VoxCPM2 weights", True),
            ("Servers", False),
        ]
        rows: list[str] = []
        for label, _required in skeleton:
            rows.append(
                f'<div class="req-row checking">'
                f'<span class="req-name">… {_escape_html(label)}</span>'
                f'<span class="req-detail">checking…</span>'
                f"</div>"
            )
        return f'<div class="req-grid">{"".join(rows)}</div>'

    rows: list[str] = []
    for item in checks:
        if item.ok:
            css, mark = "ok", "✓"
        elif not item.required:
            css, mark = "warn", "!"
        else:
            css, mark = "fail", "✗"
        detail = item.detail if len(item.detail) <= 56 else item.detail[:53] + "…"
        rows.append(
            f'<div class="req-row {css}">'
            f'<span class="req-name">{mark} {_escape_html(item.label)}</span>'
            f'<span class="req-detail">{_escape_html(detail)}</span>'
            f"</div>"
        )
    return f'<div class="req-grid">{"".join(rows)}</div>'


def _render_log_html(lines: list[tuple[str, str]]) -> str:
    if not lines:
        body = '<div class="log-line" style="color:#8b949e">No log output yet.</div>'
    else:
        parts: list[str] = []
        for level, text in lines:
            style = LOG_STYLE.get(level, LOG_STYLE["info"])
            parts.append(f'<div class="log-line" style="{style}">{_escape_html(text)}</div>')
        body = "".join(parts)
    return f'<div id="studio-log-panel" class="log-panel p-1 w-full"><div class="log-body">{body}</div></div>'


def build_ui() -> None:
    from nicegui import ui

    ui.dark_mode().enable()
    ui.add_head_html(STUDIO_CSS)

    # --- shared refs filled during layout ---
    ui_refs: dict = {}

    # --- dialogs ---
    license_dialog = ui.dialog().props("persistent")
    machine_id = get_machine_id()

    with license_dialog, ui.card().classes("studio-card w-[540px]"):
        ui.label("Activate license").classes("text-h6 font-semibold")
        ui.label(LICENSE_CONTACT_HINT).classes("studio-subtitle")
        ui.button("Open Telegram", icon="send", on_click=lambda: webbrowser.open(LICENSE_CONTACT_URL)).props(
            "flat color=primary"
        )
        ui.input("Machine ID", value=machine_id).props("readonly outlined dense").classes("w-full")
        ui.button(
            "Copy Machine ID",
            icon="content_copy",
            on_click=lambda: (
                ui.run_javascript(f"navigator.clipboard.writeText('{machine_id}')"),
                ui.notify("Machine ID copied", type="positive"),
            ),
        ).props("outline dense")
        key_input = ui.input("License key").props("outlined dense").classes("w-full")
        dlg_status = ui.label("").classes("text-caption")

        def activate() -> None:
            key = (key_input.value or "").strip()
            if not key:
                dlg_status.text = "Paste your license key first."
                return
            dlg_status.text = "Checking license…"

            def work() -> None:
                try:
                    result = activate_license_key(key)
                except Exception as exc:
                    result = LicenseStatus(False, str(exc))

                def done() -> None:
                    dlg_status.text = result.message
                    if result.ok:
                        state.enqueue_log(result.message)
                        license_dialog.close()
                        ui_refs["license_panel"].refresh()
                        ui.notify(f"License active — {result.remaining_label or ''}", type="positive")

                _schedule_ui(done)

            threading.Thread(target=work, daemon=True).start()

        with ui.row().classes("w-full justify-end gap-2 mt-2"):
            ui.button("Cancel", on_click=license_dialog.close).props("flat")
            ui.button("Activate", on_click=activate).props("unelevated color=primary")

    update_dialog = ui.dialog()
    update_ui: dict = {}

    with update_dialog, ui.card().classes("studio-card w-[500px]"):
        update_ui["title"] = ui.label().classes("text-h6")
        update_ui["body"] = ui.label().classes("studio-subtitle")
        with ui.row().classes("w-full justify-end gap-2 mt-3"):
            ui.button("Later", on_click=update_dialog.close).props("flat")
            update_ui["git_btn"] = ui.button("Git pull", on_click=lambda: (update_dialog.close(), run_git_update())).props(
                "unelevated color=primary"
            )
            ui.button(
                "Download ZIP",
                on_click=lambda: (
                    webbrowser.open(state.update_status.zip_url) if state.update_status else None,
                    update_dialog.close(),
                    ui.notify("Replace folder; keep data/license.json", type="info"),
                ),
            ).props("outline")

    with ui.column().classes("studio-shell w-full gap-1"):
        with ui.element("div").classes("studio-hero w-full"):
            with ui.row().classes("w-full items-center justify-between no-wrap"):
                with ui.column().classes("gap-0"):
                    if STUDIO_LOGO_TEXT.is_file():
                        ui.image(str(STUDIO_LOGO_TEXT)).classes("studio-hero-logo")
                    elif STUDIO_LOGO_ICON.is_file():
                        ui.image(str(STUDIO_LOGO_ICON)).classes("studio-hero-logo")
                    ui.label(STUDIO_SLOGAN).classes("studio-slogan")
                with ui.row().classes("items-center gap-1"):
                    ui_refs["update_label"] = ui.label("").classes("text-caption text-warning")
                    ui_refs["version_label"] = ui.label(f"v{get_studio_release_version()}").classes("studio-version")

        with ui.row().classes("w-full gap-1 items-stretch"):
            @ui.refreshable
            def license_panel() -> None:
                status = current_license_status()
                tone, label = _license_tone(status)
                with ui.card().classes("studio-card compact-pad flex-grow"):
                    with ui.row().classes("w-full items-center justify-between gap-1"):
                        with ui.column().classes("gap-0 flex-grow"):
                            with ui.row().classes("items-center gap-1"):
                                ui.badge(label, color=tone).props("dense outline")
                                if status.ok:
                                    ui.label(status.remaining_label or "—").classes("license-big")
                                else:
                                    ui.label("Not activated").classes("studio-subtitle")
                            if status.ok and status.expires:
                                ui.label(f"Exp. {status.expires}").classes("text-caption text-grey")
                            if status.ok and status.max_chunks is not None:
                                ui.label(f"Max chunks: {status.max_chunks} per request").classes("text-caption text-grey")
                            ui.label(f"Machine ID: {machine_id[:10]}...").classes("text-caption text-grey")
                        with ui.row().classes("items-center gap-0"):
                            ui.button("License", icon="vpn_key", on_click=license_dialog.open).props(
                                "dense flat color=primary"
                            )
                            ui.button(
                                "ID",
                                icon="content_copy",
                                on_click=lambda: (
                                    ui.run_javascript(f"navigator.clipboard.writeText('{machine_id}')"),
                                    ui.notify("Machine ID copied", type="positive"),
                                ),
                            ).props("dense flat color=primary")

            ui_refs["license_panel"] = license_panel
            license_panel()

            with ui.card().classes("studio-card compact-pad"):
                ui_refs["server_status"] = ui.html(
                    '<div class="status-pill notready"><span class="status-dot"></span>Not ready</div>'
                )
                with ui.row().classes("gap-1"):
                    ui_refs["start_btn"] = ui.button("Start", icon="play_arrow", on_click=lambda: start_studio()).props(
                        "dense unelevated color=positive"
                    )
                    ui_refs["stop_btn"] = ui.button("Stop", icon="stop", on_click=lambda: stop_servers()).props(
                        "dense outline color=negative"
                    )
                    ui_refs["open_btn"] = ui.button("Open UI", icon="open_in_new", on_click=lambda: open_ui()).props(
                        "dense outline color=primary"
                    )

        with ui.row().classes("w-full gap-1 flex-wrap"):
            ui_refs["setup_btn"] = ui.button("Setup", icon="build", on_click=lambda: run_setup()).props("dense unelevated color=primary")
            ui.button(
                "Refresh",
                icon="refresh",
                on_click=lambda: request_refresh_checks(force=True, show_placeholder=True),
            ).props("dense outline")
            ui.button("Updates", icon="system_update", on_click=lambda: check_updates(manual=True)).props("dense outline")
            ui.button(
                "License", icon="chat", on_click=lambda: webbrowser.open(LICENSE_CONTACT_URL)
            ).props("dense flat color=primary")

        with ui.card().classes("studio-card compact-pad w-full"):
            ui.label("Requirements").classes("studio-section-title")
            ui_refs["checks_html"] = ui.html(_render_checks_html([]))

        log_expansion = ui.expansion("Activity log", icon="terminal", value=True).props("dense").classes(
            "studio-log-expansion studio-card w-full"
        )
        ui_refs["log_expansion"] = log_expansion
        with log_expansion:
            with ui.column().classes("w-full studio-log-body"):
                with ui.row().classes("w-full items-center gap-1 studio-log-status no-wrap"):
                    ui_refs["activity_label"] = ui.label("Idle").classes("text-caption flex-grow truncate")
                    ui_refs["progress_pct_label"] = ui.label("").classes("text-caption text-primary shrink-0")
                    ui.button("Copy", icon="content_copy", on_click=lambda: copy_log()).props("flat dense")
                    ui.button("Clear", icon="delete_outline", on_click=lambda: clear_log()).props("flat dense")
                with ui.element("div").classes("w-full") as progress_row:
                    ui_refs["progress_row"] = progress_row
                    ui_refs["progress_bar"] = ui.linear_progress(value=0, show_value=False).props(
                        "color=primary rounded dense"
                    )
                ui_refs["log_html"] = ui.html(_render_log_html([])).classes("w-full")
        ui_refs["progress_row"].set_visibility(False)

        with ui.row().classes("w-full justify-between").style("font-size:0.65rem;color:#8b949e"):
            ui.label(f"Support · {LICENSE_CONTACT_LABEL}")
            ui.link("Telegram", LICENSE_CONTACT_URL).classes("text-primary")

    # --- handlers ---
    def requirements_ready() -> bool:
        if not state.checks_cache:
            return False
        return all(c.ok for c in state.checks_cache if c.required and c.key != "servers")

    def scroll_log_to_bottom() -> None:
        ui.run_javascript(
            "requestAnimationFrame(()=>{const el=document.getElementById('studio-log-panel');"
            "if(el){el.scrollTop=el.scrollHeight;}})"
        )

    def sync_action_buttons() -> None:
        running = state.servers_running_cached
        ready = requirements_ready()
        sig = (running, ready, state.setup_busy, state.start_busy)
        if sig == state.last_action_sig:
            return
        state.last_action_sig = sig

        if running:
            cls, label = "running", "Running"
        elif ready:
            cls, label = "ready", "Ready"
        else:
            cls, label = "notready", "Not ready"

        ui_refs["server_status"].content = (
            f'<div class="status-pill {cls}"><span class="status-dot"></span>{label}</div>'
        )

        start_enable = ready and not running and not state.setup_busy and not state.start_busy
        stop_enable = running
        open_enable = running

        (ui_refs["start_btn"].enable if start_enable else ui_refs["start_btn"].disable)()
        (ui_refs["stop_btn"].enable if stop_enable else ui_refs["stop_btn"].disable)()
        (ui_refs["open_btn"].enable if open_enable else ui_refs["open_btn"].disable)()
        if state.start_busy:
            ui_refs["start_btn"].props("loading")
        else:
            ui_refs["start_btn"].props(remove="loading")

    def apply_checks(checks: list) -> None:
        state.checks_cache = checks
        ui_refs["checks_html"].content = _render_checks_html(checks)
        state.last_action_sig = None
        sync_action_buttons()

    def rebuild_log_view() -> None:
        ui_refs["log_html"].content = _render_log_html(state.log_lines)
        scroll_log_to_bottom()

    def copy_log() -> None:
        text = "\n".join(line for _, line in state.log_lines)
        if not text:
            ui.notify("Log is empty", type="info")
            return
        ui.run_javascript(f"navigator.clipboard.writeText({json.dumps(text)})")
        ui.notify("Log copied", type="positive")

    def poll_ui_tasks() -> None:
        while True:
            try:
                checks = state.checks_results.get_nowait()
            except queue.Empty:
                break
            state.checks_busy = False
            apply_checks(checks)
            if state.checks_refresh_pending:
                state.checks_refresh_pending = False
                request_refresh_checks(force=True, show_placeholder=False)
        for _ in range(30):
            try:
                fn = state.ui_tasks.get_nowait()
            except queue.Empty:
                break
            try:
                fn()
            except Exception as exc:
                state.enqueue_log(f"UI error: {exc}")

    def sync_progress_ui() -> None:
        ui_refs["activity_label"].text = state.activity_text
        show_progress = state.progress_indeterminate or 0 < state.progress_pct < 100
        ui_refs["progress_row"].set_visibility(show_progress)
        bar = ui_refs["progress_bar"]
        if state.progress_indeterminate:
            bar.props("indeterminate")
            ui_refs["progress_pct_label"].text = ""
        elif show_progress:
            bar.props(remove="indeterminate")
            bar.value = state.progress_pct / 100.0
            ui_refs["progress_pct_label"].text = f"{int(state.progress_pct)}%"
        else:
            bar.props(remove="indeterminate")
            bar.value = 0
            ui_refs["progress_pct_label"].text = ""

    def poll_log() -> None:
        poll_ui_tasks()
        changed = False
        progress_only = False
        for _ in range(80):
            try:
                event = state.log_queue.get_nowait()
            except queue.Empty:
                break
            before = len(state.log_lines)
            _apply_log_event(event)
            if len(state.log_lines) > before or event.text:
                changed = True
            else:
                progress_only = True
        if changed:
            rebuild_log_view()
            sync_progress_ui()
        elif progress_only:
            sync_progress_ui()

    def poll_servers() -> None:
        up = state.manager.running or (_port_open(8000) and _port_open(3000))
        state.servers_running_cached = up
        sync_action_buttons()
        if up != state.servers_up:
            state.servers_up = up
            state.last_action_sig = None
            request_refresh_checks(force=True, show_placeholder=False)

    def request_refresh_checks(*, force: bool = False, show_placeholder: bool = False) -> None:
        now = time.monotonic()
        if state.checks_busy:
            state.checks_refresh_pending = True
            return
        # throttle noisy repeated checks (except explicit force)
        if not force and (now - state.last_checks_refresh_at) < 5.0:
            return
        state.last_checks_refresh_at = now
        state.checks_busy = True
        if show_placeholder:
            ui_refs["checks_html"].content = _render_checks_html([])

        def work() -> None:
            try:
                checks = run_checks()
            except Exception as exc:
                checks = []
                state.enqueue_log(f"Requirement check failed: {exc}")
            state.checks_results.put(checks)

        threading.Thread(target=work, daemon=True).start()

    def clear_log() -> None:
        state.log_lines.clear()
        state.last_progress_log_pct = -1
        rebuild_log_view()

    def set_setup_busy(busy: bool) -> None:
        state.setup_busy = busy
        btn = ui_refs["setup_btn"]
        (btn.disable if busy else btn.enable)()
        state.last_action_sig = None
        sync_action_buttons()

    def set_start_busy(busy: bool) -> None:
        state.start_busy = busy
        state.last_action_sig = None
        sync_action_buttons()

    def auto_setup() -> None:
        if state.setup_busy:
            return
        state.setup_busy = True
        state.activity_text = "Checking install requirements…"
        state.progress_indeterminate = True
        sync_progress_ui()
        state.enqueue_log("Checking install requirements (no license needed for setup)…")

        def work() -> None:
            success = True
            try:
                success = bootstrap_setup(state.manager)
            except Exception as exc:
                state.enqueue_log(f"Setup error: {exc}")
                success = False

            def done() -> None:
                state.setup_busy = False
                state.progress_indeterminate = False
                state.progress_pct = 100.0 if success else 0.0
                state.activity_text = "Ready" if success else "Setup needs attention"
                sync_progress_ui()
                request_refresh_checks(force=True, show_placeholder=False)

            _schedule_ui(done)

        threading.Thread(target=work, daemon=True).start()

    def run_setup() -> None:
        if state.setup_busy:
            return
        state.last_progress_log_pct = -1
        state.enqueue_log("Running setup…")
        state.activity_text = "Running setup…"
        state.progress_indeterminate = True
        set_setup_busy(True)
        sync_progress_ui()

        def work() -> None:
            try:
                ok = state.manager.setup()
                if not ok:
                    state.activity_text = "Setup needs attention"
                    state.progress_pct = 0.0
            except Exception as exc:
                state.enqueue_log(f"Error: {exc}")
                state.activity_text = "Setup needs attention"
            finally:
                state.progress_indeterminate = False

                def done() -> None:
                    set_setup_busy(False)
                    sync_progress_ui()
                    request_refresh_checks(force=True, show_placeholder=False)

                _schedule_ui(done)

        threading.Thread(target=work, daemon=True).start()

    def ensure_licensed() -> bool:
        status = current_license_status()
        ui_refs["license_panel"].refresh()
        if status.ok:
            return True
        license_dialog.open()
        return False

    def start_studio() -> None:
        if state.start_busy:
            return
        set_start_busy(True)
        if not ensure_licensed():
            set_start_busy(False)
            return

        def work() -> None:
            checks = run_checks()
            if not all(c.ok for c in checks if c.required and c.key != "servers"):
                _schedule_ui(
                    lambda: (
                        set_start_busy(False),
                        ui.notify("Run Setup first — some requirements are missing.", type="warning"),
                    )
                )
                return
            started = state.manager.start(open_browser=False)
            if not started:
                _schedule_ui(lambda: set_start_busy(False))
                return
            _schedule_ui(lambda: wait_and_refresh(open_ui_when_ready=True))

        threading.Thread(target=work, daemon=True).start()

    def stop_servers() -> None:
        set_start_busy(False)
        threading.Thread(target=state.manager.stop, daemon=True).start()
        ui.timer(0.5, lambda: request_refresh_checks(force=True, show_placeholder=False), once=True)

    def open_ui() -> None:
        if not ensure_licensed():
            return

        def work() -> None:
            if not (state.manager.running or (_port_open(8000) and _port_open(3000))):
                _schedule_ui(lambda: ui.notify("Start Studio first.", type="warning"))
                return
            webbrowser.open("http://localhost:3000/home")

        threading.Thread(target=work, daemon=True).start()

    def wait_and_refresh(*, open_ui_when_ready: bool = False) -> None:
        def work() -> None:
            state.enqueue_log("Waiting for API and UI to be ready…")
            ready = wait_for_servers(timeout_sec=120)
            state.enqueue_log("Servers are up." if ready else "Servers still starting…")
            def done() -> None:
                set_start_busy(False)
                request_refresh_checks(force=True, show_placeholder=False)
                if ready and open_ui_when_ready:
                    webbrowser.open("http://localhost:3000/home")
            _schedule_ui(done)

        threading.Thread(target=work, daemon=True).start()

    def set_update_ui(status: UpdateStatus) -> None:
        state.update_status = status
        ui_refs["update_label"].text = f"Update · v{status.latest}" if status.update_available else ""
        ui_refs["version_label"].text = f"v{get_studio_release_version()}"

    def show_update_dialog(status: UpdateStatus) -> None:
        set_update_ui(status)
        update_ui["title"].text = f"Update available — v{status.latest}"
        update_ui["body"].text = (
            f"You have v{status.current}. "
            + ("Git pull is available." if status.can_git_update else "Download the ZIP from GitHub.")
        )
        update_ui["git_btn"].set_visibility(status.can_git_update)
        update_dialog.open()

    def check_updates(*, manual: bool) -> None:
        state.enqueue_log("Checking for updates…")

        def work() -> None:
            status = check_for_updates()

            def done() -> None:
                set_update_ui(status)
                if status.error:
                    state.enqueue_log(f"Update check failed: {status.error}")
                    if manual:
                        ui.notify(status.error, type="negative")
                    return
                if not status.update_available:
                    state.enqueue_log(f"Up to date (v{status.current}).")
                    if manual:
                        ui.notify(f"Up to date (v{status.current})", type="positive")
                    return
                state.enqueue_log(f"Update available: v{status.latest} (you have v{status.current}).")
                show_update_dialog(status)

            _schedule_ui(done)

        threading.Thread(target=work, daemon=True).start()

    def check_updates_quiet() -> None:
        if state.update_snoozed:
            return

        def work() -> None:
            try:
                status = check_for_updates()
            except Exception:
                return
            if status.update_available:
                _schedule_ui(lambda: show_update_dialog(status))

        threading.Thread(target=work, daemon=True).start()

    def run_git_update() -> None:
        state.enqueue_log("Applying update…")

        def work() -> None:
            ok, msg = apply_git_update(state.enqueue_log)

            def done() -> None:
                ui_refs["version_label"].text = f"v{get_studio_release_version()}"
                if ok:
                    state.update_snoozed = True
                    ui.notify(msg, type="positive")
                    run_setup()
                else:
                    ui.notify(msg, type="negative")

            _schedule_ui(done)

        threading.Thread(target=work, daemon=True).start()

    ui.timer(0.2, poll_log)
    ui.timer(5.0, poll_servers)
    ui.timer(60.0, lambda: ui_refs["license_panel"].refresh())
    ui.timer(5.0, check_updates_quiet, once=True)
    ui.timer(0.05, lambda: request_refresh_checks(force=True, show_placeholder=True), once=True)

    state.enqueue_log(f"Welcome to {STUDIO_NAME}")
    sync_action_buttons()
    if not state.setup_started:
        state.setup_started = True
        ui.timer(0.3, auto_setup, once=True)


def main() -> None:
    if not _ensure_nicegui():
        _run_tk_fallback("NiceGUI not installed — run Setup once, then restart Studio.")
        return

    from nicegui import app, ui

    # Lock native window size (no maximize / resize)
    app.native.window_args.update(
        {
            "resizable": False,
            "min_size": (LAUNCHER_WIDTH, LAUNCHER_HEIGHT),
        }
    )

    @app.on_shutdown
    def _shutdown() -> None:
        if state.manager.running:
            state.manager.stop()

    favicon = (
        str(STUDIO_LAUNCHER_ICO)
        if STUDIO_LAUNCHER_ICO.is_file()
        else str(STUDIO_LOGO_ICON)
        if STUDIO_LOGO_ICON.is_file()
        else None
    )
    ui.run(
        build_ui,
        native=True,
        port=LAUNCHER_PORT,
        reload=False,
        title=STUDIO_NAME,
        window_size=(LAUNCHER_WIDTH, LAUNCHER_HEIGHT),
        favicon=favicon,
        show_welcome_message=False,
    )


if __name__ == "__main__":
    main()
