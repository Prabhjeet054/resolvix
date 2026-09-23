# Resolvix Desktop (Electron)

Downloadable desktop shell for Resolvix. Electron starts the local Python FastAPI backend and loads the **same** shared UI from [`../frontend/`](../frontend/).

## Prerequisites

1. **Node.js 18+** and npm
2. **Python 3.11** project venv at the repo root (`.venv`) with dependencies:
   ```bash
   cd ..
   python3.11 -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Optional: Oracle 23ai + Ollama for full agent behavior (app falls back gracefully if offline)

## Run (development)

```bash
cd electron
npm install
npm start
```

Electron will:

1. Spawn `python -m uvicorn api.main:app --host 127.0.0.1 --port 8080` from the repo root
2. Wait until `GET /health` succeeds
3. Open the shared UI at `http://127.0.0.1:8080`

### Environment overrides

| Variable | Purpose |
|----------|---------|
| `RESOLVIX_ROOT` | Absolute path to the Resolvix repo (default: parent of `electron/`) |
| `RESOLVIX_PYTHON` | Python executable (default: `.venv/bin/python` or `.venv\Scripts\python.exe`) |
| `RESOLVIX_PORT` | Backend port (default: `8080`) |

## Web-only (same UI, no Electron)

```bash
cd ..
source .venv/bin/activate
uvicorn api.main:app --host 127.0.0.1 --port 8080
```

Open http://127.0.0.1:8080 — identical frontend.

## Build installers

```bash
npm run dist:mac     # .dmg / .zip
npm run dist:win     # NSIS / portable
npm run dist:linux   # AppImage / deb
```

Artifacts land in `electron/dist/`.

**Packaging note:** The installer ships the Electron shell. The Python API is started from the Resolvix checkout + `.venv` (set `RESOLVIX_ROOT` if needed). Embedding a full PyInstaller Python bundle inside the DMG/EXE is a follow-up hardening step. Oracle and Ollama remain external services.

## Layout

```
electron/
├── main.js                 # BrowserWindow + backend lifecycle
├── preload.js              # contextBridge (isDesktop flag)
├── package.json            # electron + electron-builder
├── scripts/start-backend.js
└── splash.html
```
