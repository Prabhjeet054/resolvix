/**
 * Resolve project root + Python interpreter and spawn uvicorn.
 */
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");
const http = require("http");

const DEFAULT_HOST = "127.0.0.1";
const DEFAULT_PORT = Number(process.env.RESOLVIX_PORT || 8080);

function resolveProjectRoot() {
  if (process.env.RESOLVIX_ROOT) {
    return path.resolve(process.env.RESOLVIX_ROOT);
  }
  // electron/ sits one level below the repo root
  return path.resolve(__dirname, "..", "..");
}

function resolvePython(projectRoot) {
  if (process.env.RESOLVIX_PYTHON) {
    return process.env.RESOLVIX_PYTHON;
  }
  const candidates =
    process.platform === "win32"
      ? [
          path.join(projectRoot, ".venv", "Scripts", "python.exe"),
          path.join(projectRoot, "venv", "Scripts", "python.exe"),
          "python",
        ]
      : [
          path.join(projectRoot, ".venv", "bin", "python"),
          path.join(projectRoot, "venv", "bin", "python"),
          "python3",
          "python",
        ];

  for (const candidate of candidates) {
    if (candidate === "python" || candidate === "python3") {
      return candidate;
    }
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }
  return process.platform === "win32" ? "python" : "python3";
}

function waitForHealth(host, port, timeoutMs = 60000) {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve, reject) => {
    const attempt = () => {
      const req = http.get(
        { host, port, path: "/health", timeout: 2000 },
        (res) => {
          let data = "";
          res.on("data", (chunk) => {
            data += chunk;
          });
          res.on("end", () => {
            if (res.statusCode === 200) {
              resolve(data);
              return;
            }
            if (Date.now() > deadline) {
              reject(new Error(`Health check failed with status ${res.statusCode}`));
              return;
            }
            setTimeout(attempt, 500);
          });
        }
      );
      req.on("error", () => {
        if (Date.now() > deadline) {
          reject(
            new Error(
              `Backend did not become ready at http://${host}:${port}/health within ${timeoutMs}ms`
            )
          );
          return;
        }
        setTimeout(attempt, 500);
      });
      req.on("timeout", () => {
        req.destroy();
      });
    };
    attempt();
  });
}

function startBackend({ host = DEFAULT_HOST, port = DEFAULT_PORT } = {}) {
  const projectRoot = resolveProjectRoot();
  const python = resolvePython(projectRoot);
  const args = [
    "-m",
    "uvicorn",
    "api.main:app",
    "--host",
    host,
    "--port",
    String(port),
  ];

  const child = spawn(python, args, {
    cwd: projectRoot,
    env: { ...process.env, PYTHONUNBUFFERED: "1" },
    stdio: ["ignore", "pipe", "pipe"],
  });

  child.stdout.on("data", (buf) => {
    process.stdout.write(`[resolvix-api] ${buf}`);
  });
  child.stderr.on("data", (buf) => {
    process.stderr.write(`[resolvix-api] ${buf}`);
  });

  return {
    child,
    python,
    projectRoot,
    host,
    port,
    url: `http://${host}:${port}`,
    waitForReady: (timeoutMs) => waitForHealth(host, port, timeoutMs),
  };
}

function stopBackend(child) {
  if (!child || child.killed) return;
  try {
    if (process.platform === "win32") {
      spawn("taskkill", ["/pid", String(child.pid), "/f", "/t"]);
    } else {
      child.kill("SIGTERM");
      setTimeout(() => {
        if (!child.killed) child.kill("SIGKILL");
      }, 3000);
    }
  } catch {
    // ignore
  }
}

module.exports = {
  DEFAULT_HOST,
  DEFAULT_PORT,
  resolveProjectRoot,
  resolvePython,
  startBackend,
  stopBackend,
  waitForHealth,
};
