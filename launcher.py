"""VoxCPM2 Studio — NiceGUI premium launcher."""

from __future__ import annotations

import queue
import sys
import threading
import webbrowser
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
    STUDIO_NAME,
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

ASSETS = PROJECT_ROOT / "assets"
ICON_ICO = ASSETS / "studio_launcher.ico"
LOGO_HEADER = ASSETS / "studio_logo_header.png"
ICON_PNG = ASSETS / "studio_icon.png"
LAUNCHER_PORT = 8765
MAX_LOG_LINES = 400

STUDIO_CSS = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400&display=swap');
  body, .nicegui-content {
    background: radial-gradient(900px 400px at 10% -10%, #1a2744 0%, transparent 55%),
                radial-gradient(700px 350px at 100% 0%, #2a1848 0%, transparent 50%),
                #080a0f !important;
    font-family: 'Inter', 'Segoe UI', sans-serif !important;
    font-size: 13px;
  }
  .studio-shell { max-width: 760px; margin: 0 auto; padding: 10px 12px 12px; }
  .studio-hero {
    background: linear-gradient(135deg, rgba(79,140,255,0.14), rgba(124,92,255,0.08));
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 10px;
    padding: 8px 12px;
    margin-bottom: 8px;
  }
  .studio-card {
    background: rgba(18, 20, 28, 0.92) !important;
    border: 1px solid rgba(255,255,255,0.07) !important;
    border-radius: 10px !important;
    box-shadow: none !important;
  }
  .studio-section-title {
    font-size: 0.65rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #8b949e;
    font-weight: 600;
    margin-bottom: 6px;
  }
  .studio-subtitle { color: #9aa4b2; font-size: 0.78rem; }
  .studio-version {
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 999px;
    padding: 2px 8px;
    font-size: 0.68rem;
    color: #c9d1d9;
  }
  .status-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    border-radius: 999px;
    font-weight: 600;
    font-size: 0.78rem;
  }
  .status-pill.running {
    background: rgba(63,185,80,0.15);
    color: #3fb950;
    border: 1px solid rgba(63,185,80,0.35);
  }
  .status-pill.stopped {
    background: rgba(139,148,158,0.12);
    color: #8b949e;
    border: 1px solid rgba(255,255,255,0.08);
  }
  .status-dot {
    width: 6px; height: 6px; border-radius: 50%;
    background: currentColor;
  }
  .check-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 6px;
    width: 100%;
  }
  @media (max-width: 700px) { .check-grid { grid-template-columns: repeat(2, 1fr); } }
  .check-tile {
    border-radius: 8px;
    padding: 6px 8px;
    border: 1px solid rgba(255,255,255,0.06);
    background: rgba(255,255,255,0.02);
    min-height: 0;
  }
  .check-tile.ok { border-color: rgba(63,185,80,0.22); background: rgba(63,185,80,0.05); }
  .check-tile.warn { border-color: rgba(210,153,34,0.22); background: rgba(210,153,34,0.05); }
  .check-tile.fail { border-color: rgba(248,81,73,0.22); background: rgba(248,81,73,0.05); }
  .check-label { font-weight: 600; font-size: 0.75rem; color: #e6edf3; line-height: 1.2; }
  .check-detail {
    font-size: 0.68rem; color: #8b949e; margin-top: 1px;
    word-break: break-word; line-height: 1.25;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  }
  .log-panel {
    background: #0b0e14;
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 8px;
    font-family: 'JetBrains Mono', Consolas, monospace;
    font-size: 0.68rem;
  }
  .log-line { line-height: 1.35; padding: 0; }
  .studio-shell .q-btn {
    min-height: 30px !important;
    font-size: 0.78rem !important;
    padding: 0 10px !important;
  }
  .studio-shell .q-btn .q-icon { font-size: 1rem !important; }
  .license-big { font-size: 1.05rem; font-weight: 700; line-height: 1.2; }
  .studio-shell .q-expansion-item { font-size: 0.82rem; }
  .compact-pad { padding: 10px 12px !important; }
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
    last_progress_log_pct: int = -1
    checks_cache: list = field(default_factory=list)

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
    days = status.remaining_days if status.remaining_days is not None else 999
    if days <= 0:
        return "negative", "Expired"
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
            on_click=lambda: ui.run_javascript(f"navigator.clipboard.writeText('{machine_id}')"),
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

                ui.timer(0.01, done, once=True)

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

    with ui.column().classes("studio-shell w-full gap-2"):
        with ui.element("div").classes("studio-hero w-full"):
            with ui.row().classes("w-full items-center justify-between gap-2"):
                with ui.row().classes("items-center gap-2"):
                    if LOGO_HEADER.is_file():
                        ui.image(str(LOGO_HEADER)).classes("h-8")
                    elif ICON_PNG.is_file():
                        ui.image(str(ICON_PNG)).classes("h-8")
                    with ui.column().classes("gap-0"):
                        ui.label(STUDIO_NAME).classes("text-subtitle1 font-bold leading-tight")
                        ui.label("Voice studio").classes("studio-subtitle")
                with ui.row().classes("items-center gap-2"):
                    ui_refs["update_label"] = ui.label("").classes("text-caption text-warning")
                    ui_refs["version_label"] = ui.label(f"v{get_studio_release_version()}").classes("studio-version")

        with ui.row().classes("w-full gap-2"):
            @ui.refreshable
            def license_panel() -> None:
                status = current_license_status()
                tone, label = _license_tone(status)
                with ui.card().classes("studio-card compact-pad flex-grow"):
                    ui.label("License").classes("studio-section-title")
                    with ui.row().classes("w-full items-center justify-between gap-2"):
                        with ui.column().classes("gap-0"):
                            ui.badge(label, color=tone).props("outline dense")
                            if status.ok:
                                ui.label(status.remaining_label or "—").classes("license-big")
                                exp = f"Expires {status.expires}" if status.expires else ""
                                if status.source:
                                    exp = f"{exp} · {status.source}" if exp else status.source
                                if exp:
                                    ui.label(exp).classes("text-caption text-grey")
                            else:
                                ui.label("Not activated").classes("studio-subtitle")
                        ui.button("License", icon="vpn_key", on_click=license_dialog.open).props(
                            "dense outline color=primary"
                        )
                    if status.ok and status.remaining_days is not None and status.expires != "dev":
                        ui.linear_progress(
                            value=min(1.0, max(0.0, status.remaining_days / 365)),
                            show_value=False,
                        ).props(f'color="{tone}" rounded dense').classes("mt-1")

            ui_refs["license_panel"] = license_panel
            license_panel()

            with ui.card().classes("studio-card compact-pad"):
                ui.label("Studio").classes("studio-section-title")
                ui_refs["server_status"] = ui.html(
                    '<div class="status-pill stopped"><span class="status-dot"></span>Stopped</div>'
                )
                with ui.row().classes("gap-1 mt-1"):
                    ui.button("Start", icon="play_arrow", on_click=lambda: start_studio()).props(
                        "dense unelevated color=positive"
                    )
                    ui.button("Stop", icon="stop", on_click=lambda: stop_servers()).props(
                        "dense outline color=negative"
                    )
                    ui.button("Open UI", icon="open_in_new", on_click=lambda: open_ui()).props(
                        "dense outline color=primary"
                    )

        with ui.row().classes("w-full gap-1 flex-wrap"):
            ui_refs["setup_btn"] = ui.button("Setup", icon="build", on_click=lambda: run_setup()).props(
                "dense unelevated color=primary"
            )
            ui.button("Refresh", icon="refresh", on_click=lambda: refresh_checks()).props("dense outline")
            ui.button("Updates", icon="system_update", on_click=lambda: check_updates(manual=True)).props(
                "dense outline"
            )
            ui.button("Get license", icon="chat", on_click=lambda: webbrowser.open(LICENSE_CONTACT_URL)).props(
                "dense flat color=primary"
            )

        with ui.card().classes("studio-card compact-pad w-full"):
            ui.label("Requirements").classes("studio-section-title")
            checks_host = ui.element("div").classes("check-grid w-full")

            @ui.refreshable
            def checks_panel() -> None:
                checks_host.clear()
                with checks_host:
                    for item in state.checks_cache:
                        if item.ok:
                            css = "ok"
                        elif not item.required:
                            css = "warn"
                        else:
                            css = "fail"
                        with ui.element("div").classes(f"check-tile {css}"):
                            ui.label(item.label).classes("check-label")
                            ui.label(item.detail).classes("check-detail")

            ui_refs["checks_panel"] = checks_panel
            checks_panel()

        with ui.expansion("Activity log", icon="terminal", value=False).classes("studio-card w-full"):
            ui_refs["activity_label"] = ui.label("Idle").classes("text-caption font-medium")
            ui_refs["progress_bar"] = ui.linear_progress(value=0, show_value=False).props(
                "color=primary rounded dense"
            )
            with ui.row().classes("w-full items-center justify-between"):
                ui_refs["progress_pct_label"] = ui.label("").classes("text-caption text-primary")
                ui.button("Clear", icon="delete_outline", on_click=lambda: clear_log()).props("flat dense")
            ui_refs["progress_detail_label"] = ui.label("").classes("text-caption text-grey log-line")
            log_scroll = ui.scroll_area().classes("log-panel w-full h-24 p-2 mt-1")
            with log_scroll:
                ui_refs["log_column"] = ui.column().classes("w-full gap-0")

        with ui.row().classes("w-full justify-between items-center text-caption text-grey"):
            ui.label(f"Support · {LICENSE_CONTACT_LABEL}")
            ui.link("Telegram", LICENSE_CONTACT_URL).classes("text-primary text-caption")

    # --- handlers ---
    def rebuild_log_view() -> None:
        col = ui_refs["log_column"]
        col.clear()
        with col:
            for level, text in state.log_lines:
                style = LOG_STYLE.get(level, LOG_STYLE["info"])
                ui.html(f'<div class="log-line" style="{style}">{_escape_html(text)}</div>')

    def sync_progress_ui() -> None:
        ui_refs["activity_label"].text = state.activity_text
        ui_refs["progress_detail_label"].text = state.progress_detail
        bar = ui_refs["progress_bar"]
        if state.progress_indeterminate:
            bar.props("indeterminate")
        else:
            bar.props(remove="indeterminate")
            bar.value = state.progress_pct / 100.0
            ui_refs["progress_pct_label"].text = f"{int(state.progress_pct)}%" if state.progress_pct else ""

    def set_server_status(running: bool) -> None:
        cls = "running" if running else "stopped"
        label = "Running" if running else "Stopped"
        ui_refs["server_status"].content = (
            f'<div class="status-pill {cls}"><span class="status-dot"></span>{label}</div>'
        )

    def poll_log() -> None:
        changed = False
        for _ in range(40):
            try:
                event = state.log_queue.get_nowait()
            except queue.Empty:
                break
            _apply_log_event(event)
            changed = True
        if changed:
            rebuild_log_view()
            sync_progress_ui()

    def poll_servers() -> None:
        up = state.manager.running or (_port_open(8000) and _port_open(3000))
        set_server_status(up)
        if up != state.servers_up:
            state.servers_up = up
            refresh_checks()

    def refresh_checks() -> None:
        if state.checks_busy:
            return
        state.checks_busy = True

        def work() -> None:
            checks = run_checks()

            def done() -> None:
                state.checks_cache = checks
                ui_refs["checks_panel"].refresh()
                state.checks_busy = False

            ui.timer(0.01, done, once=True)

        threading.Thread(target=work, daemon=True).start()

    def clear_log() -> None:
        state.log_lines.clear()
        state.last_progress_log_pct = -1
        rebuild_log_view()

    def set_setup_busy(busy: bool) -> None:
        state.setup_busy = busy
        btn = ui_refs["setup_btn"]
        (btn.disable if busy else btn.enable)()

    def auto_setup() -> None:
        state.activity_text = "Checking install requirements…"
        state.progress_indeterminate = True
        sync_progress_ui()
        state.enqueue_log("Checking install requirements (no license needed for setup)…")
        success = True
        try:
            success = bootstrap_setup(state.manager)
        except Exception as exc:
            state.enqueue_log(f"Setup error: {exc}")
            success = False
        finally:
            state.progress_indeterminate = False
            state.progress_pct = 100.0 if success else 0.0
            state.activity_text = "Ready" if success else "Setup needs attention"
            ui.timer(0.01, lambda: (sync_progress_ui(), refresh_checks()), once=True)

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
                ui.timer(
                    0.01,
                    lambda: (set_setup_busy(False), sync_progress_ui(), refresh_checks()),
                    once=True,
                )

        threading.Thread(target=work, daemon=True).start()

    def ensure_licensed() -> bool:
        ui_refs["license_panel"].refresh()
        if current_license_status().ok:
            return True
        license_dialog.open()
        return current_license_status().ok

    def start_studio() -> None:
        if not ensure_licensed():
            return

        def work() -> None:
            checks = run_checks()
            if not all(c.ok for c in checks if c.required and c.key != "servers"):
                ui.timer(0.01, lambda: ui.notify("Run Setup first — some requirements are missing.", type="warning"), once=True)
                return
            state.manager.start(open_browser=True)
            ui.timer(0.01, wait_and_refresh, once=True)

        threading.Thread(target=work, daemon=True).start()

    def stop_servers() -> None:
        threading.Thread(target=state.manager.stop, daemon=True).start()
        ui.timer(0.5, refresh_checks, once=True)

    def open_ui() -> None:
        if not ensure_licensed():
            return

        def work() -> None:
            if not state.manager.running and not (_port_open(8000) and _port_open(3000)):
                checks = run_checks()
                if not all(c.ok for c in checks if c.required and c.key != "servers"):
                    ui.timer(0.01, lambda: ui.notify("Finish setup first.", type="warning"), once=True)
                    return
                if not state.manager.start(open_browser=False):
                    return
                ui.timer(0.01, wait_and_refresh, once=True)
            webbrowser.open("http://localhost:3000/home")

        threading.Thread(target=work, daemon=True).start()

    def wait_and_refresh() -> None:
        def work() -> None:
            state.enqueue_log("Waiting for API and UI to be ready…")
            ready = wait_for_servers(timeout_sec=120)
            state.enqueue_log("Servers are up." if ready else "Servers still starting…")
            ui.timer(0.01, refresh_checks, once=True)

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

            ui.timer(0.01, done, once=True)

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
                ui.timer(0.01, lambda: show_update_dialog(status), once=True)

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

            ui.timer(0.01, done, once=True)

        threading.Thread(target=work, daemon=True).start()

    ui.timer(0.15, poll_log)
    ui.timer(3.0, poll_servers)
    ui.timer(60.0, lambda: ui_refs["license_panel"].refresh())
    ui.timer(5.0, check_updates_quiet, once=True)
    ui.timer(0.5, refresh_checks, once=True)

    state.enqueue_log(f"Welcome to {STUDIO_NAME}")
    if not state.setup_started:
        state.setup_started = True
        ui.timer(0.3, auto_setup, once=True)


def main() -> None:
    if not _ensure_nicegui():
        _run_tk_fallback("NiceGUI not installed — run Setup once, then restart Studio.")
        return

    from nicegui import app, ui

    @app.on_shutdown
    def _shutdown() -> None:
        if state.manager.running:
            state.manager.stop()

    favicon = str(ICON_ICO) if ICON_ICO.is_file() else str(ICON_PNG) if ICON_PNG.is_file() else None
    ui.run(
        build_ui,
        native=True,
        port=LAUNCHER_PORT,
        reload=False,
        title=STUDIO_NAME,
        window_size=(780, 640),
        favicon=favicon,
        show_welcome_message=False,
    )


if __name__ == "__main__":
    main()
