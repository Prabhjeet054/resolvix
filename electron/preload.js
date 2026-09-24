/**
 * Preload bridge — keep renderer isolated; expose read-only app meta if needed.
 * Shared UI in frontend/ detects desktop via window.resolvixDesktop.isDesktop.
 */
const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("resolvixDesktop", {
  isDesktop: true,
  platform: process.platform,
  shell: "electron",
  features: {
    emergingIncidents: true,
    confidenceEscalation: true,
    themeToggle: true,
    feedbackLoop: true,
  },
});
