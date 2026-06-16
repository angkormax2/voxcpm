# VoxCPM2 Studio (Windows)

One-click local Studio: voice synthesis UI + API, with automatic setup on first run.

## Quick start (1 click)

1. **Get the app** — ZIP or git clone both work:
   ```bash
   git clone https://github.com/angkormax2/voxcpm.git
   cd voxcpm
   ```
   Or download ZIP from GitHub and extract it.

2. **Double-click** `VoxCPM Studio.bat`

3. **Wait** — setup runs automatically (Python 3.12, PyTorch, model, npm). No license needed for install.

4. **Enter a license** when prompted, then click **Start Studio**.

5. Browser opens at **http://localhost:3000/home**

6. To stop servers, run **`stop.bat`**.

Contact [t.me/rornpisith](https://t.me/rornpisith) with your **Machine ID** to get a license key.

## License (users)

- **Setup/install** does not require a license.
- **Open UI / Start Studio** requires a valid license.
- Each license works on **one computer** only and has an **expiry date**.
- **Online keys** can be revoked remotely.

## What setup does automatically

| Step | First run |
|------|-----------|
| Python 3.10–3.12 | Finds `py -3.12` or installs via winget |
| Node.js 18+ | winget if missing |
| `.venv`, PyTorch, VoxCPM package | Yes |
| VoxCPM2 weights | Yes (several GB) |
| `npm install` (starter-kit) | Yes |

Works from **git clone** or **Download ZIP** — no extra commands needed.

## What you install manually

- **NVIDIA GPU driver** — optional, for faster synthesis
- **Disk space** — ~10+ GB

## What is not in git

- `VoxCPM2/` — downloaded on setup
- `.venv/`, `starter-kit/node_modules/` — created on setup
- `data/license.json` — your activated license (local only)

## Troubleshooting

- **Setup failed** — open **Show setup log**, then click **Run setup** again.
- **Python 3.13 / 3.14** — setup auto-installs Python 3.12 on Windows; restart launcher if needed.
- **Ports in use** — run `stop.bat`, then start Studio again.
- **Online key fails** — check internet or contact the author.

## Files

| File | Purpose |
|------|---------|
| `VoxCPM Studio.bat` | Launch GUI (setup runs automatically) |
| `stop.bat` | Stop API and UI servers |
| `launcher.py` | Studio control panel |
| `license_manager.py` | License validation |
| `starter-kit/` | Next.js UI |
