#!/usr/bin/env node

const fs = require("fs");
const path = require("path");
const http = require("http");
const { execFile } = require("child_process");
const { createDashboardLegacyCompat } = require("./dashboard-legacy-compat.cjs");

const DEFAULT_HOST = "127.0.0.1";
const DEFAULT_PORT = 5055;
const DEFAULT_CACHE_TTL_MS = 5000;
const REPO_ROOT = path.resolve(__dirname, "..");
const DASHBOARD_DIR = path.join(REPO_ROOT, "dashboard");
const SWARM_UI_DIST_DIR = path.join(DASHBOARD_DIR, "swarm-ui", "dist");
const SWARM_UI_ALT_DIST_DIR = path.join(DASHBOARD_DIR, "swarm-ui-alt", "dist");
const MAIN_PY = path.join(REPO_ROOT, "main.py");
const PYTHON_BIN = process.env.PYTHON || process.env.PYTHON_BIN || "python3";
const DEFAULT_LEGACY_DATA_ROOT = process.env.SWARM_DASHBOARD_LEGACY_DATA_ROOT || "";
let legacyCompat = null;

const HELP_TEXT = `Swarm dashboard server

Usage:
  swarm-dashboard.cjs [options]
  swarm-dashboard.cjs --help

Options:
  --host <host>                  Bind host (default: ${DEFAULT_HOST})
  --port <port>                  Bind port (default: ${DEFAULT_PORT})
  --python <bin>                 Python interpreter for main.py (default: ${PYTHON_BIN})
  --repo-root <path>             Repo root containing main.py and dashboard/
  --cache-ttl <ms>               Cache TTL for JSON subprocess results (default: ${DEFAULT_CACHE_TTL_MS})
  --legacy-data-root <path>      Optional isolated persistence root for legacy backend state
  --no-cache                     Disable JSON response cache
  --help                         Show this help

Endpoints:
  GET /healthz
  GET /api/swarm/index
  GET /api/swarm/dashboard
  GET /api/swarm/health

UI:
  GET /                Redirects to /dashboard/
  GET /dashboard/      Serves the existing dashboard/index.html template with live data cards injected
  GET /dashboard/swarm-ui/index.html
  GET /dashboard/swarm-ui-alt/index.html

Examples:
  node scripts/swarm-dashboard.cjs
  node scripts/swarm-dashboard.cjs --port 8080
  node scripts/swarm-dashboard.cjs --python /usr/bin/python3
`;

function parseArgs(argv) {
  const opts = {
    host: DEFAULT_HOST,
    port: DEFAULT_PORT,
    python: PYTHON_BIN,
    repoRoot: REPO_ROOT,
    cacheTtlMs: DEFAULT_CACHE_TTL_MS,
    cacheEnabled: true,
    legacyDataRoot: DEFAULT_LEGACY_DATA_ROOT,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--help" || arg === "-h") {
      return { help: true };
    }
    if (arg === "--no-cache") {
      opts.cacheEnabled = false;
      continue;
    }
    const next = () => {
      if (i + 1 >= argv.length) {
        throw new Error(`Missing value for ${arg}`);
      }
      i += 1;
      return argv[i];
    };
    if (arg === "--host") {
      opts.host = next();
      continue;
    }
    if (arg === "--port") {
      opts.port = Number(next());
      continue;
    }
    if (arg === "--python") {
      opts.python = next();
      continue;
    }
    if (arg === "--repo-root") {
      opts.repoRoot = path.resolve(next());
      continue;
    }
    if (arg === "--cache-ttl") {
      opts.cacheTtlMs = Number(next());
      continue;
    }
    if (arg === "--legacy-data-root") {
      opts.legacyDataRoot = path.resolve(next());
      continue;
    }
    throw new Error(`Unknown argument: ${arg}`);
  }

  if (!Number.isFinite(opts.port) || opts.port <= 0) {
    throw new Error(`Invalid --port value: ${opts.port}`);
  }
  if (!Number.isFinite(opts.cacheTtlMs) || opts.cacheTtlMs < 0) {
    throw new Error(`Invalid --cache-ttl value: ${opts.cacheTtlMs}`);
  }
  return opts;
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function jsonResponse(res, statusCode, payload) {
  const body = JSON.stringify(payload, null, 2);
  res.writeHead(statusCode, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(body),
    "Cache-Control": "no-store",
  });
  res.end(body);
}

