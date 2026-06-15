"""VoxCPM2 Studio — graphical launcher (replaces CMD workflow)."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

from launcher_core import (
    PROJECT_ROOT,
    StudioManager,
    _port_open,
    bootstrap_studio,
    run_checks,
)

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
        self.root.title("VoxCPM2 Studio Launcher")
        self.root.geometry("720x640")
        self.root.minsize(600, 520)
        self.root.configure(bg=BG)

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.manager = StudioManager(log=self._enqueue_log)
        self._checks_busy = False
        self._log_line_count = 0

        self.root.withdraw()
        self._build_ui()
        self.root.after(150, self._poll_log)
        self.root.after(3000, self._poll_server_status)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        threading.Thread(target=self._auto_bootstrap, daemon=True).start()

    def _auto_bootstrap(self) -> None:
        self._enqueue_log("Starting VoxCPM2 Studio automatically…")
        try:
            bootstrap_studio(self.manager, open_browser=True)
        except Exception as exc:
            self._enqueue_log(f"Startup error: {exc}")
        self.root.after(0, self._show_gui)

    def _show_gui(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self.refresh_checks_async()

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

    def _build_ui(self) -> None:
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=16, pady=(16, 8))
        tk.Label(
            header,
            text="VoxCPM2 Studio",
            font=("Segoe UI", 18, "bold"),
            fg=TEXT,
            bg=BG,
        ).pack(anchor="w")
        tk.Label(
            header,
            text="Setup · start/stop · logs — no CMD windows.",
            font=("Segoe UI", 10),
            fg=MUTED,
            bg=BG,
        ).pack(anchor="w")

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
        import webbrowser

        webbrowser.open("http://localhost:3000/home")

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
