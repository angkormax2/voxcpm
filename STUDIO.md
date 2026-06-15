# VoxCPM2 Studio (Windows)

One-click local Studio: voice synthesis UI + API, with automatic setup on first run.

## Quick start (another PC)

1. **Clone the repo**
   ```bash
   git clone <your-repo-url>
   cd VoxCPM
   ```

2. **Double-click** `VoxCPM Studio.bat` (or `run.bat`)

3. **Wait for first-time setup** (internet required):
   - Python and Node.js (via winget if missing)
   - Virtual environment, PyTorch, Python package
   - VoxCPM2 model weights (~several GB)
   - Frontend npm packages

4. Your browser opens at **http://localhost:3000/home**

5. To stop servers, run **`stop.bat`** (frees ports 8000 and 3000).

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

## Troubleshooting

- **winget fails or asks for admin** — install [Python](https://www.python.org/downloads/) and [Node.js LTS](https://nodejs.org/) manually, then run `VoxCPM Studio.bat` again.
- **Ports in use** — run `stop.bat`, then start Studio again.
- **GPU shows CPU** — update NVIDIA drivers and run Setup again so CUDA PyTorch is installed.

## Files

| File | Purpose |
|------|---------|
| `VoxCPM Studio.bat` | Launch GUI launcher (no CMD window) |
| `launcher.py` | Studio control panel |
| `launcher_core.py` | Setup, winget, model download, servers |
| `api.py` | FastAPI backend |
| `starter-kit/` | Next.js UI |