function textResponse(res, statusCode, body, contentType = "text/plain; charset=utf-8") {
  res.writeHead(statusCode, {
    "Content-Type": contentType,
    "Content-Length": Buffer.byteLength(body),
    "Cache-Control": "no-store",
  });
  res.end(body);
}

function readFileIfExists(filePath) {
  try {
    return fs.readFileSync(filePath, "utf8");
  } catch {
    return null;
  }
}

function contentTypeFor(filePath) {
  const extension = path.extname(filePath).toLowerCase();
  if (extension === ".html") return "text/html; charset=utf-8";
  if (extension === ".js") return "application/javascript; charset=utf-8";
  if (extension === ".css") return "text/css; charset=utf-8";
  if (extension === ".json") return "application/json; charset=utf-8";
  if (extension === ".svg") return "image/svg+xml";
  if (extension === ".png") return "image/png";
  if (extension === ".jpg" || extension === ".jpeg") return "image/jpeg";
  if (extension === ".woff") return "font/woff";
  if (extension === ".woff2") return "font/woff2";
  if (extension === ".br") return "application/octet-stream";
  if (extension === ".gz") return "application/gzip";
  return "application/octet-stream";
}

function tryServeStatic(res, baseDir, relativePath) {
  const safeRelative = relativePath.replace(/^\/+/, "") || "index.html";
  const resolved = path.resolve(baseDir, safeRelative);
  if (!resolved.startsWith(baseDir + path.sep) && resolved !== path.join(baseDir, "index.html")) {
    return false;
  }
  if (!fs.existsSync(resolved) || !fs.statSync(resolved).isFile()) {
    return false;
  }
  const payload = fs.readFileSync(resolved);
  textResponse(res, 200, payload, contentTypeFor(resolved));
  return true;
}

