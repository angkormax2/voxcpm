"""VoxCPM2 Studio — NiceGUI launcher (native window, smooth dark UI)."""

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
            [sys.executable, "-m", "pip", "install", "nicegui", "pywebview", "-q"],
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
    log_expanded: bool = True
    last_progress_log_pct: int = -1
    checks_cache: list = field(default_factory=list)

    def __post_init__(self) -> None:
        self.manager = StudioManager(log=self.enqueue_log)

    def enqueue_log(self, msg: str) -> None:
        self.log_queue.put(parse_log_message(msg))


state = LauncherState()


def _license_color(status: LicenseStatus) -> str:
    if not status.ok:
        return "red"
    if status.expires == "dev":
        return "green"
    days = status.remaining_days if status.remaining_days is not None else 999
    if days <= 0:
        return "red"
    if days <= 7:
        return "orange"
    return "green"


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


def build_ui() -> None:
    from nicegui import ui

    ui.dark_mode().enable()
    ui.add_head_html(
        """
        <style>
          body { background: #0f1117 !important; }
          .studio-page { max-width: 920px; margin: 0 auto; }
          .studio-card {
            background: #1a1d2e !important;
            border: 1px solid #30363d;
            border-radius: 12px;
            transition: box-shadow 0.25s ease, transform 0.2s ease;
          }
          .studio-card:hover { box-shadow: 0 4px 24px rgba(0,0,0,0.35); }
          .log-line { font-family: Consolas, monospace; font-size: 0.82rem; line-height: 1.45; }
          .nicegui-content { padding: 0 !important; }
        </style>
        """
    )

    # --- dialogs ---
    license_dialog = ui.dialog().props("persistent")
    machine_id = get_machine_id()

    with license_dialog, ui.card().classes("w-[520px] studio-card"):
        ui.label("Activate your license").classes("text-h6")
        ui.label(f"Need a license? {LICENSE_CONTACT_HINT}").classes("text-caption text-grey")
        ui.button("Open Telegram", on_click=lambda: webbrowser.open(LICENSE_CONTACT_URL)).props(
            "flat color=primary"
        )
        ui.input("Machine ID", value=machine_id).props("readonly outlined dense").classes("w-full")
        ui.button(
            "Copy Machine ID",
            on_click=lambda: ui.run_javascript(
                f"navigator.clipboard.writeText('{machine_id}')"
            ),
        ).props("outline dense")
        key_input = ui.input("License key (VCPM-... or VCPM2...)").props("outlined dense").classes(
            "w-full"
        )
        status_lbl = ui.label("").classes("text-caption")

        def activate() -> None:
            key = (key_input.value or "").strip()
            if not key:
                status_lbl.text = "Paste your license key first."
                return
            status_lbl.text = "Checking license…"

            def work() -> None:
                try:
                    result = activate_license_key(key)
                except Exception as exc:
                    result = LicenseStatus(False, str(exc))

                def done() -> None:
                    status_lbl.text = result.message
                    if result.ok:
                        state.enqueue_log(result.message)
                        license_dialog.close()
                        license_panel.refresh()
                        ui.notify(
                            f"License active — {result.remaining_label or ''}",
                            type="positive",
                        )

                ui.timer(0.01, done, once=True)

            threading.Thread(target=work, daemon=True).start()

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=license_dialog.close).props("flat")
            ui.button("Activate license", on_click=activate).props("unelevated color=primary")

    update_dialog = ui.dialog()
    update_ui: dict = {}

    with update_dialog, ui.card().classes("w-[480px] studio-card"):
        update_ui["title"] = ui.label().classes("text-h6")
        update_ui["body"] = ui.label().classes("text-body2")

        def apply_git() -> None:
            update_dialog.close()
            run_git_update()

        def open_zip() -> None:
            if state.update_status:
                webbrowser.open(state.update_status.zip_url)
            update_dialog.close()
            ui.notify("Download ZIP and replace folder (keep data/license.json)", type="info")

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Later", on_click=update_dialog.close).props("flat")
            update_ui["git_btn"] = ui.button(
                "Git pull", on_click=apply_git
            ).props("unelevated color=primary")
            ui.button("Download ZIP", on_click=open_zip).props("outline")

    # --- header ---
    with ui.column().classes("studio-page w-full gap-4 p-4"):
        with ui.row().classes("items-center gap-4 w-full"):
            if LOGO_HEADER.is_file():
                ui.image(str(LOGO_HEADER)).classes("h-14")
            elif ICON_PNG.is_file():
                ui.image(str(ICON_PNG)).classes("h-14")
            with ui.column().classes("gap-0"):
                ui.label(STUDIO_NAME).classes("text-h5 font-bold")
                ui.label("Voice studio · setup runs quietly in the background").classes(
                    "text-caption text-grey"
                )

        @ui.refreshable
        def license_panel() -> None:
            status = current_license_status()
            color = _license_color(status)
            with ui.card().classes("studio-card w-full"):
                with ui.row().classes("w-full items-start justify-between"):
                    with ui.column().classes("gap-1"):
                        ui.label(
                            "Active" if status.ok else "Not activated",
                        ).classes(f"text-h6 text-{color}")
                        if status.ok:
                            ui.label(status.remaining_label or "—").classes(
                                f"text-h5 text-{color}"
                            )
                            ui.label(f"Expires {status.expires or '—'}").classes("text-caption")
                            if status.source:
                                ui.label(f"Type: {status.source}").classes("text-caption text-grey")
                        else:
                            ui.label(LICENSE_CONTACT_HINT).classes("text-body2")
                            ui.label("Enter a license to use Open UI / Start Studio").classes(
                                "text-caption text-grey"
                            )
                    ui.button("Enter license", on_click=license_dialog.open).props(
                        "outline color=primary"
                    )
                if status.ok and status.remaining_days is not None and status.expires != "dev":
                    ui.linear_progress(
                        value=min(1.0, max(0.0, status.remaining_days / 365)),
                        show_value=False,
                    ).props(f'color="{color}"').classes("rounded")

        license_panel()

        with ui.card().classes("studio-card w-full"):
            ui.label("Requirements").classes("text-subtitle1 font-medium mb-2")
            checks_container = ui.row().classes("w-full gap-4 flex-wrap")

            @ui.refreshable
            def checks_panel() -> None:
                checks_container.clear()
                with checks_container:
                    for item in state.checks_cache:
                        if item.ok:
                            icon, chip_color = "check_circle", "green"
                        elif not item.required:
                            icon, chip_color = "warning", "orange"
                        else:
                            icon, chip_color = "cancel", "red"
                        with ui.column().classes("gap-0 min-w-[200px]"):
                            with ui.row().classes("items-center gap-1"):
                                ui.icon(icon, color=chip_color).classes("text-sm")
                                ui.label(item.label).classes("text-body2 font-medium")
                            ui.label(item.detail).classes("text-caption text-grey pl-6")

            checks_panel()

        with ui.row().classes("gap-2 flex-wrap"):
            ui.button("Refresh checks", icon="refresh", on_click=lambda: refresh_checks()).props(
                "outline"
            )
            setup_btn = ui.button("Run setup", icon="build", on_click=lambda: run_setup()).props(
                "unelevated color=primary"
            )
            ui.button("Enter license", icon="vpn_key", on_click=license_dialog.open).props("outline")
            ui.button(
                "Get a license",
                icon="chat",
                on_click=lambda: webbrowser.open(LICENSE_CONTACT_URL),
            ).props("flat")
            ui.button(
                "Check for updates",
                icon="system_update",
                on_click=lambda: check_updates(manual=True),
            ).props("outline")

        with ui.card().classes("studio-card w-full"):
            with ui.row().classes("w-full items-center justify-between"):
                server_status = ui.label("Status: Stopped").classes("text-subtitle1 font-bold")
                with ui.row().classes("gap-2"):
                    ui.button(
                        "Open UI", icon="open_in_browser", on_click=lambda: open_ui()
                    ).props("unelevated color=primary")
                    ui.button(
                        "Stop", icon="stop", on_click=lambda: stop_servers()
                    ).props("outline color=negative")
                    ui.button(
                        "Start Studio", icon="play_arrow", on_click=lambda: start_studio()
                    ).props("unelevated color=positive")

        with ui.expansion("Activity log", icon="terminal", value=True).classes(
            "studio-card w-full"
        ) as log_expansion:
            activity_label = ui.label("Idle").classes("text-body2 font-medium")
            progress_bar = ui.linear_progress(value=0, show_value=False).props("color=positive")
            progress_pct_label = ui.label("").classes("text-caption text-positive")
            progress_detail_label = ui.label("").classes("text-caption text-grey log-line")

            with ui.row().classes("w-full justify-end"):
                ui.button(
                    "Clear log", icon="delete_outline", on_click=lambda: clear_log()
                ).props("flat dense")

            log_scroll = ui.scroll_area().classes("w-full h-56 bg-[#0d1117] rounded-lg p-2")
            with log_scroll:
                log_column = ui.column().classes("w-full gap-0")

        with ui.row().classes("w-full justify-between items-center text-caption text-grey"):
            ui.label(f"License support: {LICENSE_CONTACT_LABEL}")
            with ui.row().classes("gap-3 items-center"):
                update_label = ui.label("")
                version_label = ui.label(f"v{get_studio_release_version()}")

    # --- UI update helpers ---
    def rebuild_log_view() -> None:
        log_column.clear()
        with log_column:
            for level, text in state.log_lines:
                style = LOG_STYLE.get(level, LOG_STYLE["info"])
                ui.html(f'<div class="log-line" style="{style}">{_escape_html(text)}</div>')

    def sync_progress_ui() -> None:
        activity_label.text = state.activity_text
        progress_detail_label.text = state.progress_detail
        if state.progress_indeterminate:
            progress_bar.props('indeterminate')
        else:
            progress_bar.props(remove='indeterminate')
            progress_bar.value = state.progress_pct / 100.0
            progress_pct_label.text = f"{int(state.progress_pct)}%" if state.progress_pct else ""

    def poll_log() -> None:
        changed = False
        batch = 0
        while batch < 40:
            try:
                event = state.log_queue.get_nowait()
            except queue.Empty:
                break
            _apply_log_event(event)
            changed = True
            batch += 1
        if changed:
            rebuild_log_view()
            sync_progress_ui()

    def poll_servers() -> None:
        up = state.manager.running or (_port_open(8000) and _port_open(3000))
        server_status.text = "Status: Running" if up else "Status: Stopped"
        if up != state.servers_up:
            state.servers_up = up
            refresh_checks()

    def poll_license() -> None:
        license_panel.refresh()

    def refresh_checks() -> None:
        if state.checks_busy:
            return
        state.checks_busy = True

        def work() -> None:
            checks = run_checks()

            def done() -> None:
                state.checks_cache = checks
                checks_panel.refresh()
                state.checks_busy = False

            ui.timer(0.01, done, once=True)

        threading.Thread(target=work, daemon=True).start()

    def clear_log() -> None:
        state.log_lines.clear()
        state.last_progress_log_pct = -1
        rebuild_log_view()

    def set_setup_busy(busy: bool) -> None:
        state.setup_busy = busy
        if busy:
            setup_btn.disable()
        else:
            setup_btn.enable()

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
        log_expansion.value = True

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
        license_panel.refresh()
        if current_license_status().ok:
            return True
        license_dialog.open()
        return current_license_status().ok

    def start_studio() -> None:
        if not ensure_licensed():
            return

        def work() -> None:
            checks = run_checks()
            ready = all(c.ok for c in checks if c.required and c.key != "servers")
            if not ready:
                ui.timer(
                    0.01,
                    lambda: ui.notify("Some requirements are missing — run Setup first.", type="warning"),
                    once=True,
                )
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
                ready = all(c.ok for c in checks if c.required and c.key != "servers")
                if not ready:
                    ui.timer(
                        0.01,
                        lambda: ui.notify("Finish setup first, then open the UI.", type="warning"),
                        once=True,
                    )
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
        if status.update_available:
            update_label.text = f"Update available: v{status.latest}"
        else:
            update_label.text = ""
        version_label.text = f"v{get_studio_release_version()}"

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
            if not status.update_available:
                return

            def notify() -> None:
                set_update_ui(status)
                show_update_dialog(status)

            ui.timer(0.01, notify, once=True)

        threading.Thread(target=work, daemon=True).start()

    def run_git_update() -> None:
        state.enqueue_log("Applying update…")

        def work() -> None:
            ok, msg = apply_git_update(state.enqueue_log)

            def done() -> None:
                version_label.text = f"v{get_studio_release_version()}"
                if ok:
                    state.update_snoozed = True
                    ui.notify(msg, type="positive")
                    run_setup()
                else:
                    ui.notify(msg, type="negative")

            ui.timer(0.01, done, once=True)

        threading.Thread(target=work, daemon=True).start()

    # timers
    ui.timer(0.15, poll_log)
    ui.timer(3.0, poll_servers)
    ui.timer(60.0, poll_license)
    ui.timer(5.0, check_updates_quiet, once=True)
    ui.timer(0.5, refresh_checks, once=True)

    state.enqueue_log(f"Welcome to {STUDIO_NAME}")
    if not state.setup_started:
        state.setup_started = True
        ui.timer(0.3, auto_setup, once=True)


def _escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def main() -> None:
    if not _ensure_nicegui():
        _run_tk_fallback("NiceGUI not installed — using classic launcher. Run Setup, then restart.")
        return

    from nicegui import ui

    try:
        build_ui()

        def on_shutdown() -> None:
            if state.manager.running:
                state.manager.stop()

        ui.on_shutdown(on_shutdown)
        favicon = str(ICON_ICO) if ICON_ICO.is_file() else str(ICON_PNG) if ICON_PNG.is_file() else None
        ui.run(
            native=True,
            port=LAUNCHER_PORT,
            reload=False,
            title=STUDIO_NAME,
            window_size=(920, 860),
            favicon=favicon,
        )
    except Exception as exc:
        print(f"NiceGUI launcher failed: {exc}", file=sys.stderr)
        _run_tk_fallback(f"NiceGUI error ({exc}) — using classic launcher.")


if __name__ == "__main__":
    main()
