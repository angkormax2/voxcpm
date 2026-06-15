"""VoxCPM2 Studio — graphical launcher (replaces CMD workflow)."""

from __future__ import annotations

import queue
import sys
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

from license_manager import (
    LicenseStatus,
    activate_license_key,
    current_license_status,
    get_machine_id,
)
from studio_branding import STUDIO_NAME
from launcher_core import (
    PROJECT_ROOT,
    StudioManager,
    _port_open,
    bootstrap_setup,
    run_checks,
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
        self.root.geometry("720x640")
        self.root.minsize(600, 520)
        self.root.configure(bg=BG)

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.manager = StudioManager(log=self._enqueue_log)
        self._checks_busy = False
        self._log_line_count = 0
        self._window_icon: tk.PhotoImage | None = None
        self._header_logo: tk.PhotoImage | None = None
        self._setup_started = False

        self._set_window_icon()
        self._build_main_ui()

        self.root.after(150, self._poll_log)
        self.root.after(3000, self._poll_server_status)
        self.root.after(1000, self._poll_access_status)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._enqueue_log(f"Welcome to {STUDIO_NAME}")
        self._update_access_label()
        if not self._setup_started:
            self._setup_started = True
            threading.Thread(target=self._auto_setup, daemon=True).start()

    def _auto_setup(self) -> None:
        self._enqueue_log("Checking install requirements (no license needed for setup)…")
        try:
            bootstrap_setup(self.manager)
        except Exception as exc:
            self._enqueue_log(f"Setup error: {exc}")
        self.root.after(0, self.refresh_checks_async)

    def _enqueue_log(self, msg: str) -> None:
        self.log_queue.put(msg)

    def _poll_log(self) -> None:
        batch = 0
        while batch < 40:
            try:
                line = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self.log_box.configure(state="normal")
            self.log_box.insert(tk.END, line + "\n")
            self._log_line_count += 1
            if self._log_line_count > MAX_LOG_LINES:
                self.log_box.delete("1.0", f"{self._log_line_count - MAX_LOG_LINES}.0")
                self._log_line_count = MAX_LOG_LINES
            self.log_box.see(tk.END)
            self.log_box.configure(state="disabled")
            batch += 1
        self.root.after(150, self._poll_log)

    def _poll_server_status(self) -> None:
        if self.manager.running or (_port_open(8000) and _port_open(3000)):
            self.status_var.set("Status: Running")
        else:
            self.status_var.set("Status: Stopped")
        self.root.after(3000, self._poll_server_status)

    def _poll_access_status(self) -> None:
        self._update_access_label()
        self.root.after(10000, self._poll_access_status)

    def _update_access_label(self) -> None:
        status = current_license_status()
        if status.ok:
            self.access_var.set(status.message)
        else:
            self.access_var.set("No license — Enter license before Open UI or Start Studio")

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
        win.geometry("520x380")
        win.transient(self.root)
        win.grab_set()

        tk.Label(
            win,
            text="License activation",
            font=("Segoe UI", 14, "bold"),
            fg=TEXT,
            bg=BG,
        ).pack(anchor="w", padx=16, pady=(14, 4))
        if note:
            tk.Label(
                win,
                text=note,
                font=("Segoe UI", 9),
                fg=WARN,
                bg=BG,
                wraplength=480,
                justify="left",
            ).pack(anchor="w", padx=16, pady=(0, 8))

        panel = tk.Frame(win, bg=PANEL)
        panel.pack(fill="both", expand=True, padx=16, pady=8)

        mid_var = tk.StringVar(value=get_machine_id())
        tk.Label(panel, text="Machine ID:", fg=MUTED, bg=PANEL, font=("Segoe UI", 9)).pack(
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

        ttk.Button(row, text="Copy", command=copy_mid).pack(side="left", padx=(8, 0))

        tk.Label(
            panel,
            text="License key (VCPM-.... online or VCPM2.... offline):",
            fg=MUTED,
            bg=PANEL,
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=12, pady=(10, 2))
        key_entry = tk.Entry(panel, font=("Consolas", 9), bg="#0d1117", fg=TEXT, relief="flat")
        key_entry.pack(fill="x", padx=12, ipady=5)
        status_var = tk.StringVar()
        tk.Label(panel, textvariable=status_var, fg=MUTED, bg=PANEL, font=("Segoe UI", 9), wraplength=460).pack(
            anchor="w", padx=12, pady=8
        )

        def activate() -> None:
            status_var.set("Checking…")
            key = key_entry.get().strip()

            def work() -> None:
                try:
                    result = activate_license_key(key)
                except Exception as exc:
                    result = LicenseStatus(False, str(exc))

                def done() -> None:
                    status_var.set(result.message)
                    if result.ok:
                        self._update_access_label()
                        self._enqueue_log(result.message)
                        win.destroy()

                win.after(0, done)

            threading.Thread(target=work, daemon=True).start()

        btn_row = tk.Frame(panel, bg=PANEL)
        btn_row.pack(anchor="w", padx=12, pady=(0, 12))
        ttk.Button(btn_row, text="Activate", command=activate).pack(side="left")
        ttk.Button(btn_row, text="Close", command=win.destroy).pack(side="left", padx=(8, 0))
        tk.Label(
            panel,
            text="Get a key: t.me/rornpisith",
            fg=MUTED,
            bg=PANEL,
            font=("Segoe UI", 8),
        ).pack(anchor="w", padx=12, pady=(0, 12))

    def _ensure_licensed(self) -> bool:
        status = current_license_status()
        self._update_access_label()
        if status.ok:
            return True
        self._show_license_dialog(status.message)
        return False

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
            text="Setup runs automatically · license required for Open UI / Start Studio",
            font=("Segoe UI", 10),
            fg=MUTED,
            bg=BG,
        ).pack(anchor="w")

        self.access_var = tk.StringVar()
        tk.Label(
            header,
            textvariable=self.access_var,
            font=("Segoe UI", 9),
            fg=MUTED,
            bg=BG,
            wraplength=680,
            justify="left",
        ).pack(anchor="w", pady=(6, 0))

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
        ttk.Button(btn_row, text="Run setup", command=self._run_setup).pack(side="left", padx=(0, 8))
        ttk.Button(btn_row, text="Enter license", command=lambda: self._show_license_dialog()).pack(
            side="left"
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

        log_frame = tk.LabelFrame(
            self.root,
            text=" Log ",
            font=("Segoe UI", 10, "bold"),
            fg=TEXT,
            bg=PANEL,
            labelanchor="n",
        )
        log_frame.pack(fill="both", expand=True, padx=16, pady=(8, 16))

        self.log_box = scrolledtext.ScrolledText(
            log_frame,
            height=14,
            font=("Consolas", 9),
            bg="#0d1117",
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            state="disabled",
        )
        self.log_box.pack(fill="both", expand=True, padx=8, pady=8)

        foot = tk.Label(
            self.root,
            text=f"Project: {PROJECT_ROOT}",
            font=("Segoe UI", 8),
            fg=MUTED,
            bg=BG,
        )
        foot.pack(anchor="w", padx=16, pady=(0, 10))

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

    def _run_setup(self) -> None:
        self._enqueue_log("Running setup…")
        self._run_async(self.manager.setup)

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
            self.root.after(0, self.refresh_checks_async)

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
            import webbrowser

            webbrowser.open("http://localhost:3000/home")
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
