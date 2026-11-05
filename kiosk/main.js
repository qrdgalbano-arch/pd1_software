// Electron kiosk wrapper: runs the prototype as a standalone, offline, locked-down window.
// - Files are served from a private app:// scheme (secure context => camera works, no web server needed).
// - The MediaPipe CDN URLs used by prototype/app.js are answered from node_modules (works offline).
// - Every other network request is blocked; navigation, new windows, devtools and common shortcuts are disabled.
const { app, BrowserWindow, protocol, session, Menu } = require("electron");
const path = require("path");
const fs = require("fs");

const DEBUG = process.env.KIOSK_DEBUG === "1";
const CONTENT = app.isPackaged ? path.join(process.resourcesPath, "content") : path.join(__dirname, "..");
const MP_DIR = path.join(__dirname, "node_modules", "@mediapipe", "tasks-vision");
const START_URL = "app://rehab/prototype/index.html";
const MIME = {
  ".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css", ".json": "application/json",
  ".wasm": "application/wasm", ".glb": "model/gltf-binary", ".task": "application/octet-stream",
  ".png": "image/png", ".jpg": "image/jpeg", ".svg": "image/svg+xml", ".woff2": "font/woff2", ".ttf": "font/ttf"
};

protocol.registerSchemesAsPrivileged([
  { scheme: "app", privileges: { standard: true, secure: true, supportFetchAPI: true, stream: true, corsEnabled: true } }
]);

function fileResponse(file) {
  try {
    const buf = fs.readFileSync(file);
    return new Response(buf, { headers: { "content-type": MIME[path.extname(file).toLowerCase()] || "application/octet-stream", "cache-control": "no-store" } });
  } catch {
    return new Response("Not found", { status: 404 });
  }
}
function mediapipeEntry() {
  try { const p = JSON.parse(fs.readFileSync(path.join(MP_DIR, "package.json"), "utf8")); return p.module || p.main || "vision_bundle.mjs"; }
  catch { return "vision_bundle.mjs"; }
}

if (!app.requestSingleInstanceLock()) app.quit();
app.commandLine.appendSwitch("ignore-gpu-blocklist");
app.commandLine.appendSwitch("enable-gpu-rasterization");
app.commandLine.appendSwitch("ozone-platform-hint", "auto");

let win;
function createWindow() {
  win = new BrowserWindow({
    fullscreen: true, kiosk: true, frame: false, autoHideMenuBar: true, backgroundColor: "#EFEADA",
    webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true, devTools: DEBUG, autoplayPolicy: "no-user-gesture-required" }
  });
  Menu.setApplicationMenu(null);
  win.loadURL(START_URL);
  const wc = win.webContents;
  wc.on("will-navigate", (e, url) => { if (!url.startsWith("app://rehab/")) e.preventDefault(); });
  wc.setWindowOpenHandler(() => ({ action: "deny" }));
  wc.on("context-menu", (e) => e.preventDefault());
  wc.on("render-process-gone", () => { if (win && !win.isDestroyed()) win.loadURL(START_URL); });
  wc.on("before-input-event", (e, input) => {
    if (input.type !== "keyDown") return;
    const k = String(input.key).toLowerCase(), c = input.control || input.meta;
    if (c && input.shift && input.alt && k === "q") { app.quit(); return; } // admin exit: Ctrl+Alt+Shift+Q
    if (DEBUG) return;
    const blocked = ["f5", "f11", "f12"].includes(k) ||
      (c && ["r", "w", "n", "t", "l", "p", "s", "+", "-", "=", "0"].includes(k)) ||
      (c && input.shift && ["i", "j", "c", "r"].includes(k)) ||
      (input.alt && ["arrowleft", "arrowright", "f4"].includes(k));
    if (blocked) e.preventDefault();
  });
  win.on("closed", () => app.quit());
}

app.whenReady().then(() => {
  protocol.handle("app", (req) => {
    const rel = decodeURIComponent(new URL(req.url).pathname);
    const file = path.normalize(path.join(CONTENT, rel));
    if (!file.startsWith(CONTENT)) return new Response("Forbidden", { status: 403 });
    return fileResponse(file);
  });
  // Offline: answer the MediaPipe CDN URLs from node_modules, block everything else on the network.
  protocol.handle("https", (req) => {
    const u = new URL(req.url);
    if (u.hostname === "cdn.jsdelivr.net") {
      const m = /^\/npm\/@mediapipe\/tasks-vision@[^/]+(\/.*)?$/.exec(u.pathname);
      if (m) {
        if (!m[1] || m[1] === "/") return fileResponse(path.join(MP_DIR, mediapipeEntry()));
        const file = path.normalize(path.join(MP_DIR, m[1]));
        if (file.startsWith(MP_DIR)) return fileResponse(file);
      }
    }
    return new Response("Blocked: offline kiosk", { status: 403 });
  });
  protocol.handle("http", () => new Response("Blocked: offline kiosk", { status: 403 }));

  const ses = session.defaultSession;
  ses.setPermissionRequestHandler((wc, permission, cb) => cb(permission === "media"));
  ses.setPermissionCheckHandler((wc, permission) => permission === "media");
  createWindow();
});
app.on("second-instance", () => { if (win) { win.show(); win.focus(); } });
app.on("window-all-closed", () => app.quit());
