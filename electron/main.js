/**
 * Resolvix Electron main process.
 * Spawns the Python FastAPI backend, waits for /health, then loads the shared UI.
 */
const { app, BrowserWindow, shell } = require("electron");
const path = require("path");
const { startBackend, stopBackend, DEFAULT_PORT } = require("./scripts/start-backend");

let mainWindow = null;
let backend = null;

function createSplash(message) {
  const win = new BrowserWindow({
    width: 520,
    height: 280,
    resizable: false,
    frame: true,
    show: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  const html = encodeURIComponent(`<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Resolvix</title>
<style>
  body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;margin:0;
  display:flex;align-items:center;justify-content:center;height:100vh;
  background:linear-gradient(160deg,#0f1720,#1a2a38);color:#e8eef5}
  .box{text-align:center;padding:2rem;max-width:420px}
  h1{margin:0 0 .5rem;font-size:1.4rem}
  p{opacity:.85;line-height:1.45}
</style></head>
<body><div class="box"><h1>Resolvix</h1><p>${message}</p></div></body></html>`);
  win.loadURL(`data:text/html;charset=utf-8,${html}`);
  return win;
}

async function boot() {
  mainWindow = createSplash("Starting local Resolvix API…");

  try {
    backend = startBackend({ port: DEFAULT_PORT });
  } catch (err) {
    mainWindow.loadURL(
      `data:text/html;charset=utf-8,${encodeURIComponent(
        `<h2>Failed to start Python backend</h2><pre>${String(err)}</pre>`
      )}`
    );
    return;
  }

  backend.child.on("exit", (code) => {
    if (!app.isQuitting && mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.loadURL(
        `data:text/html;charset=utf-8,${encodeURIComponent(
          `<div style="font-family:sans-serif;padding:2rem">
            <h2>Resolvix backend exited</h2>
            <p>Python process exited with code ${code}. Check that the project
            virtualenv exists and dependencies are installed.</p>
            <p>Project root: <code>${backend.projectRoot}</code></p>
            <p>Python: <code>${backend.python}</code></p>
          </div>`
        )}`
      );
    }
  });

  try {
    await backend.waitForReady(90000);
  } catch (err) {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.setSize(720, 420);
      mainWindow.loadURL(
        `data:text/html;charset=utf-8,${encodeURIComponent(
          `<div style="font-family:sans-serif;padding:2rem;line-height:1.45">
            <h2>Backend did not become ready</h2>
            <p>${String(err.message || err)}</p>
            <p>Ensure:</p>
            <ol>
              <li>Python venv at <code>${backend.projectRoot}/.venv</code></li>
              <li><code>pip install -r requirements.txt</code></li>
              <li>Port ${DEFAULT_PORT} is free</li>
            </ol>
            <p>Or set <code>RESOLVIX_ROOT</code> / <code>RESOLVIX_PYTHON</code>.</p>
          </div>`
        )}`
      );
    }
    return;
  }

  if (!mainWindow || mainWindow.isDestroyed()) return;

  mainWindow.setSize(1280, 860);
  mainWindow.center();
  mainWindow.loadURL(backend.url);

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });
}

app.whenReady().then(boot);

app.on("before-quit", () => {
  app.isQuitting = true;
  if (backend) stopBackend(backend.child);
});

app.on("window-all-closed", () => {
  if (backend) stopBackend(backend.child);
  if (process.platform !== "darwin") app.quit();
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) boot();
});
