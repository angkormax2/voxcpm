# VoxCPM2 Studio (Windows)

One-click local Studio: voice synthesis UI + API, with automatic setup on first run.

## Quick start

1. **Clone the repo**
   ```bash
   git clone https://github.com/angkormax2/voxcpm.git
   cd voxcpm
   ```

2. **Double-click** `VoxCPM Studio.bat` (or `run.bat`)

3. **Enter a license** when prompted:
   - **Online key:** `VCPM-XXXX-XXXX` from the author (activates on first use, one PC)
   - **Offline key:** full `VCPM2....` key (bound to your Machine ID)
   - Send your **Machine ID** to [t.me/rornpisith](https://t.me/rornpisith) to get a key

4. **Wait for first-time setup** (internet required; no license needed for install):
   - Python and Node.js (via winget if missing)
   - Virtual environment, PyTorch, Python package
   - VoxCPM2 model weights (~several GB)
   - Frontend npm packages

5. Your browser opens at **http://localhost:3000/home**

6. To stop servers, run **`stop.bat`** (frees ports 8000 and 3000).

## License (users)

- **Setup/install** does not require a license.
- **Open UI / Start Studio** requires a valid license.
- Each license works on **one computer** only and has an **expiry date**.
- **Online keys** can be revoked remotely; the app re-checks with the server before synthesis.
- Contact the author on [Telegram](https://t.me/rornpisith) with your Machine ID to get a key.

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

## What is not in git

- `VoxCPM2/` — downloaded on setup
- `.venv/`, `starter-kit/node_modules/` — created on setup
- `data/voice_profiles/` — your saved voices (local only)
- `data/license.json` — activated license (local only)

## Troubleshooting

- **winget fails or asks for admin** — install [Python](https://www.python.org/downloads/) and [Node.js LTS](https://nodejs.org/) manually, then run `VoxCPM Studio.bat` again.
- **Ports in use** — run `stop.bat`, then start Studio again.
- **GPU shows CPU** — update NVIDIA drivers and run Setup again so CUDA PyTorch is installed.
- **Online key fails** — check internet and contact the author if the key was revoked or expired.

## Files

| File | Purpose |
|------|---------|
| `VoxCPM Studio.bat` | Launch GUI launcher (no CMD window) |
| `run.bat` | Same as Studio launcher |
| `stop.bat` | Stop API and UI servers |
| `license_manager.py` | License validation (offline + online) |
| `assets/license_server.url` | Online license server URL |
| `assets/license_public.pem` | Public key for license verification |
| `launcher.py` | Studio control panel |
| `launcher_core.py` | Setup, winget, model download, servers |
| `api.py` | FastAPI backend |
| `starter-kit/` | Next.js UI |
