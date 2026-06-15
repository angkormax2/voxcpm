"""VoxCPM2 Studio — License Admin GUI (offline + online keys)."""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from importlib.machinery import SourceFileLoader

_issue = SourceFileLoader(
    "issue_license", str(PROJECT_ROOT / "tools" / "issue_license.py")
).load_module()

from license_config import get_license_server_url  # noqa: E402
from license_manager import activate_license_key, get_machine_id, verify_signed_license  # noqa: E402

ASSETS = PROJECT_ROOT / "assets"
ICON_ICO = ASSETS / "studio_launcher.ico"
ADMIN_CONFIG = PROJECT_ROOT / "data" / "license_admin_config.json"
SERVER_URL_FILE = ASSETS / "license_server.url"

BG = "#0f1117"
PANEL = "#1a1d2e"
TEXT = "#e6edf3"
MUTED = "#8b949e"
OK = "#3fb950"
ERR = "#f85149"


class LicenseAdminApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("VoxCPM2 License Admin")
        self.root.geometry("760x680")
        self.root.minsize(640, 560)
        self.root.configure(bg=BG)
        self._set_icon()

        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=16, pady=(14, 6))
        tk.Label(
            header,
            text="VoxCPM2 License Admin",
            font=("Segoe UI", 18, "bold"),
            fg=TEXT,
            bg=BG,
        ).pack(anchor="w")
        tk.Label(
            header,
            text="Create offline keys, issue online keys (Firebase), and verify licenses",
            font=("Segoe UI", 10),
            fg=MUTED,
            bg=BG,
        ).pack(anchor="w")

        self._key_status = tk.StringVar()
        self._update_key_status()

        status_row = tk.Frame(self.root, bg=BG)
        status_row.pack(fill="x", padx=16, pady=(0, 8))
        tk.Label(
            status_row,
            textvariable=self._key_status,
            font=("Segoe UI", 9),
            fg=MUTED,
            bg=BG,
            wraplength=700,
            justify="left",
        ).pack(anchor="w")
        if not _issue.private_key_ready():
            ttk.Button(status_row, text="Generate signing keys", command=self._generate_keys).pack(
                anchor="w", pady=(6, 0)
            )

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=16, pady=8)

        self._tab_create(notebook)
        self._tab_online(notebook)
        self._tab_verify(notebook)
        self._tab_test_activate(notebook)

        foot = tk.Label(
            self.root,
            text=f"Signing key: tools/license_private.pem  ·  Keep secret, never commit",
            font=("Segoe UI", 8),
            fg=MUTED,
            bg=BG,
        )
        foot.pack(anchor="w", padx=16, pady=(0, 10))

    def _set_icon(self) -> None:
        try:
            if sys.platform == "win32" and ICON_ICO.is_file():
                self.root.iconbitmap(default=str(ICON_ICO))
        except Exception:
            pass

    def _update_key_status(self) -> None:
        if _issue.private_key_ready():
            self._key_status.set("Signing keys: ready")
        else:
            self._key_status.set(
                "Signing keys: missing — click Generate signing keys or run python tools/generate_license_keys.py"
            )

    def _panel(self, parent: tk.Widget, title: str) -> tk.Frame:
        frame = tk.LabelFrame(
            parent,
            text=f" {title} ",
            font=("Segoe UI", 10, "bold"),
            fg=TEXT,
            bg=PANEL,
            labelanchor="n",
        )
        frame.pack(fill="both", expand=True, padx=8, pady=8)
        inner = tk.Frame(frame, bg=PANEL)
        inner.pack(fill="both", expand=True, padx=12, pady=12)
        return inner

    def _load_admin_config(self) -> dict:
        if ADMIN_CONFIG.is_file():
            try:
                return json.loads(ADMIN_CONFIG.read_text(encoding="utf-8"))
            except Exception:
                pass
        url = get_license_server_url()
        return {"server_url": url, "admin_secret": ""}

    def _save_admin_config(self, server_url: str, admin_secret: str) -> None:
        ADMIN_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        ADMIN_CONFIG.write_text(
            json.dumps(
                {"server_url": server_url.strip().rstrip("/"), "admin_secret": admin_secret},
                indent=2,
            ),
            encoding="utf-8",
        )

    def _admin_request(
        self, method: str, path: str, payload: dict | None = None
    ) -> dict:
        server = self._online_server.get().strip().rstrip("/")
        secret = self._online_secret.get().strip()
        if not server:
            raise RuntimeError("Enter the license server URL.")
        if not secret:
            raise RuntimeError("Enter the admin secret.")

        data = None
        headers = {
            "Content-Type": "application/json",
            "X-Admin-Secret": secret,
            "User-Agent": "VoxCPM2-LicenseAdmin/1.0",
        }
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{server}{path}", data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            detail = exc.reason or "Request failed"
            try:
                detail = json.loads(exc.read().decode("utf-8")).get("detail", detail)
            except Exception:
                pass
            raise RuntimeError(str(detail)) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Cannot reach server: {exc.reason}") from exc

    def _tab_online(self, notebook: ttk.Notebook) -> None:
        tab = tk.Frame(notebook, bg=BG)
        notebook.add(tab, text="  Online keys  ")
        inner = self._panel(tab, "Firebase / FastAPI Cloud (revocable keys)")

        cfg = self._load_admin_config()
        self._online_server = tk.StringVar(value=cfg.get("server_url", ""))
        self._online_secret = tk.StringVar(value=cfg.get("admin_secret", ""))

        tk.Label(inner, text="License server URL:", fg=MUTED, bg=PANEL, font=("Segoe UI", 9)).pack(
            anchor="w"
        )
        tk.Entry(
            inner,
            textvariable=self._online_server,
            font=("Consolas", 9),
            bg="#0d1117",
            fg=TEXT,
            relief="flat",
        ).pack(fill="x", pady=(4, 8), ipady=4)

        tk.Label(inner, text="Admin secret (X-Admin-Secret):", fg=MUTED, bg=PANEL, font=("Segoe UI", 9)).pack(
            anchor="w"
        )
        tk.Entry(
            inner,
            textvariable=self._online_secret,
            font=("Consolas", 9),
            bg="#0d1117",
            fg=TEXT,
            relief="flat",
            show="*",
        ).pack(fill="x", pady=(4, 8), ipady=4)

        btn_row = tk.Frame(inner, bg=PANEL)
        btn_row.pack(fill="x", pady=(0, 8))
        ttk.Button(btn_row, text="Save settings", command=self._save_online_settings).pack(side="left")
        ttk.Button(btn_row, text="Write URL to app", command=self._write_server_url_file).pack(
            side="left", padx=(8, 0)
        )

        row2 = tk.Frame(inner, bg=PANEL)
        row2.pack(fill="x", pady=(0, 8))
        tk.Label(row2, text="Valid days:", fg=MUTED, bg=PANEL, font=("Segoe UI", 9)).pack(side="left")
        self._online_days = tk.IntVar(value=365)
        tk.Spinbox(row2, from_=1, to=3650, textvariable=self._online_days, width=8).pack(
            side="left", padx=(8, 16)
        )
        tk.Label(row2, text="Label:", fg=MUTED, bg=PANEL, font=("Segoe UI", 9)).pack(side="left")
        self._online_label = tk.StringVar()
        tk.Entry(
            row2,
            textvariable=self._online_label,
            font=("Segoe UI", 10),
            bg="#0d1117",
            fg=TEXT,
            relief="flat",
            width=24,
        ).pack(side="left", padx=(8, 0), ipady=3)

        act_row = tk.Frame(inner, bg=PANEL)
        act_row.pack(fill="x", pady=(0, 8))
        ttk.Button(act_row, text="Issue online key", command=self._issue_online_key).pack(side="left")
        ttk.Button(act_row, text="List recent", command=self._list_online_keys).pack(side="left", padx=(8, 0))

        tk.Label(inner, text="Revoke license ID:", fg=MUTED, bg=PANEL, font=("Segoe UI", 9)).pack(anchor="w")
        rev_row = tk.Frame(inner, bg=PANEL)
        rev_row.pack(fill="x", pady=(4, 8))
        self._revoke_id = tk.StringVar()
        tk.Entry(
            rev_row,
            textvariable=self._revoke_id,
            font=("Consolas", 9),
            bg="#0d1117",
            fg=TEXT,
            relief="flat",
        ).pack(side="left", fill="x", expand=True, ipady=4)
        ttk.Button(rev_row, text="Revoke", command=self._revoke_online_key).pack(side="left", padx=(8, 0))

        self._online_output = scrolledtext.ScrolledText(
            inner, height=12, font=("Consolas", 9), bg="#0d1117", fg=TEXT, relief="flat"
        )
        self._online_output.pack(fill="both", expand=True, pady=(4, 0))

        tk.Label(
            inner,
            text="Customers enter the short VCPM-.... key in the Studio launcher (binds to one PC).",
            fg=MUTED,
            bg=PANEL,
            font=("Segoe UI", 8),
            wraplength=640,
            justify="left",
        ).pack(anchor="w", pady=(8, 0))

    def _save_online_settings(self) -> None:
        self._save_admin_config(self._online_server.get(), self._online_secret.get())
        messagebox.showinfo("Saved", f"Admin settings saved to {ADMIN_CONFIG.name}")

    def _write_server_url_file(self) -> None:
        url = self._online_server.get().strip().rstrip("/")
        if not url:
            messagebox.showerror("Error", "Enter a server URL first.")
            return
        SERVER_URL_FILE.write_text(f"{url}\n", encoding="utf-8")
        messagebox.showinfo(
            "Saved",
            f"Wrote {SERVER_URL_FILE.name}\n\nShip this file with the app so customers can use online keys.",
        )

    def _issue_online_key(self) -> None:
        try:
            result = self._admin_request(
                "POST",
                "/admin/issue",
                {"days": self._online_days.get(), "label": self._online_label.get()},
            )
        except Exception as exc:
            messagebox.showerror("Error", str(exc))
            return
        self._save_admin_config(self._online_server.get(), self._online_secret.get())
        self._online_output.delete("1.0", tk.END)
        self._online_output.insert(
            tk.END,
            f"Key        : {result.get('key', '')}\n"
            f"Expires    : {result.get('expires', '')}\n"
            f"Label      : {result.get('label') or '(none)'}\n"
            f"License ID : {result.get('license_id', '')}\n",
        )

    def _list_online_keys(self) -> None:
        try:
            result = self._admin_request("GET", "/admin/list?limit=30")
        except Exception as exc:
            messagebox.showerror("Error", str(exc))
            return
        lines = ["Recent online licenses:\n"]
        for row in result.get("licenses", []):
            revoked = " [REVOKED]" if row.get("revoked") else ""
            lines.append(
                f"{row.get('license_id', '')[:8]}…  "
                f"exp={row.get('expires')}  "
                f"pc={row.get('machine_id')}  "
                f"{row.get('label', '')}{revoked}\n"
            )
        self._online_output.delete("1.0", tk.END)
        self._online_output.insert(tk.END, "".join(lines) or "(none)")

    def _revoke_online_key(self) -> None:
        lid = self._revoke_id.get().strip()
        if not lid:
            messagebox.showerror("Error", "Enter a license ID to revoke.")
            return
        if not messagebox.askyesno("Revoke", f"Revoke license {lid}?"):
            return
        try:
            self._admin_request("POST", f"/admin/revoke/{lid}")
        except Exception as exc:
            messagebox.showerror("Error", str(exc))
            return
        messagebox.showinfo("Revoked", f"License {lid} revoked.")
        self._list_online_keys()

        tab = tk.Frame(notebook, bg=BG)
        notebook.add(tab, text="  Create license  ")
        inner = self._panel(tab, "Offline license (one PC)")

        tk.Label(inner, text="Customer Machine ID:", fg=MUTED, bg=PANEL, font=("Segoe UI", 9)).pack(
            anchor="w"
        )
        mid_row = tk.Frame(inner, bg=PANEL)
        mid_row.pack(fill="x", pady=(4, 10))
        self._create_mid = tk.StringVar()
        tk.Entry(
            mid_row,
            textvariable=self._create_mid,
            font=("Consolas", 10),
            bg="#0d1117",
            fg=TEXT,
            relief="flat",
        ).pack(side="left", fill="x", expand=True, ipady=5)
        ttk.Button(mid_row, text="This PC", command=self._use_this_pc_create).pack(side="left", padx=(8, 0))

        row2 = tk.Frame(inner, bg=PANEL)
        row2.pack(fill="x", pady=(0, 10))
        tk.Label(row2, text="Valid days:", fg=MUTED, bg=PANEL, font=("Segoe UI", 9)).pack(side="left")
        self._create_days = tk.IntVar(value=365)
        tk.Spinbox(
            row2,
            from_=1,
            to=3650,
            textvariable=self._create_days,
            width=8,
            font=("Segoe UI", 10),
        ).pack(side="left", padx=(8, 16))
        tk.Label(row2, text="Customer label:", fg=MUTED, bg=PANEL, font=("Segoe UI", 9)).pack(side="left")
        self._create_label = tk.StringVar()
        tk.Entry(
            row2,
            textvariable=self._create_label,
            font=("Segoe UI", 10),
            bg="#0d1117",
            fg=TEXT,
            relief="flat",
            width=28,
        ).pack(side="left", padx=(8, 0), ipady=4)

        ttk.Button(inner, text="Generate license key", command=self._generate_offline).pack(anchor="w", pady=(0, 8))

        self._create_output = scrolledtext.ScrolledText(
            inner,
            height=10,
            font=("Consolas", 9),
            bg="#0d1117",
            fg=TEXT,
            relief="flat",
        )
        self._create_output.pack(fill="both", expand=True, pady=(4, 8))

        btn_row = tk.Frame(inner, bg=PANEL)
        btn_row.pack(fill="x")
        ttk.Button(btn_row, text="Copy key", command=self._copy_create_output).pack(side="left")
        tk.Label(
            btn_row,
            text="Send this full VCPM2.... key to the customer.",
            fg=MUTED,
            bg=PANEL,
            font=("Segoe UI", 8),
        ).pack(side="left", padx=(12, 0))

    def _tab_verify(self, notebook: ttk.Notebook) -> None:
        tab = tk.Frame(notebook, bg=BG)
        notebook.add(tab, text="  Verify key  ")
        inner = self._panel(tab, "Check a license key")

        tk.Label(inner, text="License key:", fg=MUTED, bg=PANEL, font=("Segoe UI", 9)).pack(anchor="w")
        self._verify_key = scrolledtext.ScrolledText(
            inner, height=5, font=("Consolas", 9), bg="#0d1117", fg=TEXT, relief="flat"
        )
        self._verify_key.pack(fill="x", pady=(4, 8))

        tk.Label(inner, text="Machine ID to check against (optional):", fg=MUTED, bg=PANEL, font=("Segoe UI", 9)).pack(
            anchor="w"
        )
        self._verify_mid = tk.StringVar(value=get_machine_id())
        tk.Entry(
            inner,
            textvariable=self._verify_mid,
            font=("Consolas", 10),
            bg="#0d1117",
            fg=TEXT,
            relief="flat",
        ).pack(fill="x", pady=(4, 8), ipady=4)

        ttk.Button(inner, text="Verify", command=self._run_verify).pack(anchor="w", pady=(0, 8))
        self._verify_result = tk.StringVar()
        tk.Label(
            inner,
            textvariable=self._verify_result,
            fg=TEXT,
            bg=PANEL,
            font=("Segoe UI", 10),
            wraplength=640,
            justify="left",
        ).pack(anchor="w")

    def _tab_test_activate(self, notebook: ttk.Notebook) -> None:
        tab = tk.Frame(notebook, bg=BG)
        notebook.add(tab, text="  Test on this PC  ")
        inner = self._panel(tab, "Activate on this computer (testing)")

        tk.Label(
            inner,
            text=f"This PC Machine ID: {get_machine_id()}",
            font=("Consolas", 10),
            fg=TEXT,
            bg=PANEL,
        ).pack(anchor="w", pady=(0, 8))

        tk.Label(inner, text="Paste license key:", fg=MUTED, bg=PANEL, font=("Segoe UI", 9)).pack(anchor="w")
        self._test_key = scrolledtext.ScrolledText(
            inner, height=5, font=("Consolas", 9), bg="#0d1117", fg=TEXT, relief="flat"
        )
        self._test_key.pack(fill="x", pady=(4, 8))
        ttk.Button(inner, text="Activate on this PC", command=self._test_activate).pack(anchor="w", pady=(0, 8))
        self._test_result = tk.StringVar()
        tk.Label(
            inner,
            textvariable=self._test_result,
            fg=TEXT,
            bg=PANEL,
            font=("Segoe UI", 10),
            wraplength=640,
            justify="left",
        ).pack(anchor="w")

    def _use_this_pc_create(self) -> None:
        self._create_mid.set(get_machine_id())

    def _generate_offline(self) -> None:
        if not _issue.private_key_ready():
            messagebox.showerror("Missing keys", "Generate signing keys first.")
            return
        try:
            result = _issue.create_offline_license(
                machine_id=self._create_mid.get().strip(),
                days=self._create_days.get(),
                label=self._create_label.get(),
            )
        except Exception as exc:
            messagebox.showerror("Error", str(exc))
            return

        self._create_output.delete("1.0", tk.END)
        self._create_output.insert(
            tk.END,
            f"Machine ID : {result['machine_id']}\n"
            f"Expires    : {result['expires']}\n"
            f"Label      : {result['label'] or '(none)'}\n"
            f"License ID : {result['license_id']}\n\n"
            f"{result['token']}",
        )

    def _copy_create_output(self) -> None:
        text = self._create_output.get("1.0", tk.END).strip()
        if "VCPM2." in text:
            key = text[text.index("VCPM2.") :].split()[0].strip()
        else:
            key = text
        if not key:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(key)
        messagebox.showinfo("Copied", "License key copied to clipboard.")

    def _run_verify(self) -> None:
        key = self._verify_key.get("1.0", tk.END).strip()
        mid = self._verify_mid.get().strip() or get_machine_id()
        status = verify_signed_license(key, machine_id=mid)
        self._verify_result.set(status.message)
        # tk doesn't easily recolor StringVar label; messagebox for clarity
        if status.ok:
            messagebox.showinfo("Valid", status.message)
        else:
            messagebox.showwarning("Invalid", status.message)

    def _test_activate(self) -> None:
        key = self._test_key.get("1.0", tk.END).strip()
        try:
            status = activate_license_key(key)
        except Exception as exc:
            status = type("S", (), {"ok": False, "message": str(exc)})()
        self._test_result.set(status.message)
        if status.ok:
            messagebox.showinfo("Activated", status.message)
        else:
            messagebox.showwarning("Failed", status.message)

    def _generate_keys(self) -> None:
        script = PROJECT_ROOT / "tools" / "generate_license_keys.py"
        try:
            subprocess.run([sys.executable, str(script)], check=True, cwd=str(PROJECT_ROOT))
            self._update_key_status()
            messagebox.showinfo("Done", "Signing keys created in tools/license_private.pem")
        except subprocess.CalledProcessError as exc:
            messagebox.showerror("Error", f"Key generation failed: {exc}")

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    LicenseAdminApp().run()


if __name__ == "__main__":
    main()
