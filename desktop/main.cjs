const { app, BrowserWindow, Menu, shell, dialog, ipcMain } = require("electron");
const { spawn } = require("child_process");
const http = require("http");
const path = require("path");
const fs = require("fs");

const PORT = Number(process.env.NTERM_PORT || 8787);
const HOST = "127.0.0.1";

let win;
let engine;

function dataDir() {
  return path.join(app.getPath("userData"), "data");
}

function engineCommand() {
  const packaged = app.isPackaged;
  if (packaged) {
    const exe = process.platform === "win32" ? "nterm-engine.exe" : "nterm-engine";
    const bin = path.join(process.resourcesPath, "engine", exe);
    if (fs.existsSync(bin)) return { cmd: bin, args: [], cwd: path.dirname(bin) };
  }
  const backend = path.join(__dirname, "..", "backend");
  const py = process.platform === "win32"
    ? path.join(backend, ".venv", "Scripts", "python.exe")
    : path.join(backend, ".venv", "bin", "python");
  return {
    cmd: fs.existsSync(py) ? py : (process.platform === "win32" ? "python" : "python3"),
    args: ["-m", "app.engine"],
    cwd: backend,
  };
}

function startEngine() {
  fs.mkdirSync(dataDir(), { recursive: true });
  const { cmd, args, cwd } = engineCommand();
  const env = {
    ...process.env,
    NTERM_DESKTOP: "1",
    NTERM_HOST: HOST,
    NTERM_PORT: String(PORT),
    NTERM_DATA_DIR: dataDir(),
    PYTHONUNBUFFERED: "1",
  };
  engine = spawn(cmd, args, { cwd, env, stdio: ["ignore", "pipe", "pipe"] });
  engine.stdout.on("data", (d) => process.stdout.write(`[nterm-engine] ${d}`));
  engine.stderr.on("data", (d) => process.stderr.write(`[nterm-engine] ${d}`));
  engine.on("exit", (code) => {
    if (win && !win.isDestroyed() && code && code !== 0) {
      dialog.showErrorBox("NTerm engine stopped", `The local engine exited (${code}).`);
    }
  });
}

function ping(url, tries = 80) {
  return new Promise((resolve, reject) => {
    const tick = (left) => {
      const req = http.get(url, (res) => {
        res.resume();
        if (res.statusCode && res.statusCode < 500) resolve();
        else if (left <= 0) reject(new Error(`No response from ${url}`));
        else setTimeout(() => tick(left - 1), 200);
      });
      req.on("error", () => {
        if (left <= 0) reject(new Error(`No response from ${url}`));
        else setTimeout(() => tick(left - 1), 200);
      });
    };
    tick(tries);
  });
}

function waitForEngine(tries = 80) {
  return ping(`http://${HOST}:${PORT}/api/health`, tries);
}

async function uiUrl() {
  if (!app.isPackaged) {
    try {
      await ping("http://127.0.0.1:5173/", 4);
      return "http://127.0.0.1:5173/";
    } catch {
      /* use engine static */
    }
  }
  return `http://${HOST}:${PORT}/`;
}

async function createWindow() {
  win = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1100,
    minHeight: 700,
    title: "NTerm",
    backgroundColor: "#07090d",
    icon: path.join(__dirname, "build", "icon.png"),
    autoHideMenuBar: process.platform === "win32",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  win.loadURL(await uiUrl());
  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });
}

function buildMenu() {
  const isMac = process.platform === "darwin";
  const template = [
    ...(isMac ? [{ role: "appMenu" }] : []),
    {
      label: "File",
      submenu: isMac ? [{ role: "close" }] : [{ role: "quit" }],
    },
    { role: "editMenu" },
    { role: "viewMenu" },
    { role: "windowMenu" },
    {
      label: "Help",
      submenu: [
        {
          label: "nterm.ai",
          click: () => shell.openExternal("https://nterm.ai"),
        },
        {
          label: "Downloads",
          click: () => shell.openExternal("https://nterm.ai/download"),
        },
      ],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

ipcMain.handle("open-external", (_e, url) => shell.openExternal(url));

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (win) {
      if (win.isMinimized()) win.restore();
      win.focus();
    }
  });
  app.whenReady().then(async () => {
    buildMenu();
    try {
      await waitForEngine(3);
    } catch {
      startEngine();
      try {
        await waitForEngine();
      } catch (err) {
        dialog.showErrorBox("NTerm failed to start", String(err.message || err));
        app.quit();
        return;
      }
    }
    await createWindow();
  });
}

app.on("before-quit", () => {
  if (engine && !engine.killed) engine.kill();
});
app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