function loadDashboardTemplate() {
  const template = readFileIfExists(path.join(DASHBOARD_DIR, "index.html"));
  if (template) return template;
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Swarm Dashboard</title></head>
<body><main><h1>Swarm Dashboard</h1><p>Template missing.</p></main></body></html>`;
}

function buildLiveSection() {
  return `
      <section class="card live-panel">
        <span class="eyebrow">Live Runtime</span>
        <h2>Swarm JSON endpoints</h2>
        <p class="live-note">These cards are filled from the real CLI runtime via <code>main.py --json</code>.</p>
        <div class="live-grid">
          <article class="live-card" id="live-index-card"><h3>Index</h3><pre>Loading...</pre></article>
          <article class="live-card" id="live-dashboard-card"><h3>Dashboard</h3><pre>Loading...</pre></article>
          <article class="live-card" id="live-health-card"><h3>Health</h3><pre>Loading...</pre></article>
        </div>
      </section>`;
}

function buildClientScript() {
  return `
    <script>
      const endpoints = [
        ["live-index-card", "/api/swarm/index"],
        ["live-dashboard-card", "/api/swarm/dashboard"],
        ["live-health-card", "/api/swarm/health"],
      ];

      function formatValue(value) {
        if (value === null || value === undefined) return "null";
        if (typeof value === "string") return value;
        return JSON.stringify(value, null, 2);
      }

      function pickSummary(payload) {
        if (!payload || typeof payload !== "object") return payload;
        if (payload.counts && payload.recent) {
          return {
            ok: payload.ok,
            limit: payload.limit,
            counts: payload.counts,
            output_dirs: payload.output_dirs,
            recent_keys: Object.keys(payload.recent || {}),
          };
        }
        if (payload.rows) {
          return {
            ok: payload.ok,
            limit: payload.limit,
            sort_by: payload.sort_by,
            counts: payload.counts,
            kinds: payload.kinds,
            rows: (payload.rows || []).slice(0, 5),
          };
        }
        return payload;
      }

      async function refreshCard(id, url) {
        const card = document.getElementById(id);
        if (!card) return;
        const pre = card.querySelector("pre");
        try {
          const response = await fetch(url, { headers: { Accept: "application/json" } });
          const payload = await response.json();
          pre.textContent = formatValue(pickSummary(payload));
          card.dataset.state = response.ok ? "ok" : "error";
        } catch (error) {
          pre.textContent = String(error && error.message ? error.message : error);
          card.dataset.state = "error";
        }
      }

      async function refreshAll() {
        await Promise.all(endpoints.map(([id, url]) => refreshCard(id, url)));
      }

      refreshAll();
      setInterval(refreshAll, 15000);
    </script>`;
}

function injectDashboardTemplate(template) {
  const liveSection = buildLiveSection();
  const script = buildClientScript();
  let html = template;
  if (html.includes("<section class=\"grid\">")) {
    html = html.replace("<section class=\"grid\">", `${liveSection}\n      <section class="grid">`);
  } else if (html.includes("</main>")) {
    html = html.replace("</main>", `${liveSection}\n    </main>`);
  }
  if (html.includes("</style>")) {
    html = html.replace(
      "</style>",
      `
      .live-panel { margin: 28px 0 0; }
      .live-note { margin-top: 0; }
      .live-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
        gap: 12px;
        margin-top: 14px;
      }
      .live-card {
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 14px;
        background: rgba(255, 255, 255, 0.03);
        min-height: 160px;
      }
      .live-card h3 {
        margin: 0 0 10px;
        font-size: 1rem;
      }
      .live-card pre {
        margin: 0;
        white-space: pre-wrap;
        word-break: break-word;
        color: var(--muted);
        font-size: 0.84rem;
        line-height: 1.5;
      }
      .live-card[data-state="ok"] { box-shadow: inset 0 0 0 1px rgba(134, 215, 255, 0.12); }
      .live-card[data-state="error"] { box-shadow: inset 0 0 0 1px rgba(255, 116, 116, 0.25); }
      </style>`
    );
  }
  if (html.includes("</body>")) {
    html = html.replace("</body>", `${script}\n  </body>`);
  }
  return html;
}

function buildReadmePage(title, readmePath, backHref) {
  const raw = readFileIfExists(readmePath) || "README not found.";
  return `<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>${escapeHtml(title)}</title>
    <style>
      :root {
        color-scheme: dark;
        --bg: #08111f;
        --panel: #101c2e;
        --panel-alt: #16253b;
        --text: #e9f0fb;
        --muted: #9fb3cf;
        --accent: #86d7ff;
        --border: rgba(255, 255, 255, 0.09);
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        min-height: 100vh;
        font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
        background:
          radial-gradient(circle at top, rgba(134, 215, 255, 0.16), transparent 30%),
          linear-gradient(160deg, var(--bg), #050a12 70%);
        color: var(--text);
      }
      main {
        max-width: 980px;
        margin: 0 auto;
        padding: 40px 24px 56px;
      }
      .card {
        background: linear-gradient(180deg, var(--panel), var(--panel-alt));
        border: 1px solid var(--border);
        border-radius: 18px;
        padding: 20px;
      }
      a { color: var(--accent); text-decoration: none; }
      pre {
        white-space: pre-wrap;
        word-break: break-word;
        margin: 0;
        color: var(--muted);
        line-height: 1.6;
      }
      .actions { margin-top: 14px; }
    </style>
  </head>
  <body>
    <main>
      <div class="card">
        <h1>${escapeHtml(title)}</h1>
        <p><a href="${escapeHtml(backHref)}">Back to dashboard</a></p>
        <pre>${escapeHtml(raw)}</pre>
      </div>
    </main>
  </body>
</html>`;
}

function runMainJson(args, options = {}) {
  const { python, repoRoot, cacheKey, cacheEnabled, cacheTtlMs } = options;
  const useCache = cacheEnabled && cacheKey;
  const now = Date.now();
  if (useCache && commandCache.has(cacheKey)) {
    const cached = commandCache.get(cacheKey);
    if (cached.value && now - cached.at < cacheTtlMs) {
      return Promise.resolve(cached.value);
    }
    if (cached.promise) return cached.promise;
  }

  const promise = new Promise((resolve, reject) => {
    const startedAt = Date.now();
    const child = execFile(
      python,
      [MAIN_PY, ...args],
      {
        cwd: repoRoot,
        env: { ...process.env, PYTHONUNBUFFERED: "1" },
        maxBuffer: 20 * 1024 * 1024,
      },
      (error, stdout, stderr) => {
        if (error) {
          const details = [
            `Command failed: ${python} ${[MAIN_PY, ...args].join(" ")}`,
            stderr ? `stderr:\n${stderr.trim()}` : "",
            stdout ? `stdout:\n${stdout.trim()}` : "",
          ]
            .filter(Boolean)
            .join("\n\n");
          const wrapped = new Error(details);
          wrapped.cause = error;
          reject(wrapped);
          return;
        }
        try {
          const parsed = JSON.parse(stdout || "null");
          resolve({
            payload: parsed,
            meta: {
              command: [python, MAIN_PY, ...args].join(" "),
              duration_ms: Date.now() - startedAt,
              repo_root: repoRoot,
            },
          });
        } catch (parseError) {
          const wrapped = new Error(
            `Failed to parse JSON from ${python} ${[MAIN_PY, ...args].join(" ")}\n${String(stdout || "").trim()}`
          );
          wrapped.cause = parseError;
          reject(wrapped);
        }
      }
    );
    child.stdin?.end();
  });

  if (useCache) {
    commandCache.set(cacheKey, { promise });
    promise
      .then((value) => commandCache.set(cacheKey, { value, at: Date.now() }))
      .catch(() => commandCache.delete(cacheKey));
  }
  return promise;
}

function toBool(value) {
  if (value === undefined || value === null) return false;
  const normalized = String(value).trim().toLowerCase();
  return ["1", "true", "yes", "on"].includes(normalized);
}

function queryArgsForIndex(query) {
  const args = ["deliberation-campaign-index", "--json"];
  const limit = query.get("limit");
  if (limit) args.push("--limit", limit);
  const options = [
    ["campaign_output_dir", "--campaign-output-dir"],
    ["comparison_output_dir", "--comparison-output-dir"],
    ["export_output_dir", "--export-output-dir"],
    ["benchmark_output_dir", "--benchmark-output-dir"],
    ["matrix_benchmark_output_dir", "--matrix-benchmark-output-dir"],
    ["matrix_benchmark_export_output_dir", "--matrix-benchmark-export-output-dir"],
    ["matrix_benchmark_comparison_output_dir", "--matrix-benchmark-comparison-output-dir"],
    ["matrix_benchmark_comparison_export_output_dir", "--matrix-benchmark-comparison-export-output-dir"],
  ];
  for (const [key, flag] of options) {
    const value = query.get(key);
    if (value) args.push(flag, value);
  }
  return args;
}

function queryArgsForDashboard(query) {
  const args = ["deliberation-campaign-dashboard", "--json"];
  const kinds = query.getAll("kind");
  for (const kind of kinds) {
    if (kind) args.push("--kind", kind);
  }
  const limit = query.get("limit");
  if (limit) args.push("--limit", limit);
  const sortBy = query.get("sort_by");
  if (sortBy) args.push("--sort-by", sortBy);
  const campaignStatus = query.get("campaign_status");
  if (campaignStatus) args.push("--campaign-status", campaignStatus);
  if (toBool(query.get("comparable_only"))) args.push("--comparable-only");
  const options = [
    ["campaign_output_dir", "--campaign-output-dir"],
    ["comparison_output_dir", "--comparison-output-dir"],
    ["export_output_dir", "--export-output-dir"],
    ["benchmark_output_dir", "--benchmark-output-dir"],
    ["matrix_benchmark_output_dir", "--matrix-benchmark-output-dir"],
    ["matrix_benchmark_export_output_dir", "--matrix-benchmark-export-output-dir"],
    ["matrix_benchmark_comparison_output_dir", "--matrix-benchmark-comparison-output-dir"],
    ["matrix_benchmark_comparison_export_output_dir", "--matrix-benchmark-comparison-export-output-dir"],
  ];
  for (const [key, flag] of options) {
    const value = query.get(key);
    if (value) args.push(flag, value);
  }
  return args;
}

function queryArgsForHealth(query) {
  const args = ["runtime-health", "--json"];
  const runtime = query.get("runtime");
  if (runtime) args.push("--runtime", runtime);
  return args;
}

function sendError(res, error, statusCode = 500) {
  jsonResponse(res, statusCode, {
    ok: false,
    error: error && error.message ? error.message : String(error),
  });
}

function serveDashboardPage(res) {
  const html = injectDashboardTemplate(loadDashboardTemplate());
  textResponse(res, 200, html, "text/html; charset=utf-8");
}

function serveReadmeRoute(res, title, readmePath) {
  textResponse(res, 200, buildReadmePage(title, readmePath, "/dashboard/"), "text/html; charset=utf-8");
}

function routeRequest(req, res, opts) {
  const url = new URL(req.url, `http://${req.headers.host || "localhost"}`);
  const { pathname, searchParams } = url;

  if (pathname === "/healthz") {
    jsonResponse(res, 200, {
      ok: true,
      service: "swarm-dashboard",
      repo_root: opts.repoRoot,
      dashboard_dir: DASHBOARD_DIR,
      main_py: MAIN_PY,
      cache_enabled: opts.cacheEnabled,
      cache_ttl_ms: opts.cacheTtlMs,
      uptime_ms: Math.round(process.uptime() * 1000),
      timestamp: new Date().toISOString(),
    });
    return;
  }

  if (pathname === "/" || pathname === "") {
    res.writeHead(302, { Location: "/dashboard/" });
    res.end();
    return;
  }

  if (pathname === "/dashboard" || pathname === "/dashboard/") {
    serveDashboardPage(res);
    return;
  }

  if (pathname === "/dashboard/swarm-ui" || pathname === "/dashboard/swarm-ui/") {
    if (fs.existsSync(path.join(SWARM_UI_DIST_DIR, "index.html"))) {
      tryServeStatic(res, SWARM_UI_DIST_DIR, "index.html");
      return;
    }
    res.writeHead(302, { Location: "/dashboard/swarm-ui/index.html" });
    res.end();
    return;
  }

  if (pathname.startsWith("/dashboard/swarm-ui/")) {
    const relative = pathname.slice("/dashboard/swarm-ui/".length) || "index.html";
    if (fs.existsSync(path.join(SWARM_UI_DIST_DIR, "index.html")) && tryServeStatic(res, SWARM_UI_DIST_DIR, relative)) {
      return;
    }
    if (pathname === "/dashboard/swarm-ui/index.html") {
      serveReadmeRoute(res, "Swarm UI workspace", path.join(DASHBOARD_DIR, "swarm-ui", "README.md"));
      return;
    }
    res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
    res.end("Not Found");
    return;
  }

  if (pathname === "/dashboard/swarm-ui-alt" || pathname === "/dashboard/swarm-ui-alt/") {
    if (fs.existsSync(path.join(SWARM_UI_ALT_DIST_DIR, "index.html"))) {
      tryServeStatic(res, SWARM_UI_ALT_DIST_DIR, "index.html");
      return;
    }
    res.writeHead(302, { Location: "/dashboard/swarm-ui-alt/index.html" });
    res.end();
    return;
  }

  if (pathname.startsWith("/dashboard/swarm-ui-alt/")) {
    const relative = pathname.slice("/dashboard/swarm-ui-alt/".length) || "index.html";
    if (fs.existsSync(path.join(SWARM_UI_ALT_DIST_DIR, "index.html")) && tryServeStatic(res, SWARM_UI_ALT_DIST_DIR, relative)) {
      return;
    }
    if (pathname === "/dashboard/swarm-ui-alt/index.html") {
      serveReadmeRoute(res, "Swarm UI Alt workspace", path.join(DASHBOARD_DIR, "swarm-ui-alt", "README.md"));
      return;
    }
    res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
    res.end("Not Found");
    return;
  }

  if (pathname === "/api/swarm/index") {
    runMainJson(queryArgsForIndex(searchParams), {
      python: opts.python,
      repoRoot: opts.repoRoot,
      cacheEnabled: opts.cacheEnabled,
      cacheTtlMs: opts.cacheTtlMs,
      cacheKey: `index?${searchParams.toString()}`,
    })
      .then(({ payload }) => jsonResponse(res, 200, payload))
      .catch((error) => sendError(res, error));
    return;
  }

  if (pathname === "/api/swarm/dashboard") {
    runMainJson(queryArgsForDashboard(searchParams), {
      python: opts.python,
      repoRoot: opts.repoRoot,
      cacheEnabled: opts.cacheEnabled,
      cacheTtlMs: opts.cacheTtlMs,
      cacheKey: `dashboard?${searchParams.toString()}`,
    })
      .then(({ payload }) => jsonResponse(res, 200, payload))
      .catch((error) => sendError(res, error));
    return;
  }

  if (pathname === "/api/swarm/health") {
    runMainJson(queryArgsForHealth(searchParams), {
      python: opts.python,
      repoRoot: opts.repoRoot,
      cacheEnabled: opts.cacheEnabled,
      cacheTtlMs: opts.cacheTtlMs,
      cacheKey: `health?${searchParams.toString()}`,
    })
      .then(({ payload }) => jsonResponse(res, 200, payload))
      .catch((error) => sendError(res, error));
    return;
  }

  legacyCompat.handle(req, res, url).then((handled) => {
    if (handled) {
      return;
    }

    if (req.method !== "GET") {
      res.writeHead(405, {
        Allow: "GET, POST",
        "Content-Type": "text/plain; charset=utf-8",
      });
      res.end("Method Not Allowed");
      return;
    }

    res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
    res.end("Not Found");
  }).catch((error) => {
    sendError(res, error);
  });
}

