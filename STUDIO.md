# VoxCPM2 Studio (Windows)

One-click local Studio: voice synthesis UI + API, with automatic setup on first run.

## Quick start (another PC)

1. **Clone the repo**
   ```bash
   git clone <your-repo-url>
   cd VoxCPM
   ```

2. **Double-click** `VoxCPM Studio.bat` (or `run.bat`)

3. **Enter a license** when you want to use the Studio UI:
   - **Online key:** `VCPM-XXXX-XXXX` from the author (activates on first use, one PC)
   - **Offline key:** full `VCPM2....` key (bound to your Machine ID)
   - Send your **Machine ID** to [t.me/rornpisith](https://t.me/rornpisith) to get a key

4. **Wait for first-time setup** (internet required, no license needed for install):
   - Python and Node.js (via winget if missing)
   - Virtual environment, PyTorch, Python package
   - VoxCPM2 model weights (~several GB)
   - Frontend npm packages

5. Your browser opens at **http://localhost:3000/home**

6. To stop servers, run **`stop.bat`** (frees ports 8000 and 3000).

## License (for users)

- **Setup/install** does not require a license.
- **Open UI / Start Studio** requires a valid license.
- Each license works on **one computer** only and has an **expiry date**.
- **Online keys** can be revoked remotely; the app re-checks with the server before synthesis.
- Contact the author on [Telegram](https://t.me/rornpisith) with your Machine ID to buy a key.

## License (for you — BONG Pisith)

### Offline keys (no server)

Use **License Admin.bat** → **Create license**, or:

```bash
python tools/issue_license.py --machine-id THEIR_MACHINE_ID --days 365 --label "Customer name"
```

### Online keys (Firebase + revocable)

1. Deploy the **private** license API: [github.com/angkormax2/api](https://github.com/angkormax2/api) — see `license_server/README.md` and [`docs/GITHUB_PUSH.md`](docs/GITHUB_PUSH.md)
2. Host on [FastAPI Cloud](https://fastapicloud.com/) (or your VPS)
3. **License Admin.bat** → **Online keys**:
   - Server URL + admin secret
   - **Write URL to app** → saves `assets/license_server.url` (ship with the app)
   - **Issue online key** → send short `VCPM-....` to customer

Keep `tools/license_private.pem` secret. Never commit it. The same key signs both offline and online tokens.

**Dev only:** set `VOXCPM_LICENSE_SKIP=1` to bypass checks while developing.

## Is it secure?

This protects honest users and casual sharing. It is **not unbreakable**:

- A technical user could edit the code or set `VOXCPM_LICENSE_SKIP=1`.
- Offline keys cannot be revoked without contacting you for a new key.
- **Online keys** add server-side revocation, one-PC binding, and re-validation before each synthesis job.

For stronger protection you would need compiled binaries or commercial DRM.

## What installs automatically

| Step | First run |
|------|-----------|
| Python 3.10+ | winget if missing |
| Node.js 18+ | winget if missing |
| `.venv`, PyTorch, `pip install -e .` | Yes |
| VoxCPM2 weights | Yes (during setup) |
| `npm install` (starter-kit) | Yes |
| Start API + UI | Yes |

## What you install manually

- **NVIDIA GPU driver** — optional, for faster synthesis on NVIDIA GPUs
- **Disk space** — plan for ~10+ GB (model + venv + node_modules)
- **Firebase + license server** — only if you use online keys (author)

## What is not in git

- `VoxCPM2/` — downloaded on setup
- `.venv/`, `starter-kit/node_modules/` — created on setup
- `data/voice_profiles/` — your saved voices (local only)
- `data/license.json` — activated license (local only)
- `data/license_admin_config.json` — your admin server URL/secret (local only)
- `tools/license_private.pem` — signing key (never commit)

## Troubleshooting

- **winget fails or asks for admin** — install [Python](https://www.python.org/downloads/) and [Node.js LTS](https://nodejs.org/) manually, then run `VoxCPM Studio.bat` again.
- **Ports in use** — run `stop.bat`, then start Studio again.
- **GPU shows CPU** — update NVIDIA drivers and run Setup again so CUDA PyTorch is installed.
- **Online key fails** — check internet; author must set `assets/license_server.url` to the deployed API URL.

## Files

| File | Purpose |
|------|---------|
| `VoxCPM Studio.bat` | Launch GUI launcher (no CMD window) |
| `License Admin.bat` | **You (author)** — offline + online license keys |
| `license_admin.py` | License admin GUI |
| `license_manager.py` | Client license validation (offline + online) |
| `docs/GITHUB_PUSH.md` | Push API (private) + client (public) to GitHub |
| `assets/license_server.url` | Online license server URL baked into the app |
| `launcher.py` | Studio control panel |
| `launcher_core.py` | Setup, winget, model download, servers |
| `api.py` | FastAPI backend |
| `starter-kit/` | Next.js UI |
