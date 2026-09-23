/**
 * Resolve project root + Python interpreter and spawn uvicorn.
 */
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");
const http = require("http");
const net = require("net");

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

function probeHealth(host, port, timeoutMs = 1500) {
  return new Promise((resolve) => {
    const req = http.get({ host, port, path: "/health", timeout: timeoutMs }, (res) => {
      let data = "";
      res.on("data", (chunk) => {
        data += chunk;
      });
      res.on("end", () => {
        resolve(res.statusCode === 200 ? data : null);
      });
    });
    req.on("error", () => resolve(null));
    req.on("timeout", () => {
      req.destroy();
      resolve(null);
    });
  });
}

function isPortFree(host, port) {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.once("error", () => resolve(false));
    server.once("listening", () => {
      server.close(() => resolve(true));
    });
    server.listen(port, host);
  });
}

async function choosePort(host, preferred) {
  for (let port = preferred; port < preferred + 20; port += 1) {
    if (await isPortFree(host, port)) {
      return { port, reuse: false };
    }
  }
  throw new Error(
    `No free Resolvix API port found in range ${preferred}-${preferred + 19}`
  );
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

async function startBackend({ host = DEFAULT_HOST, port = DEFAULT_PORT } = {}) {
  const projectRoot = resolveProjectRoot();
  const python = resolvePython(projectRoot);
  const chosen = await choosePort(host, port);
  const selectedPort = chosen.port;

  if (chosen.reuse) {
    return {
      child: null,
      reused: true,
      python,
      projectRoot,
      host,
      port: selectedPort,
      url: `http://${host}:${selectedPort}`,
      waitForReady: async () => probeHealth(host, selectedPort),
    };
  }

  const args = [
    "-m",
    "uvicorn",
    "api.main:app",
    "--host",
    host,
    "--port",
    String(selectedPort),
  ];

  const child = spawn(python, args, {
    cwd: projectRoot,
    env: {
      ...process.env,
      PYTHONUNBUFFERED: "1",
      // Prefer cached sentence-transformers weights; avoid Hub round-trips on launch.
      HF_HUB_OFFLINE: process.env.HF_HUB_OFFLINE || "1",
      TRANSFORMERS_OFFLINE: process.env.TRANSFORMERS_OFFLINE || "1",
      HF_HUB_DISABLE_TELEMETRY: "1",
      TOKENIZERS_PARALLELISM: "false",
    },
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
    reused: false,
    python,
    projectRoot,
    host,
    port: selectedPort,
    url: `http://${host}:${selectedPort}`,
    waitForReady: (timeoutMs) => waitForHealth(host, selectedPort, timeoutMs),
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
  choosePort,
};
