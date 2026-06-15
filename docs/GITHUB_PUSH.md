# Push to GitHub — two repos

| Repo | URL | Visibility | Contents |
|------|-----|------------|----------|
| **API (license)** | https://github.com/angkormax2/api | **Private** | `license_server/` folder only |
| **Client (Studio)** | https://github.com/angkormax2/voxcpm | **Public** | Full VoxCPM Studio (no secrets) |

## Before you push — checklist

### Firebase
- [ ] Firebase project created
- [ ] Firestore enabled
- [ ] `firestore.rules` deployed (deny all client access)
- [ ] Service account JSON downloaded (keep local only)

### Keys
- [ ] Ran `python tools/generate_license_keys.py`
- [ ] `assets/license_public.pem` committed in **voxcpm** (public)
- [ ] `tools/license_private.pem` **never** committed (in `.gitignore`)
- [ ] Private key copied to API server / FastAPI Cloud env

### API deployed
- [ ] API running locally or on [FastAPI Cloud](https://fastapicloud.com/)
- [ ] `/health` returns OK
- [ ] Test issue key via License Admin → Online keys
- [ ] Production URL written to `assets/license_server.url`

### Secrets never in public repo
- [ ] No `license_private.pem`
- [ ] No Firebase JSON
- [ ] No `data/license_admin_config.json` (local admin secret)
- [ ] No `data/license.json` (customer licenses)

---

## Troubleshooting push / deploy

### `Permission denied to pamais` (403)
GitHub CLI is logged in as **pamais**, but repos are under **angkormax2**. Fix one of:

1. **Log in as angkormax2** (recommended):
   ```powershell
   gh auth login
   git config --global credential.helper manager
   ```
   Choose GitHub.com → HTTPS → login as **angkormax2**.

2. **Or** add `pamais` as collaborator on both repos (Settings → Collaborators).

### `angkormax2/api` not found
Create it while logged in as **angkormax2**:
- https://github.com/new → name `api` → **Private** → Create
- Then push from `license_server/` (commands in section A above).

### FastAPI Cloud not logged in
```powershell
cd license_server
$env:PYTHONUTF8=1
fastapi login
powershell -ExecutionPolicy Bypass -File deploy.ps1
```

---

## A. Push API (private) — `angkormax2/api`

The API is the `license_server/` folder as its **own git repo**.

```powershell
cd C:\Users\RornPisith\VoxCPM\license_server

git init
git add main.py signing.py firebase_store.py requirements.txt pyproject.toml README.md .env.example .gitignore firestore.rules
git commit -m "Initial VoxCPM2 license API (Firebase + FastAPI)"

git branch -M main
git remote add origin https://github.com/angkormax2/api.git
git push -u origin main
```

Create the repo on GitHub first: https://github.com/new → name `api` → **Private**.

After push, deploy to FastAPI Cloud and set env vars (see `license_server/README.md`).

---

## B. Push client (public) — `angkormax2/voxcpm`

From the main VoxCPM project (exclude API secrets and upstream OpenBMB remote if you want your own history).

```powershell
cd C:\Users\RornPisith\VoxCPM

# Optional: new remote for your public fork
git remote add voxcpm https://github.com/angkormax2/voxcpm.git

# Stage client files — do NOT add secrets
git add .
# Verify nothing secret is staged:
git status

git commit -m "VoxCPM2 Studio By BONG Pisith — launcher, license client, UI"
git push -u voxcpm main
```

Create the repo: https://github.com/new → name `voxcpm` → **Public**.

**Note:** Your current `origin` points to `OpenBMB/VoxCPM`. Use a separate remote (`voxcpm`) so you do not push Studio changes upstream by mistake.

### What stays in voxcpm (public)

- `license_manager.py`, `license_config.py`, `license_admin.py`
- `assets/license_public.pem`, `assets/license_server.url`
- `tools/generate_license_keys.py`, `tools/issue_license.py` (offline keys for author)
- Studio launcher, UI, `STUDIO.md`

### What is NOT in voxcpm

- `license_server/` — lives only in **angkormax2/api** (you can delete this folder from voxcpm after API is pushed, or keep a copy for local dev; do not duplicate secrets)

---

## C. After both are live

1. Deploy API → get URL
2. License Admin → Online keys → **Write URL to app**
3. Commit `assets/license_server.url` to **voxcpm**
4. Customer clones `angkormax2/voxcpm` → runs `VoxCPM Studio.bat` → enters `VCPM-....` key

## Author workflow

| Task | Tool |
|------|------|
| Offline key (no server) | License Admin → Create license |
| Online key (revocable) | License Admin → Online keys |
| Revoke online license | License Admin → Online keys → Revoke |

Contact: [t.me/rornpisith](https://t.me/rornpisith)
