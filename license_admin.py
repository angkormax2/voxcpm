"""VoxCPM2 Studio — License Admin GUI (offline + online keys)."""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import tkinter as tk
from datetime import datetime, timezone
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
from launcher_core import _subprocess_hide_kwargs, center_tk_window  # noqa: E402
from license_manager import (  # noqa: E402
    activate_license_key,
    format_remaining,
    get_machine_id,
    verify_signed_license,
)
from studio_branding import (  # noqa: E402
    DEFAULT_STUDIO_REPO_URL,
    LICENSE_CONTACT_URL,
    STUDIO_REPO_URL_FILE,
    get_studio_repo_url,
)

ASSETS = PROJECT_ROOT / "assets"
ICON_ICO = ASSETS / "studio_launcher.ico"
ADMIN_CONFIG = PROJECT_ROOT / "data" / "license_admin_config.json"
ISSUED_LOG = PROJECT_ROOT / "data" / "license_issued_log.json"
SERVER_URL_FILE = ASSETS / "license_server.url"

BG = "#0f1117"
PANEL = "#1a1d2e"
TEXT = "#e6edf3"
MUTED = "#8b949e"
OK = "#3fb950"
WARN = "#d29922"
ERR = "#f85149"
ENTRY_BG = "#0d1117"


class LicenseAdminApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("VoxCPM2 License Admin")
        self.root.geometry("900x760")
        self.root.minsize(760, 620)
        self.root.configure(bg=BG)
        self._last_key = ""
        self._last_license_id = ""
        self._last_expires = ""
        self._last_label = ""
        self._last_type = ""
        self._manage_row_data: dict[str, dict] = {}
        self._set_icon()
        self._apply_styles()

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
            text="Issue, manage, copy, and revoke customer licenses",
            font=("Segoe UI", 10),
            fg=MUTED,
            bg=BG,
        ).pack(anchor="w")

        self._key_status = tk.StringVar()
        self._update_key_status()
        status_row = tk.Frame(self.root, bg=BG)
        status_row.pack(fill="x", padx=16, pady=(0, 6))
        tk.Label(
            status_row,
            textvariable=self._key_status,
            font=("Segoe UI", 9),
            fg=MUTED,
            bg=BG,
        ).pack(side="left")
        if not _issue.private_key_ready():
            ttk.Button(status_row, text="Generate signing keys", command=self._generate_keys).pack(
                side="right"
            )

        self._build_last_key_bar()

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=16, pady=8)

        self._tab_manage(notebook)
        self._tab_create(notebook)
        self._tab_online(notebook)
        self._tab_verify(notebook)
        self._tab_test_activate(notebook)

        foot = tk.Label(
            self.root,
            text="Keep tools/license_private.pem secret · never commit it",
            font=("Segoe UI", 8),
            fg=MUTED,
            bg=BG,
        )
        foot.pack(anchor="w", padx=16, pady=(0, 10))

        self._refresh_manage_table()
        center_tk_window(self.root, width=900, height=760)

    def _apply_styles(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(
            "Treeview",
            background=ENTRY_BG,
            foreground=TEXT,
            fieldbackground=ENTRY_BG,
            rowheight=26,
            borderwidth=0,
        )
        style.configure(
            "Treeview.Heading",
            background=PANEL,
            foreground=TEXT,
            relief="flat",
        )
        style.map("Treeview", background=[("selected", "#2d333b")])

    def _set_icon(self) -> None:
        try:
            if sys.platform == "win32" and ICON_ICO.is_file():
                self.root.iconbitmap(default=str(ICON_ICO))
        except Exception:
            pass

    def _entry(self, parent: tk.Widget, **kwargs) -> tk.Entry:
        defaults = dict(font=("Consolas", 10), bg=ENTRY_BG, fg=TEXT, relief="flat")
        defaults.update(kwargs)
        return tk.Entry(parent, **defaults)

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

    def _copy_clipboard(self, text: str, *, title: str = "Copied") -> None:
        text = text.strip()
        if not text:
            messagebox.showwarning("Nothing to copy", "No text available.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        messagebox.showinfo(title, "Copied to clipboard.")

    def _customer_message(self, key: str, expires: str, label: str, lic_type: str) -> str:
        name = label.strip() or "Customer"
        repo = ""
        if hasattr(self, "_studio_repo"):
            repo = self._studio_repo.get().strip().rstrip("/")
        if not repo:
            repo = get_studio_repo_url()
        lines = [
            f"Hi {name},",
            "",
            f"Your VoxCPM2 Studio license ({lic_type}):",
            "",
            f"Key: {key}",
            f"Valid until: {expires}",
            "",
        ]
        if repo:
            clone_url = repo if repo.endswith(".git") else f"{repo}.git"
            lines.extend(
                [
                    "How to install:",
                    f"1. Clone: git clone {clone_url}",
                    "2. Open the folder and double-click VoxCPM Studio.bat",
                    "3. Click Enter license and paste the key above",
                    "",
                    f"Or open in browser: {repo}",
                ]
            )
        else:
            lines.extend(
                [
                    "1. Download / open VoxCPM2 Studio",
                    "2. Click Enter license",
                    "3. Paste the key above",
                ]
            )
        lines.extend(["", f"Support: {LICENSE_CONTACT_URL.replace('https://', '')}"])
        return "\n".join(lines)

    def _set_last_issued(
        self,
        *,
        key: str,
        license_id: str,
        expires: str,
        label: str,
        lic_type: str,
        machine_id: str = "",
    ) -> None:
        self._last_key = key
        self._last_license_id = license_id
        self._last_expires = expires
        self._last_label = label
        self._last_type = lic_type
        self._last_key_var.set(key)
        remaining, _, _ = format_remaining(expires)
        self._last_meta_var.set(f"{lic_type} · expires {expires} · {remaining}")

        entry = {
            "type": lic_type,
            "key": key,
            "license_id": license_id,
            "expires": expires,
            "label": label,
            "machine_id": machine_id,
            "issued_at": datetime.now(timezone.utc).isoformat(),
        }
        log = self._load_issued_log()
        log.insert(0, entry)
        self._save_issued_log(log[:200])
        self._refresh_manage_table()

    def _load_issued_log(self) -> list[dict]:
        if not ISSUED_LOG.is_file():
            return []
        try:
            data = json.loads(ISSUED_LOG.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save_issued_log(self, rows: list[dict]) -> None:
        ISSUED_LOG.parent.mkdir(parents=True, exist_ok=True)
        ISSUED_LOG.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    def _build_last_key_bar(self) -> None:
        bar = tk.LabelFrame(
            self.root,
            text=" Last issued key ",
            font=("Segoe UI", 9, "bold"),
            fg=TEXT,
            bg=PANEL,
            labelanchor="n",
        )
        bar.pack(fill="x", padx=16, pady=(0, 4))

        inner = tk.Frame(bar, bg=PANEL)
        inner.pack(fill="x", padx=10, pady=8)

        self._last_key_var = tk.StringVar(value="(issue a license to see it here)")
        self._entry(inner, textvariable=self._last_key_var, state="readonly", readonlybackground=ENTRY_BG).pack(
            fill="x", ipady=5
        )
        self._last_meta_var = tk.StringVar(value="")
        tk.Label(inner, textvariable=self._last_meta_var, fg=MUTED, bg=PANEL, font=("Segoe UI", 8)).pack(
            anchor="w", pady=(4, 6)
        )

        row = tk.Frame(inner, bg=PANEL)
        row.pack(fill="x")
        ttk.Button(row, text="Copy key", command=self._copy_last_key).pack(side="left")
        ttk.Button(row, text="Copy customer message", command=self._copy_last_message).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(row, text="Copy license ID", command=self._copy_last_id).pack(side="left", padx=(8, 0))

    def _copy_last_key(self) -> None:
        self._copy_clipboard(self._last_key, title="Key copied")

    def _copy_last_id(self) -> None:
        self._copy_clipboard(self._last_license_id, title="License ID copied")

    def _copy_last_message(self) -> None:
        if not self._last_key:
            messagebox.showwarning("No key", "Issue a license first.")
            return
        self._copy_clipboard(
            self._customer_message(
                self._last_key, self._last_expires, self._last_label, self._last_type
            ),
            title="Customer message copied",
        )

    def _update_key_status(self) -> None:
        if _issue.private_key_ready():
            self._key_status.set("Signing keys: ready")
        else:
            self._key_status.set("Signing keys: missing")

    def _load_admin_config(self) -> dict:
        if ADMIN_CONFIG.is_file():
            try:
                return json.loads(ADMIN_CONFIG.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"server_url": get_license_server_url(), "admin_secret": ""}

    def _save_admin_config(self, server_url: str, admin_secret: str) -> None:
        ADMIN_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        ADMIN_CONFIG.write_text(
            json.dumps(
                {"server_url": server_url.strip().rstrip("/"), "admin_secret": admin_secret},
                indent=2,
            ),
            encoding="utf-8",
        )

    def _admin_request(self, method: str, path: str, payload: dict | None = None) -> dict:
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
        req = urllib.request.Request(f"{server}{path}", data=data, headers=headers, method=method)
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

    def _admin_delete_license(self, license_id: str) -> tuple[bool, str]:
        lid = urllib.parse.quote(license_id.strip(), safe="")
        last_err = ""
        for method in ("DELETE", "POST"):
            try:
                self._admin_request(method, f"/admin/delete/{lid}")
                return True, ""
            except RuntimeError as exc:
                last_err = str(exc)
                if last_err == "Not Found" and method == "DELETE":
                    continue
        if last_err == "Not Found":
            last_err = (
                "Delete API not deployed yet (update license_server and run fastapi deploy)."
            )
        return False, last_err

    def _remove_from_issued_log(self, *, license_id: str = "", key: str = "") -> None:
        log = self._load_issued_log()
        kept: list[dict] = []
        for entry in log:
            if license_id and entry.get("license_id") == license_id:
                continue
            if not license_id and key and entry.get("key") == key:
                continue
            kept.append(entry)
        self._save_issued_log(kept)
        self._refresh_manage_table()

    def _tab_manage(self, notebook: ttk.Notebook) -> None:
        tab = tk.Frame(notebook, bg=BG)
        notebook.add(tab, text="  Manage  ")
        inner = self._panel(tab, "Issued licenses")

        toolbar = tk.Frame(inner, bg=PANEL)
        toolbar.pack(fill="x", pady=(0, 8))
        ttk.Button(toolbar, text="Refresh from server", command=self._sync_server_licenses).pack(side="left")
        ttk.Button(toolbar, text="Copy key", command=self._copy_selected_key).pack(side="left", padx=(8, 0))
        ttk.Button(toolbar, text="Copy message", command=self._copy_selected_message).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(toolbar, text="Copy license ID", command=self._copy_selected_id).pack(side="left", padx=(8, 0))
        ttk.Button(toolbar, text="Revoke online", command=self._revoke_selected).pack(side="left", padx=(8, 0))
        ttk.Button(toolbar, text="Delete", command=self._delete_selected).pack(side="left", padx=(8, 0))

        cols = ("type", "key", "label", "expires", "machine", "status", "license_id")
        self._manage_tree = ttk.Treeview(inner, columns=cols, show="headings", height=14)
        headings = {
            "type": "Type",
            "key": "Key",
            "label": "Customer",
            "expires": "Expires",
            "machine": "PC / Machine",
            "status": "Status",
            "license_id": "License ID",
        }
        widths = {"type": 70, "key": 180, "label": 120, "expires": 95, "machine": 120, "status": 90, "license_id": 220}
        for col in cols:
            self._manage_tree.heading(col, text=headings[col])
            self._manage_tree.column(col, width=widths[col], anchor="w")
        self._manage_tree.pack(fill="both", expand=True)
        self._manage_tree.bind("<Double-1>", lambda _e: self._copy_selected_key())

        scroll = ttk.Scrollbar(inner, orient="vertical", command=self._manage_tree.yview)
        self._manage_tree.configure(yscrollcommand=scroll.set)

        tk.Label(
            inner,
            text="Select a row, then copy or revoke/delete. Double-click copies the full key when available.",
            fg=MUTED,
            bg=PANEL,
            font=("Segoe UI", 8),
        ).pack(anchor="w", pady=(8, 0))

    def _key_stored(self, key: str) -> bool:
        key = (key or "").strip()
        return bool(key) and not key.startswith("(")

    def _refresh_manage_table(self) -> None:
        if not hasattr(self, "_manage_tree"):
            return
        for item in self._manage_tree.get_children():
            self._manage_tree.delete(item)
        self._manage_row_data.clear()

        for row in self._load_issued_log():
            key = row.get("key", "")
            short_key = key if len(key) <= 28 else key[:25] + "..."
            if not self._key_stored(key):
                short_key = key or "—"
            status = row.get("status", "issued")
            if row.get("revoked"):
                status = "revoked"
            label = row.get("label", "") or "—"
            iid = self._manage_tree.insert(
                "",
                tk.END,
                values=(
                    row.get("type", ""),
                    short_key,
                    label,
                    row.get("expires", ""),
                    row.get("machine_id", "") or row.get("machine", "not activated"),
                    status,
                    row.get("license_id", ""),
                ),
            )
            self._manage_row_data[iid] = dict(row)

    def _selected_row(self) -> dict | None:
        sel = self._manage_tree.selection()
        if not sel:
            messagebox.showinfo("Select a row", "Click a license in the table first.")
            return None
        row = self._manage_row_data.get(sel[0])
        if row:
            return row
        values = self._manage_tree.item(sel[0], "values")
        return {
            "type": values[0] if values else "",
            "key": values[1] if len(values) > 1 else "",
            "label": "" if len(values) <= 2 or values[2] == "—" else values[2],
            "expires": values[3] if len(values) > 3 else "",
            "machine_id": values[4] if len(values) > 4 else "",
            "status": values[5] if len(values) > 5 else "",
            "license_id": values[6] if len(values) > 6 else "",
        }

    def _copy_selected_key(self) -> None:
        row = self._selected_row()
        if not row:
            return
        key = row.get("key", "")
        if not self._key_stored(key):
            messagebox.showwarning(
                "Key not available",
                "The full key was not saved locally (e.g. synced from server before logging).\n"
                "You can still copy the license ID or revoke/delete on the server.",
            )
            return
        self._copy_clipboard(key, title="Key copied")

    def _copy_selected_id(self) -> None:
        row = self._selected_row()
        if not row:
            return
        lid = row.get("license_id", "")
        if not lid:
            messagebox.showwarning("No ID", "This row has no license ID (offline keys use the key itself).")
            return
        self._copy_clipboard(lid, title="License ID copied")

    def _copy_selected_message(self) -> None:
        row = self._selected_row()
        if not row:
            return
        if not self._key_stored(row.get("key", "")):
            messagebox.showwarning(
                "Key not available",
                "Cannot build the customer message without the full key.",
            )
            return
        self._copy_clipboard(
            self._customer_message(row["key"], row["expires"], row.get("label", ""), row["type"]),
            title="Customer message copied",
        )

    def _revoke_selected(self) -> None:
        row = self._selected_row()
        if not row:
            return
        if row["type"] != "online":
            messagebox.showwarning("Offline key", "Only online licenses can be revoked on the server.")
            return
        lid = row["license_id"]
        if not lid:
            messagebox.showerror("Error", "No license ID on this row.")
            return
        if row.get("revoked") or row.get("status") == "revoked":
            messagebox.showinfo("Already revoked", "This license is already revoked.")
            return
        key_hint = row.get("key", "")
        if self._key_stored(key_hint):
            prompt = f"Revoke this online license?\n\nKey: {key_hint}\nID: {lid}"
        else:
            prompt = f"Revoke this online license?\n\nID: {lid}"
        if not messagebox.askyesno("Revoke", prompt):
            return
        try:
            self._admin_request("POST", f"/admin/revoke/{lid}")
        except Exception as exc:
            messagebox.showerror("Error", str(exc))
            return
        log = self._load_issued_log()
        for entry in log:
            if entry.get("license_id") == lid:
                entry["revoked"] = True
                entry["status"] = "revoked"
        self._save_issued_log(log)
        self._refresh_manage_table()
        messagebox.showinfo("Revoked", "License revoked on server.")

    def _delete_selected(self) -> None:
        row = self._selected_row()
        if not row:
            return
        lic_type = row.get("type", "")
        lid = row.get("license_id", "")
        key = row.get("key", "")

        if lic_type == "online" and lid:
            prompt = (
                f"Delete this online license from the server and remove it from this list?\n\n"
                f"License ID: {lid}"
            )
            if not messagebox.askyesno("Delete license", prompt):
                return
            ok, err = self._admin_delete_license(lid)
            if not ok:
                remove_local = messagebox.askyesno(
                    "Server delete failed",
                    f"{err}\n\nRemove this row from your local list anyway?",
                )
                if not remove_local:
                    return
        else:
            shown = key if self._key_stored(key) else "(local entry)"
            if not messagebox.askyesno("Remove from list", f"Remove this entry from the local list?\n\n{shown}"):
                return

        self._remove_from_issued_log(license_id=lid, key=key)
        messagebox.showinfo("Deleted", "Removed from the list.")

    def _sync_server_licenses(self) -> None:
        try:
            result = self._admin_request("GET", "/admin/list?limit=50")
        except Exception as exc:
            messagebox.showerror("Error", str(exc))
            return
        log = self._load_issued_log()
        by_id = {e.get("license_id"): e for e in log if e.get("license_id")}
        for row in result.get("licenses", []):
            lid = row.get("license_id", "")
            if not lid:
                continue
            existing = by_id.get(lid)
            if existing:
                existing["expires"] = row.get("expires", existing.get("expires", ""))
                existing["machine_id"] = row.get("machine_id", existing.get("machine_id", ""))
                if row.get("revoked"):
                    existing["revoked"] = True
                    existing["status"] = "revoked"
                elif existing.get("machine_id") not in ("", "not activated"):
                    existing["status"] = "activated"
            else:
                log.insert(
                    0,
                    {
                        "type": "online",
                        "key": "(issued before log)",
                        "license_id": lid,
                        "expires": row.get("expires", ""),
                        "label": row.get("label", ""),
                        "machine_id": row.get("machine_id", ""),
                        "revoked": bool(row.get("revoked")),
                        "status": "revoked" if row.get("revoked") else "on server",
                        "issued_at": "",
                    },
                )
        self._save_issued_log(log[:200])
        self._refresh_manage_table()
        messagebox.showinfo("Refreshed", f"Synced {len(result.get('licenses', []))} licenses from server.")

    def _tab_online(self, notebook: ttk.Notebook) -> None:
        tab = tk.Frame(notebook, bg=BG)
        notebook.add(tab, text="  Online keys  ")
        inner = self._panel(tab, "Issue revocable VCPM-.... keys")

        cfg = self._load_admin_config()
        self._online_server = tk.StringVar(value=cfg.get("server_url", ""))
        self._online_secret = tk.StringVar(value=cfg.get("admin_secret", ""))

        settings = tk.LabelFrame(inner, text=" Server settings ", fg=MUTED, bg=PANEL, font=("Segoe UI", 9))
        settings.pack(fill="x", pady=(0, 10))
        sinner = tk.Frame(settings, bg=PANEL)
        sinner.pack(fill="x", padx=8, pady=8)

        tk.Label(sinner, text="Server URL:", fg=MUTED, bg=PANEL, font=("Segoe UI", 9)).grid(
            row=0, column=0, sticky="w"
        )
        self._entry(sinner, textvariable=self._online_server, font=("Consolas", 9)).grid(
            row=0, column=1, sticky="ew", padx=(8, 0), pady=2
        )
        tk.Label(sinner, text="Admin secret:", fg=MUTED, bg=PANEL, font=("Segoe UI", 9)).grid(
            row=1, column=0, sticky="w", pady=(6, 0)
        )
        self._entry(sinner, textvariable=self._online_secret, show="*", font=("Consolas", 9)).grid(
            row=1, column=1, sticky="ew", padx=(8, 0), pady=(6, 0)
        )
        tk.Label(sinner, text="Studio repo (clone):", fg=MUTED, bg=PANEL, font=("Segoe UI", 9)).grid(
            row=2, column=0, sticky="w", pady=(6, 0)
        )
        self._studio_repo = tk.StringVar(value=get_studio_repo_url() or DEFAULT_STUDIO_REPO_URL)
        self._entry(sinner, textvariable=self._studio_repo, font=("Consolas", 9)).grid(
            row=2, column=1, sticky="ew", padx=(8, 0), pady=(6, 0)
        )
        sinner.columnconfigure(1, weight=1)

        sbtn = tk.Frame(sinner, bg=PANEL)
        sbtn.grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Button(sbtn, text="Save settings", command=self._save_online_settings).pack(side="left")
        ttk.Button(sbtn, text="Write URL to app", command=self._write_server_url_file).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(sbtn, text="Write repo URL", command=self._write_studio_repo_url_file).pack(
            side="left", padx=(8, 0)
        )

        row2 = tk.Frame(inner, bg=PANEL)
        row2.pack(fill="x", pady=(0, 8))
        tk.Label(row2, text="Valid days:", fg=MUTED, bg=PANEL, font=("Segoe UI", 9)).pack(side="left")
        self._online_days = tk.IntVar(value=365)
        tk.Spinbox(row2, from_=1, to=3650, textvariable=self._online_days, width=8).pack(side="left", padx=(8, 16))
        tk.Label(row2, text="Customer:", fg=MUTED, bg=PANEL, font=("Segoe UI", 9)).pack(side="left")
        self._online_label = tk.StringVar()
        self._entry(row2, textvariable=self._online_label, width=28, font=("Segoe UI", 10)).pack(
            side="left", padx=(8, 0), ipady=3
        )

        ttk.Button(inner, text="Issue online key", command=self._issue_online_key).pack(anchor="w", pady=(0, 8))

        self._online_result = tk.StringVar(value="")
        tk.Label(inner, textvariable=self._online_result, fg=OK, bg=PANEL, font=("Segoe UI", 10), wraplength=700).pack(
            anchor="w", pady=(0, 6)
        )

    def _save_online_settings(self) -> None:
        self._save_admin_config(self._online_server.get(), self._online_secret.get())
        messagebox.showinfo("Saved", "Server settings saved.")

    def _write_server_url_file(self) -> None:
        url = self._online_server.get().strip().rstrip("/")
        if not url:
            messagebox.showerror("Error", "Enter a server URL first.")
            return
        SERVER_URL_FILE.write_text(f"{url}\n", encoding="utf-8")
        messagebox.showinfo("Saved", f"Wrote {SERVER_URL_FILE.name}")

    def _write_studio_repo_url_file(self) -> None:
        url = self._studio_repo.get().strip().rstrip("/")
        if not url:
            messagebox.showerror("Error", "Enter a studio repo URL first.")
            return
        STUDIO_REPO_URL_FILE.parent.mkdir(parents=True, exist_ok=True)
        STUDIO_REPO_URL_FILE.write_text(f"{url}\n", encoding="utf-8")
        messagebox.showinfo("Saved", f"Wrote {STUDIO_REPO_URL_FILE.name}")

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
        key = result.get("key", "")
        expires = result.get("expires", "")
        lid = result.get("license_id", "")
        label = result.get("label") or self._online_label.get()
        self._online_result.set(f"Issued {key} — valid until {expires}")
        self._set_last_issued(
            key=key, license_id=lid, expires=expires, label=label, lic_type="online"
        )
        self._copy_last_message()

    def _tab_create(self, notebook: ttk.Notebook) -> None:
        tab = tk.Frame(notebook, bg=BG)
        notebook.add(tab, text="  Offline key  ")
        inner = self._panel(tab, "Signed VCPM2.... key (one PC, no server)")

        tk.Label(inner, text="Customer Machine ID:", fg=MUTED, bg=PANEL, font=("Segoe UI", 9)).pack(anchor="w")
        mid_row = tk.Frame(inner, bg=PANEL)
        mid_row.pack(fill="x", pady=(4, 10))
        self._create_mid = tk.StringVar()
        self._entry(mid_row, textvariable=self._create_mid).pack(side="left", fill="x", expand=True, ipady=5)
        ttk.Button(mid_row, text="This PC", command=lambda: self._create_mid.set(get_machine_id())).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(mid_row, text="Copy", command=lambda: self._copy_clipboard(self._create_mid.get())).pack(
            side="left", padx=(8, 0)
        )

        row2 = tk.Frame(inner, bg=PANEL)
        row2.pack(fill="x", pady=(0, 10))
        tk.Label(row2, text="Valid days:", fg=MUTED, bg=PANEL, font=("Segoe UI", 9)).pack(side="left")
        self._create_days = tk.IntVar(value=365)
        tk.Spinbox(row2, from_=1, to=3650, textvariable=self._create_days, width=8).pack(side="left", padx=(8, 16))
        tk.Label(row2, text="Customer:", fg=MUTED, bg=PANEL, font=("Segoe UI", 9)).pack(side="left")
        self._create_label = tk.StringVar()
        self._entry(row2, textvariable=self._create_label, width=28, font=("Segoe UI", 10)).pack(
            side="left", padx=(8, 0), ipady=3
        )

        ttk.Button(inner, text="Generate offline key", command=self._generate_offline).pack(anchor="w", pady=(0, 8))

        self._offline_key_var = tk.StringVar(value="")
        self._entry(inner, textvariable=self._offline_key_var, state="readonly", readonlybackground=ENTRY_BG).pack(
            fill="x", ipady=6
        )

        btn_row = tk.Frame(inner, bg=PANEL)
        btn_row.pack(fill="x", pady=(8, 0))
        ttk.Button(btn_row, text="Copy key", command=lambda: self._copy_clipboard(self._offline_key_var.get())).pack(
            side="left"
        )
        ttk.Button(btn_row, text="Copy customer message", command=self._copy_offline_message).pack(
            side="left", padx=(8, 0)
        )

    def _copy_offline_message(self) -> None:
        key = self._offline_key_var.get().strip()
        if not key:
            messagebox.showwarning("No key", "Generate a key first.")
            return
        self._copy_clipboard(
            self._customer_message(key, self._last_expires, self._last_label, "offline"),
            title="Customer message copied",
        )

    def _tab_verify(self, notebook: ttk.Notebook) -> None:
        tab = tk.Frame(notebook, bg=BG)
        notebook.add(tab, text="  Verify  ")
        inner = self._panel(tab, "Check a license key")

        self._verify_key = scrolledtext.ScrolledText(
            inner, height=5, font=("Consolas", 9), bg=ENTRY_BG, fg=TEXT, relief="flat"
        )
        self._verify_key.pack(fill="x", pady=(4, 8))

        tk.Label(inner, text="Machine ID (optional):", fg=MUTED, bg=PANEL, font=("Segoe UI", 9)).pack(anchor="w")
        self._verify_mid = tk.StringVar(value=get_machine_id())
        self._entry(inner, textvariable=self._verify_mid).pack(fill="x", pady=(4, 8), ipady=4)

        ttk.Button(inner, text="Verify license", command=self._run_verify).pack(anchor="w", pady=(0, 8))
        self._verify_result = tk.StringVar()
        tk.Label(
            inner, textvariable=self._verify_result, fg=TEXT, bg=PANEL, font=("Segoe UI", 10), wraplength=640
        ).pack(anchor="w")

    def _tab_test_activate(self, notebook: ttk.Notebook) -> None:
        tab = tk.Frame(notebook, bg=BG)
        notebook.add(tab, text="  Test  ")
        inner = self._panel(tab, "Activate on this PC")

        tk.Label(
            inner,
            text=f"Machine ID: {get_machine_id()}",
            font=("Consolas", 10),
            fg=TEXT,
            bg=PANEL,
        ).pack(anchor="w", pady=(0, 8))

        self._test_key = scrolledtext.ScrolledText(
            inner, height=5, font=("Consolas", 9), bg=ENTRY_BG, fg=TEXT, relief="flat"
        )
        self._test_key.pack(fill="x", pady=(4, 8))
        ttk.Button(inner, text="Activate on this PC", command=self._test_activate).pack(anchor="w", pady=(0, 8))
        self._test_result = tk.StringVar()
        tk.Label(
            inner, textvariable=self._test_result, fg=TEXT, bg=PANEL, font=("Segoe UI", 10), wraplength=640
        ).pack(anchor="w")

    def _generate_offline(self) -> None:
        if not _issue.private_key_ready():
            messagebox.showerror("Missing keys", "Generate signing keys first.")
            return
        mid = self._create_mid.get().strip()
        if len(mid) < 8:
            messagebox.showerror("Error", "Enter the customer Machine ID.")
            return
        try:
            result = _issue.create_offline_license(
                machine_id=mid,
                days=self._create_days.get(),
                label=self._create_label.get(),
            )
        except Exception as exc:
            messagebox.showerror("Error", str(exc))
            return

        token = result["token"]
        self._offline_key_var.set(token)
        self._set_last_issued(
            key=token,
            license_id=result["license_id"],
            expires=result["expires"],
            label=result["label"],
            lic_type="offline",
            machine_id=result["machine_id"],
        )
        messagebox.showinfo(
            "License created",
            f"Offline key generated.\nValid until {result['expires']}.\n\nCustomer message copied to clipboard.",
        )
        self._copy_last_message()

    def _run_verify(self) -> None:
        key = self._verify_key.get("1.0", tk.END).strip()
        mid = self._verify_mid.get().strip() or get_machine_id()
        status = verify_signed_license(key, machine_id=mid)
        self._verify_result.set(status.message)
        if status.ok:
            remaining = status.remaining_label or ""
            messagebox.showinfo("Valid", f"{status.message}\n{remaining}")
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
            subprocess.run(
                [sys.executable, str(script)],
                check=True,
                cwd=str(PROJECT_ROOT),
                **_subprocess_hide_kwargs(),
            )
            self._update_key_status()
            messagebox.showinfo("Done", "Signing keys created.")
        except subprocess.CalledProcessError as exc:
            messagebox.showerror("Error", f"Key generation failed: {exc}")

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    LicenseAdminApp().run()


if __name__ == "__main__":
    main()