const commandCache = new Map();

async function main() {
  let opts;
  try {
    opts = parseArgs(process.argv.slice(2));
  } catch (error) {
    if (String(error && error.message ? error.message : error).includes("Unknown argument")) {
      console.error(error.message);
      console.error("Use --help for usage.");
      process.exit(1);
      return;
    }
    if (error && error.message && error.message.includes("Missing value")) {
      console.error(error.message);
      console.error("Use --help for usage.");
      process.exit(1);
      return;
    }
    console.error(error.message || String(error));
    process.exit(1);
    return;
  }

  if (opts.help) {
    process.stdout.write(HELP_TEXT);
    return;
  }

  legacyCompat = createDashboardLegacyCompat({
    namespace: "swarm",
    title: "Swarm Dashboard",
    dataRoot: opts.legacyDataRoot || undefined,
  });

  const server = http.createServer((req, res) => {
    routeRequest(req, res, opts);
  });

  server.on("clientError", (err, socket) => {
    socket.end("HTTP/1.1 400 Bad Request\r\n\r\n");
    if (err) console.error(err.message || err);
  });

  process.on("SIGINT", () => {
    server.close(() => process.exit(0));
  });
  process.on("SIGTERM", () => {
    server.close(() => process.exit(0));
  });

  server.listen(opts.port, opts.host, () => {
    console.log(`Swarm dashboard listening at http://${opts.host}:${opts.port}/dashboard/`);
  });
}

main().catch((error) => {
  console.error(error && error.stack ? error.stack : error);
  process.exit(1);
});
