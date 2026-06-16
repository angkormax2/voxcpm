# SINEKOOL AI

SINEKOOL AI is a Windows-first voice studio built on VoxCPM, with one-click setup, license-gated usage, and a local web UI.

This repository is the client-facing distribution for:
- Launcher app (NiceGUI native window)
- Automatic first-run setup (Python/Node/venv/dependencies/model)
- Local API + web UI at `http://localhost:3000/home`
- Offline/online license activation flow

## Quick Start (Clients)

1. Clone or download:
   ```bash
   git clone https://github.com/angkormax2/voxcpm.git
   cd voxcpm
   ```
2. Double-click `VoxCPM Studio.bat`
3. Wait for automatic setup to complete (first run only)
4. Copy Machine ID and activate license
5. Click `Start` to start servers (UI opens automatically when ready)

## What Setup Does Automatically

On first run, the launcher checks and installs what is missing:
- Supported Python runtime
- Node.js LTS
- `.venv` and Python dependencies
- Frontend dependencies (`starter-kit/node_modules`)
- Required model assets

No manual command-line setup is required for normal client usage.

## License Flow

- Setup/install can run without a license.
- Starting Studio/Open UI requires a valid license.
- Each license is machine-bound and has an expiry date.
- Clients can copy Machine ID from the launcher and send it to admin.

Contact: [Telegram @rornpisith](https://t.me/rornpisith)

## Main Scripts

- `VoxCPM Studio.bat` - Start launcher (recommended for clients)
- `run.bat` - Alias to launcher startup
- `stop.bat` - Stop local servers
- `VoxCPM Studio.vbs` - No-console launcher entry

## Project Structure

- `launcher.py` - Main SINEKOOL AI launcher UI (NiceGUI)
- `launcher_core.py` - Setup, dependency checks, server start/stop logic
- `license_manager.py` - License validation/activation
- `starter-kit/` - Web client application
- `assets/` - Branding, icon, and studio metadata

## Updating

- Launcher includes update checking for git-based installs.
- Current studio version is stored in `assets/studio_version.txt`.
- If updating from ZIP, replace project files and keep `data/license.json` if needed.

## Notes

- This repo includes SINEKOOL AI branding and launcher UX customizations.
- For additional operation details, see `STUDIO.md`.
