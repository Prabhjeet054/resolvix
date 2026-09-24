/**
 * Resolvix API client for the shared web / Electron UI.
 */
(function (global) {
  const DEFAULT_BASE =
    (typeof window !== "undefined" && window.RESOLVIX_API_BASE) ||
    `${window.location.protocol}//${window.location.host}`;

  async function request(path, options = {}) {
    const url = `${DEFAULT_BASE.replace(/\/$/, "")}${path}`;
    const resp = await fetch(url, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    let body = null;
    const text = await resp.text();
    try {
      body = text ? JSON.parse(text) : null;
    } catch {
      body = { detail: text };
    }
    if (!resp.ok) {
      const detail =
        (body && (body.detail || body.message)) || `HTTP ${resp.status}`;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    return body;
  }

  global.ResolvixAPI = {
    base: DEFAULT_BASE,
    getStatus(model) {
      const q = model ? `?model=${encodeURIComponent(model)}` : "";
      return request(`/api/v1/status${q}`);
    },
    resolve(payload) {
      return request("/api/v1/resolve", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
    fileTicket(payload) {
      return request("/api/v1/tickets", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
    submitFeedback(payload) {
      return request("/api/v1/feedback", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
    feedbackReview(status = "open") {
      const q = status ? `?status=${encodeURIComponent(status)}` : "";
      return request(`/api/v1/feedback/review${q}`);
    },
    incidentsLast24h(method, hours = 24, minClusterSize = 5) {
      const params = new URLSearchParams();
      if (method) params.set("method", method);
      if (hours != null) params.set("hours", String(hours));
      if (minClusterSize != null) {
        params.set("min_cluster_size", String(minClusterSize));
      }
      const q = params.toString() ? `?${params.toString()}` : "";
      return request(`/api/v1/incidents/last-24h${q}`);
    },
  };
})(window);
