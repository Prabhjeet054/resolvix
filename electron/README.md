# Resolvix Desktop (Electron)

Downloadable desktop shell for Resolvix. Electron starts the local Python FastAPI backend and loads the **same** shared UI from [`../frontend/`](../frontend/) — including light/dark theme, resolution confidence, HITL auto-escalate, Emerging Incidents, thumbs feedback, hybrid vector+keyword search, multi-turn Refine & Clarify, **PII redaction** before embed/LLM/storage, and **groundedness self-check** (second LLM pass: every step must cite a retrieved ticket, else escalate). There is no separate Electron UI to keep in sync.

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
| `RESOLVIX_VIEW` | Optional startup view: `incidents` opens Emerging Incidents (`#incidents`) |

## Web-only (same UI, no Electron)

```bash
cd ..
source .venv/bin/activate
uvicorn api.main:app --host 127.0.0.1 --port 8080
```

Open http://127.0.0.1:8080 — identical frontend to the desktop window (confidence panel, theme toggle, escalation, **Emerging Incidents**, thumbs feedback, **hybrid vector+keyword** match badges).

Electron clears its HTTP cache on each launch so `frontend/` changes (CSS/JS) appear without rebuilding the shell. Votes persist in `data/feedback_store.json` under the Resolvix project root (same store for browser, Electron, and Streamlit). Hybrid retrieval runs in the Python API the Electron shell starts — no separate desktop search path.

## Build installers

Unsigned local builds (recommended for development):

```bash
npm run pack        # → dist/mac-arm64/Resolvix.app
npm run dist:mac    # → dist/Resolvix-*.dmg and/or .zip
```

Artifacts:
- `dist/mac-arm64/Resolvix.app` — run directly
- `dist/Resolvix-0.1.0-arm64-mac.zip` — distributable zip
- `dist/Resolvix-0.1.0-arm64.dmg` — macOS disk image (when `hdiutil` succeeds)

Code signing is disabled by default (`mac.identity: null`) so local builds do not require an Apple Developer certificate. For App Store / notarized releases, set a signing identity and remove `-c.mac.identity=null`.

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
