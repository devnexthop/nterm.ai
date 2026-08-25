const { contextBridge, ipcRenderer, shell } = require("electron");

contextBridge.exposeInMainWorld("nterm", {
  openExternal: (url) => ipcRenderer.invoke("open-external", url),
  platform: process.platform,
  versions: process.versions,
});
