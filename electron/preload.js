/**
 * Preload bridge — keep renderer isolated; expose read-only app meta if needed.
 */
const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("resolvixDesktop", {
  isDesktop: true,
  platform: process.platform,
});
