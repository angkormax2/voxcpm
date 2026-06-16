"""VoxCPM2 Studio — graphical launcher (replaces CMD workflow)."""

from __future__ import annotations

import queue
import sys
import threading
import webbrowser
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

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
    center_tk_window,
    run_checks,
    wait_for_servers,
)

ASSETS = PROJECT_ROOT / "assets"
ICON_ICO = ASSETS / "studio_launcher.ico"
ICON_PNG = ASSETS / "studio_icon.png"
LOGO_HEADER = ASSETS / "studio_logo_header.png"

BG = "#0f1117"
PANEL = "#1a1d2e"
TEXT = "#e6edf3"
MUTED = "#8b949e"
OK = "#3fb950"
WARN = "#d29922"
ERR = "#f85149"
MAX_LOG_LINES = 400


class StudioLauncherApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title(STUDIO_NAME)
        self.root.geometry("740x680")
        self.root.minsize(620, 560)
        self.root.configure(bg=BG)

        self.log_queue: queue.Queue[LogEvent] = queue.Queue()
        self.manager = StudioManager(log=self._enqueue_log)
        self._checks_busy = False
        self._log_line_count = 0
        self._activity_busy = False
        self._last_progress_log_pct = -1
        self._window_icon: tk.PhotoImage | None = None
        self._header_logo: tk.PhotoImage | None = None
        self._setup_started = False
        self._log_visible = False
        self._servers_up = False
        self._update_status: UpdateStatus | None = None
        self._update_snoozed = False

        self._set_window_icon()
        self._build_main_ui()
        center_tk_window(self.root, width=740, height=680)

        self.root.after(150, self._poll_log)
        self.root.after(500, self.refresh_checks_async)
        self.root.after(3000, self._poll_server_status)
        self.root.after(1000, self._poll_access_status)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(5000, self._check_updates_quiet)

        self._enqueue_log(f"Welcome to {STUDIO_NAME}")
        self._refresh_license_panel()
        if not self._setup_started:
            self._setup_started = True
            threading.Thread(target=self._auto_setup, daemon=True).start()

    def _auto_setup(self) -> None:
        self.root.after(0, self._show_log_panel_if_hidden)
        self.root.after(0, lambda: self._begin_activity("Checking install requirements…"))
        self._enqueue_log("Checking install requirements (no license needed for setup)…")
        success = True
        try:
            success = bootstrap_setup(self.manager)
        except Exception as exc:
            self._enqueue_log(f"Setup error: {exc}")
            success = False
        finally:
            self.root.after(0, lambda s=success: self._finish_activity(success=s))
        self.root.after(0, self.refresh_checks_async)

    def _enqueue_log(self, msg: str) -> None:
        self.log_queue.put(parse_log_message(msg))

    def _begin_activity(self, text: str) -> None:
        self._activity_var.set(text)
        self._log_progress.configure(mode="indeterminate")
        self._log_progress.start(10)
        self._log_pct_var.set("")
        self._activity_busy = True

    def _finish_activity(self, *, success: bool = True) -> None:
        if self._activity_busy:
            self._log_progress.stop()
            self._log_progress.configure(mode="determinate")
            self._activity_busy = False
        self._log_progress["value"] = 100 if success else 0
        self._log_pct_var.set("100%" if success else "")
        self._activity_var.set("Ready" if success else "Setup needs attention")

    def _set_log_progress(self, pct: float, text: str = "", detail: str = "") -> None:
        if self._activity_busy:
            self._log_progress.stop()
            self._log_progress.configure(mode="determinate")
            self._activity_busy = False
        pct = max(0.0, min(100.0, pct))
        self._log_progress["value"] = pct
        self._log_pct_var.set(f"{int(pct)}%")
        shown = detail or text
        if shown:
            self._log_detail_var.set(shown)
            self._activity_var.set(shown if len(shown) <= 72 else shown[:69] + "…")
            step = int(pct // 10) * 10
            if step > self._last_progress_log_pct or pct >= 100:
                self._last_progress_log_pct = step
                self.log_box.configure(state="normal")
                self.log_box.insert(tk.END, shown + "\n", ("dim",))
                self.log_box.see(tk.END)
                self.log_box.configure(state="disabled")

    def _apply_log_event(self, event: LogEvent) -> None:
        if event.progress is not None:
            self._set_log_progress(
                event.progress,
                event.progress_text or event.text,
                event.progress_detail,
            )
        elif event.level == "title":
            lower = event.text.lower()
            if "started" in lower:
                self._begin_activity(event.text)
            elif "finished" in lower or "complete" in lower:
                self._finish_activity(success=True)
        elif event.level in ("warn", "cmd", "info", "ok", "err") and self._activity_busy:
            short = event.text if len(event.text) <= 72 else event.text[:69] + "…"
            if not short.startswith("$ "):
                self._activity_var.set(short)

        if not event.text:
            return

        self.log_box.configure(state="normal")
        self.log_box.insert(tk.END, event.text + "\n", (event.level,))
        self._log_line_count += 1
        if self._log_line_count > MAX_LOG_LINES:
            self.log_box.delete("1.0", f"{self._log_line_count - MAX_LOG_LINES}.0")
            self._log_line_count = MAX_LOG_LINES
        self.log_box.see(tk.END)
        self.log_box.configure(state="disabled")

    def _poll_log(self) -> None:
        batch = 0
        while batch < 40:
            try:
                event = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self._apply_log_event(event)
            batch += 1
        self.root.after(150, self._poll_log)

    def _poll_server_status(self) -> None:
        up = self.manager.running or (_port_open(8000) and _port_open(3000))
        self.status_var.set("Status: Running" if up else "Status: Stopped")
        if up != self._servers_up:
            self._servers_up = up
            self.refresh_checks_async()
        self.root.after(3000, self._poll_server_status)

    def _wait_and_refresh_checks(self) -> None:
        """Wait until API + UI ports are open, then refresh the requirements grid."""

        def work() -> None:
            self._enqueue_log("Waiting for API and UI to be ready…")
            ready = wait_for_servers(timeout_sec=120)
            if ready:
                self._enqueue_log("Servers are up.")
            else:
                self._enqueue_log("Servers still starting — checks will update when ready.")
            self._servers_up = _port_open(8000) and _port_open(3000)
            self.root.after(0, self.refresh_checks_async)

        threading.Thread(target=work, daemon=True).start()

    def _poll_access_status(self) -> None:
        self._refresh_license_panel()
        self.root.after(60000, self._poll_access_status)

    def _license_status_color(self, status: LicenseStatus) -> str:
        if not status.ok:
            return ERR
        if status.expires == "dev":
            return OK
        days = status.remaining_days if status.remaining_days is not None else 999
        if days <= 0:
            return ERR
        if days <= 7:
            return WARN
        return OK

    def _refresh_license_panel(self) -> None:
        status = current_license_status()
        color = self._license_status_color(status)

        if status.ok:
            self.license_state_var.set("Active")
            self.license_state_label.configure(fg=color)
            remaining = status.remaining_label or "—"
            self.license_remaining_var.set(remaining)
            self.license_remaining_label.configure(fg=color)
            self.license_expires_var.set(f"Expires {status.expires or '—'}")
            if status.source:
                self.license_type_var.set(f"Type: {status.source}")
            else:
                self.license_type_var.set("")
            if status.remaining_days is not None and status.expires != "dev":
                pct = min(100, max(0, int((status.remaining_days / 365) * 100)))
                self.license_progress["value"] = pct
                self.license_progress.pack(fill="x", pady=(6, 0))
            else:
                self.license_progress.pack_forget()
        else:
            self.license_state_var.set("Not activated")
            self.license_state_label.configure(fg=ERR)
            self.license_remaining_var.set(LICENSE_CONTACT_HINT)
            self.license_remaining_label.configure(fg=MUTED)
            self.license_expires_var.set("Enter a license to use Open UI / Start Studio")
            self.license_type_var.set("")
            self.license_progress.pack_forget()

        if hasattr(self, "access_var"):
            self.access_var.set(status.message if status.ok else "")

    def _open_license_contact(self) -> None:
        webbrowser.open(LICENSE_CONTACT_URL)

    def _show_activation_success(self, result: LicenseStatus) -> None:
        remaining = result.remaining_label or "—"
        kind = (result.source or "offline").capitalize()
        messagebox.showinfo(
            "License activated",
            f"Your license is now active.\n\n"
            f"Time remaining: {remaining}\n"
            f"Expiry date: {result.expires or '—'}\n"
            f"License type: {kind}\n\n"
            "You can click Open UI or Start Studio.",
        )

    def _set_window_icon(self) -> None:
        try:
            if sys.platform == "win32" and ICON_ICO.is_file():
                self.root.iconbitmap(default=str(ICON_ICO))
            elif ICON_PNG.is_file():
                self._window_icon = tk.PhotoImage(file=str(ICON_PNG))
                self.root.iconphoto(True, self._window_icon)
        except Exception:
            pass

    def _load_header_logo(self) -> tk.PhotoImage | None:
        for path in (LOGO_HEADER, ICON_PNG):
            if not path.is_file():
                continue
            try:
                return tk.PhotoImage(file=str(path))
            except Exception:
                continue
        return None

    def _show_license_dialog(self, note: str = "") -> None:
        win = tk.Toplevel(self.root)
        win.title("Activate license")
        win.configure(bg=BG)
        win.geometry("540x460")
        win.transient(self.root)
        win.grab_set()

        tk.Label(
            win,
            text="Activate your license",
            font=("Segoe UI", 15, "bold"),
            fg=TEXT,
            bg=BG,
        ).pack(anchor="w", padx=16, pady=(14, 4))

        contact = tk.Frame(win, bg=PANEL)
        contact.pack(fill="x", padx=16, pady=(0, 8))
        tk.Label(
            contact,
            text="Need a license?",
            font=("Segoe UI", 9, "bold"),
            fg=TEXT,
            bg=PANEL,
        ).pack(anchor="w", padx=12, pady=(10, 2))
        tk.Label(
            contact,
            text=f"{LICENSE_CONTACT_HINT}\n{LICENSE_CONTACT_LABEL}",
            font=("Segoe UI", 9),
            fg=MUTED,
            bg=PANEL,
            justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 8))
        ttk.Button(contact, text="Open Telegram", command=self._open_license_contact).pack(
            anchor="w", padx=12, pady=(0, 10)
        )

        if note:
            tk.Label(
                win,
                text=note,
                font=("Segoe UI", 9),
                fg=WARN,
                bg=BG,
                wraplength=500,
                justify="left",
            ).pack(anchor="w", padx=16, pady=(0, 8))

        panel = tk.Frame(win, bg=PANEL)
        panel.pack(fill="both", expand=True, padx=16, pady=8)

        mid_var = tk.StringVar(value=get_machine_id())
        tk.Label(panel, text="Your Machine ID (send to author):", fg=MUTED, bg=PANEL, font=("Segoe UI", 9)).pack(
            anchor="w", padx=12, pady=(12, 2)
        )
        row = tk.Frame(panel, bg=PANEL)
        row.pack(fill="x", padx=12)
        tk.Entry(
            row,
            textvariable=mid_var,
            font=("Consolas", 9),
            state="readonly",
            readonlybackground="#0d1117",
            fg=TEXT,
            relief="flat",
        ).pack(side="left", fill="x", expand=True, ipady=4)

        def copy_mid() -> None:
            win.clipboard_clear()
            win.clipboard_append(mid_var.get())
            status_var.set("Machine ID copied.")

        ttk.Button(row, text="Copy", command=copy_mid).pack(side="left", padx=(8, 0))

        tk.Label(
            panel,
            text="License key (VCPM-.... online  or  VCPM2.... offline):",
            fg=MUTED,
            bg=PANEL,
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=12, pady=(12, 2))
        key_entry = tk.Entry(panel, font=("Consolas", 9), bg="#0d1117", fg=TEXT, relief="flat")
        key_entry.pack(fill="x", padx=12, ipady=6)
        key_entry.focus_set()
        status_var = tk.StringVar()
        tk.Label(panel, textvariable=status_var, fg=MUTED, bg=PANEL, font=("Segoe UI", 9), wraplength=480).pack(
            anchor="w", padx=12, pady=8
        )

        def activate() -> None:
            status_var.set("Checking license…")
            key = key_entry.get().strip()
            if not key:
                status_var.set("Paste your license key first.")
                return

            def work() -> None:
                try:
                    result = activate_license_key(key)
                except Exception as exc:
                    result = LicenseStatus(False, str(exc))

                def done() -> None:
                    status_var.set(result.message)
                    if result.ok:
                        self._refresh_license_panel()
                        self._enqueue_log(result.message)
                        win.destroy()
                        self._show_activation_success(result)

                win.after(0, done)

            threading.Thread(target=work, daemon=True).start()

        btn_row = tk.Frame(panel, bg=PANEL)
        btn_row.pack(anchor="w", padx=12, pady=(0, 12))
        ttk.Button(btn_row, text="Activate license", command=activate).pack(side="left")
        ttk.Button(btn_row, text="Cancel", command=win.destroy).pack(side="left", padx=(8, 0))
        center_tk_window(win, width=540, height=460, parent=self.root)

    def _ensure_licensed(self) -> bool:
        status = current_license_status()
        self._refresh_license_panel()
        if status.ok:
            return True
        self._show_license_dialog(status.message)
        return current_license_status().ok

    def _build_main_ui(self) -> None:
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=16, pady=(16, 8))

        title_row = tk.Frame(header, bg=BG)
        title_row.pack(anchor="w")

        self._header_logo = self._load_header_logo()
        if self._header_logo is not None:
            tk.Label(title_row, image=self._header_logo, bg=BG).pack(side="left", padx=(0, 12))

        title_text = tk.Frame(title_row, bg=BG)
        title_text.pack(side="left")
        tk.Label(
            title_text,
            text=STUDIO_NAME,
            font=("Segoe UI", 18, "bold"),
            fg=TEXT,
            bg=BG,
        ).pack(anchor="w")
        tk.Label(
            title_text,
            text="Voice studio · setup runs quietly in the background",
            font=("Segoe UI", 10),
            fg=MUTED,
            bg=BG,
        ).pack(anchor="w")

        self.access_var = tk.StringVar()
        self._build_license_panel()

        req_frame = tk.LabelFrame(
            self.root,
            text=" Requirements ",
            font=("Segoe UI", 10, "bold"),
            fg=TEXT,
            bg=PANEL,
            labelanchor="n",
        )
        req_frame.pack(fill="x", padx=16, pady=8)

        self.req_grid = tk.Frame(req_frame, bg=PANEL)
        self.req_grid.pack(fill="x", padx=12, pady=10)

        btn_row = tk.Frame(self.root, bg=BG)
        btn_row.pack(fill="x", padx=16, pady=4)

        ttk.Button(btn_row, text="Refresh checks", command=self.refresh_checks_async).pack(
            side="left", padx=(0, 8)
        )
        self.setup_btn = ttk.Button(btn_row, text="Run setup", command=self._run_setup)
        self.setup_btn.pack(side="left", padx=(0, 8))
        ttk.Button(btn_row, text="Enter license", command=lambda: self._show_license_dialog()).pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(btn_row, text="Get a license", command=self._open_license_contact).pack(side="left")
        ttk.Button(btn_row, text="Check for updates", command=lambda: self._check_updates(manual=True)).pack(
            side="left", padx=(8, 0)
        )

        srv_row = tk.Frame(self.root, bg=BG)
        srv_row.pack(fill="x", padx=16, pady=8)

        self.status_var = tk.StringVar(value="Status: Stopped")
        tk.Label(
            srv_row,
            textvariable=self.status_var,
            font=("Segoe UI", 11, "bold"),
            fg=TEXT,
            bg=BG,
        ).pack(side="left")

        ttk.Button(srv_row, text="Start Studio", command=self._start).pack(side="right", padx=(8, 0))
        ttk.Button(srv_row, text="Stop", command=self._stop).pack(side="right", padx=(8, 0))
        ttk.Button(srv_row, text="Open UI", command=self._open_ui).pack(side="right")

        log_toggle_row = tk.Frame(self.root, bg=BG)
        log_toggle_row.pack(fill="x", padx=16, pady=(4, 0))
        self.log_toggle_btn = ttk.Button(log_toggle_row, text="Show activity log", command=self._toggle_log)
        self.log_toggle_btn.pack(side="left")
        tk.Label(
            log_toggle_row,
            text="Setup progress, downloads, and server messages",
            font=("Segoe UI", 9),
            fg=MUTED,
            bg=BG,
        ).pack(side="left", padx=(10, 0))

        self.log_frame = tk.LabelFrame(
            self.root,
            text=" Activity log ",
            font=("Segoe UI", 10, "bold"),
            fg=TEXT,
            bg=PANEL,
            labelanchor="n",
            highlightbackground="#30363d",
            highlightthickness=1,
        )
        # Hidden by default; auto-opens during setup.

        log_header = tk.Frame(self.log_frame, bg=PANEL)
        log_header.pack(fill="x", padx=10, pady=(10, 4))

        tk.Label(
            log_header,
            text="Current task",
            font=("Segoe UI", 8),
            fg=MUTED,
            bg=PANEL,
        ).pack(anchor="w")
        self._activity_var = tk.StringVar(value="Idle")
        tk.Label(
            log_header,
            textvariable=self._activity_var,
            font=("Segoe UI", 10, "bold"),
            fg=TEXT,
            bg=PANEL,
            anchor="w",
        ).pack(fill="x", pady=(2, 0))

        progress_row = tk.Frame(self.log_frame, bg=PANEL)
        progress_row.pack(fill="x", padx=10, pady=(0, 6))

        style = ttk.Style(self.root)
        style.configure(
            "Studio.Horizontal.TProgressbar",
            troughcolor="#0d1117",
            background=OK,
            darkcolor=OK,
            lightcolor=OK,
            bordercolor=PANEL,
            thickness=10,
        )
        self._log_progress = ttk.Progressbar(
            progress_row,
            maximum=100,
            mode="determinate",
            style="Studio.Horizontal.TProgressbar",
        )
        self._log_progress.pack(side="left", fill="x", expand=True)
        self._log_pct_var = tk.StringVar(value="")
        tk.Label(
            progress_row,
            textvariable=self._log_pct_var,
            font=("Consolas", 9, "bold"),
            fg=OK,
            bg=PANEL,
            width=5,
        ).pack(side="right", padx=(8, 0))

        self._log_detail_var = tk.StringVar(value="")
        tk.Label(
            self.log_frame,
            textvariable=self._log_detail_var,
            font=("Consolas", 9),
            fg=MUTED,
            bg=PANEL,
            anchor="w",
        ).pack(fill="x", padx=10, pady=(0, 4))

        log_toolbar = tk.Frame(self.log_frame, bg=PANEL)
        log_toolbar.pack(fill="x", padx=10, pady=(0, 4))
        ttk.Button(log_toolbar, text="Clear log", command=self._clear_log).pack(side="right")

        log_colors = {
            "info": TEXT,
            "ok": OK,
            "warn": WARN,
            "err": ERR,
            "cmd": "#79c0ff",
            "dim": MUTED,
            "title": "#a371f7",
        }
        self.log_box = scrolledtext.ScrolledText(
            self.log_frame,
            height=12,
            font=("Consolas", 9),
            bg="#0d1117",
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            highlightthickness=1,
            highlightbackground="#21262d",
            highlightcolor="#21262d",
            state="disabled",
            wrap="word",
        )
        for tag, color in log_colors.items():
            font = ("Consolas", 9, "bold") if tag == "title" else ("Consolas", 9)
            self.log_box.tag_configure(tag, foreground=color, font=font)
        self.log_box.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        foot = tk.Frame(self.root, bg=BG)
        foot.pack(fill="x", padx=16, pady=(8, 10))
        self._version_var = tk.StringVar(value=f"v{get_studio_release_version()}")
        tk.Label(
            foot,
            textvariable=self._version_var,
            font=("Segoe UI", 9),
            fg=MUTED,
            bg=BG,
        ).pack(side="right")
        self._update_var = tk.StringVar(value="")
        tk.Label(
            foot,
            textvariable=self._update_var,
            font=("Segoe UI", 9),
            fg=WARN,
            bg=BG,
        ).pack(side="right", padx=(0, 12))
        tk.Label(
            foot,
            text=f"License support: {LICENSE_CONTACT_LABEL}",
            font=("Segoe UI", 9),
            fg=MUTED,
            bg=BG,
        ).pack(side="left")
        tk.Label(
            foot,
            text="Open Telegram",
            font=("Segoe UI", 9, "underline"),
            fg=OK,
            bg=BG,
            cursor="hand2",
        ).pack(side="left", padx=(8, 0))
        foot.winfo_children()[-1].bind("<Button-1>", lambda _e: self._open_license_contact())

    def _refresh_version_label(self) -> None:
        self._version_var.set(f"v{get_studio_release_version()}")

    def _set_update_status(self, status: UpdateStatus) -> None:
        self._update_status = status
        if status.update_available:
            self._update_var.set(f"Update available: v{status.latest}")
        else:
            self._update_var.set("")

    def _check_updates_quiet(self) -> None:
        if self._update_snoozed:
            return

        def work() -> None:
            try:
                status = check_for_updates()
            except Exception:
                return

            def notify() -> None:
                self._set_update_status(status)
                if not status.update_available:
                    return
                if messagebox.askyesno(
                    "Update available",
                    f"Version {status.latest} is available (you have {status.current}).\n\n"
                    "Open the update options now?",
                ):
                    self._show_update_dialog(status)

            self.root.after(0, notify)

        threading.Thread(target=work, daemon=True).start()

    def _check_updates(self, *, manual: bool) -> None:
        self._enqueue_log("Checking for updates…")

        def work() -> None:
            status = check_for_updates()

            def done() -> None:
                self._set_update_status(status)
                if status.error:
                    self._enqueue_log(f"Update check failed: {status.error}")
                    if manual:
                        messagebox.showwarning(
                            "Update check failed",
                            f"Could not reach GitHub.\n\n{status.error}",
                        )
                    return
                if not status.update_available:
                    self._enqueue_log(f"Up to date (v{status.current}).")
                    if manual:
                        messagebox.showinfo("Up to date", f"You have the latest version (v{status.current}).")
                    return
                self._enqueue_log(f"Update available: v{status.latest} (you have v{status.current}).")
                self._show_update_dialog(status)

            self.root.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def _show_update_dialog(self, status: UpdateStatus) -> None:
        if status.can_git_update:
            choice = messagebox.askyesnocancel(
                "Update available",
                f"Version {status.latest} is available (you have {status.current}).\n\n"
                "Yes = Update now (git pull)\n"
                "No = Open download page (ZIP install)\n"
                "Cancel = Later",
            )
            if choice is True:
                self._run_git_update()
            elif choice is False:
                import webbrowser

                webbrowser.open(status.zip_url)
                messagebox.showinfo(
                    "Download update",
                    "Download the ZIP, extract it, and replace your app folder.\n\n"
                    "Keep your data\\license.json file if you want to keep the same license.",
                )
            else:
                self._update_snoozed = True
            return

        if messagebox.askyesno(
            "Update available",
            f"Version {status.latest} is available (you have {status.current}).\n\n"
            "Open the download page?",
        ):
            import webbrowser

            webbrowser.open(status.zip_url)
            messagebox.showinfo(
                "Download update",
                "Download the ZIP, extract it, and replace your app folder.\n\n"
                "Keep your data\\license.json file if you want to keep the same license.",
            )

    def _run_git_update(self) -> None:
        self._enqueue_log("Applying update…")

        def work() -> None:
            ok, msg = apply_git_update(self._enqueue_log)

            def done() -> None:
                self._refresh_version_label()
                if ok:
                    status = check_for_updates()
                    self._set_update_status(status)
                    messagebox.showinfo(
                        "Updated",
                        f"{msg}\n\nSetup will run if anything new is needed.",
                    )
                    if status.update_available:
                        messagebox.showwarning(
                            "Update incomplete",
                            "Files were pulled but version did not change.\n\n"
                            "Use Check for updates → No to download the ZIP.",
                        )
                    else:
                        self._update_snoozed = True
                    self._run_setup()
                else:
                    messagebox.showerror("Update failed", msg)

            self.root.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def _build_license_panel(self) -> None:
        frame = tk.LabelFrame(
            self.root,
            text=" License ",
            font=("Segoe UI", 10, "bold"),
            fg=TEXT,
            bg=PANEL,
            labelanchor="n",
        )
        frame.pack(fill="x", padx=16, pady=(4, 8))

        inner = tk.Frame(frame, bg=PANEL)
        inner.pack(fill="x", padx=12, pady=10)

        top = tk.Frame(inner, bg=PANEL)
        top.pack(fill="x")

        self.license_state_var = tk.StringVar(value="Checking…")
        self.license_state_label = tk.Label(
            top,
            textvariable=self.license_state_var,
            font=("Segoe UI", 12, "bold"),
            fg=TEXT,
            bg=PANEL,
        )
        self.license_state_label.pack(side="left")

        ttk.Button(top, text="Enter license", command=lambda: self._show_license_dialog()).pack(
            side="right"
        )

        self.license_remaining_var = tk.StringVar(value="—")
        self.license_remaining_label = tk.Label(
            inner,
            textvariable=self.license_remaining_var,
            font=("Segoe UI", 14, "bold"),
            fg=OK,
            bg=PANEL,
        )
        self.license_remaining_label.pack(anchor="w", pady=(8, 2))

        self.license_expires_var = tk.StringVar(value="")
        tk.Label(
            inner,
            textvariable=self.license_expires_var,
            font=("Segoe UI", 9),
            fg=MUTED,
            bg=PANEL,
        ).pack(anchor="w")

        self.license_type_var = tk.StringVar(value="")
        tk.Label(
            inner,
            textvariable=self.license_type_var,
            font=("Segoe UI", 8),
            fg=MUTED,
            bg=PANEL,
        ).pack(anchor="w", pady=(2, 0))

        self.license_progress = ttk.Progressbar(inner, maximum=100, mode="determinate")
        self.license_progress.pack_forget()

    def _show_log_panel_if_hidden(self) -> None:
        if not self._log_visible:
            self._toggle_log()

    def _clear_log(self) -> None:
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", tk.END)
        self.log_box.configure(state="disabled")
        self._log_line_count = 0

    def _toggle_log(self) -> None:
        if self._log_visible:
            self.log_frame.pack_forget()
            self._log_visible = False
            self.log_toggle_btn.configure(text="Show activity log")
        else:
            self.log_frame.pack(fill="both", expand=True, padx=16, pady=(8, 12))
            self._log_visible = True
            self.log_toggle_btn.configure(text="Hide activity log")

    def _apply_checks(self, checks) -> None:
        for child in self.req_grid.winfo_children():
            child.destroy()

        for i, item in enumerate(checks):
            icon = "✓" if item.ok else ("!" if not item.required else "✗")
            color = OK if item.ok else (WARN if not item.required else ERR)
            row = tk.Frame(self.req_grid, bg=PANEL)
            row.grid(row=i // 2, column=i % 2, sticky="w", padx=6, pady=3)

            tk.Label(
                row, text=icon, fg=color, bg=PANEL, width=2, font=("Segoe UI", 10, "bold")
            ).pack(side="left")
            tk.Label(
                row,
                text=f"{item.label}: {item.detail}",
                fg=TEXT,
                bg=PANEL,
                font=("Segoe UI", 9),
                anchor="w",
            ).pack(side="left")

        self._checks_busy = False

    def refresh_checks_async(self) -> None:
        if self._checks_busy:
            return
        self._checks_busy = True

        def work() -> None:
            checks = run_checks()
            self.root.after(0, lambda: self._apply_checks(checks))

        threading.Thread(target=work, daemon=True).start()

    def _run_async(self, fn, *, refresh_after: bool = True) -> None:
        def worker() -> None:
            try:
                fn()
            except Exception as exc:
                self._enqueue_log(f"Error: {exc}")
            finally:
                if refresh_after:
                    self.root.after(0, self.refresh_checks_async)

        threading.Thread(target=worker, daemon=True).start()

    def _set_setup_busy(self, busy: bool) -> None:
        try:
            self.setup_btn.configure(state="disabled" if busy else "normal")
        except Exception:
            pass

    def _run_setup(self) -> None:
        self.root.after(0, self._show_log_panel_if_hidden)
        self.root.after(0, lambda: self._begin_activity("Running setup…"))
        self.root.after(0, lambda: self._set_setup_busy(True))
        self._last_progress_log_pct = -1
        self._enqueue_log("Running setup…")

        def work() -> None:
            try:
                ok = self.manager.setup()
                if not ok:
                    self.root.after(0, lambda: self._finish_activity(success=False))
            except Exception as exc:
                self._enqueue_log(f"Error: {exc}")
                self.root.after(0, lambda: self._finish_activity(success=False))
            finally:
                self.root.after(0, lambda: self._set_setup_busy(False))
                self.root.after(0, self.refresh_checks_async)

        threading.Thread(target=work, daemon=True).start()

    def _start(self) -> None:
        if not self._ensure_licensed():
            return

        def work() -> None:
            checks = run_checks()
            ready = all(c.ok for c in checks if c.required and c.key != "servers")
            if not ready:

                def ask() -> None:
                    if messagebox.askyesno(
                        "Setup required",
                        "Some requirements are missing.\n\nRun setup now?",
                    ):
                        self._run_setup()

                self.root.after(0, ask)
                return
            self.manager.start(open_browser=True)
            self.root.after(0, self._wait_and_refresh_checks)

        threading.Thread(target=work, daemon=True).start()

    def _stop(self) -> None:
        self._run_async(self.manager.stop)

    def _open_ui(self) -> None:
        if not self._ensure_licensed():
            return

        def work() -> None:
            if not self.manager.running and not (_port_open(8000) and _port_open(3000)):
                checks = run_checks()
                ready = all(c.ok for c in checks if c.required and c.key != "servers")
                if not ready:
                    self.root.after(
                        0,
                        lambda: messagebox.showwarning(
                            "Setup required",
                            "Finish setup first (Run setup), then open the UI.",
                        ),
                    )
                    return
                if not self.manager.start(open_browser=False):
                    return
                self.root.after(0, self._wait_and_refresh_checks)
            import webbrowser

            webbrowser.open("http://localhost:3000/home")
            if self.manager.running or (_port_open(8000) and _port_open(3000)):
                self.root.after(0, self.refresh_checks_async)

        threading.Thread(target=work, daemon=True).start()

    def _on_close(self) -> None:
        if self.manager.running:
            if messagebox.askyesno("Quit", "Stop servers and close launcher?"):
                self.manager.stop()
            else:
                return
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    StudioLauncherApp().run()


if __name__ == "__main__":
    main()
