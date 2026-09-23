/**
 * Resolvix shared UI — mirrors app/demo_app.py Streamlit dashboard.
 */
(function () {
  const PRESETS = {
    hi:
      "मेरा पासवर्ड रीसेट नहीं हो रहा है — ईमेल में मिला रीसेट लिंक " +
      "तुरंत समाप्त हो जाता है या अमान्य टोकन त्रुटि दिखाता है।",
    en:
      "I was charged twice for my monthly subscription on the same invoice " +
      "and need the extra charge reversed.",
    ta:
      "latest version-ல் mobile app splash screen-க்குப் பிறகு immediately " +
      "crash ஆகிறது; tickets open செய்ய முடியவில்லை.",
    es:
      "No puedo iniciar sesión: el enlace de restablecimiento de contraseña " +
      "caduca de inmediato o muestra un token inválido.",
    ja:
      "最新バージョンのモバイルアプリがスプラッシュ画面の直後にクラッシュし、" +
      "チケットを開けません。",
  };

  const CATEGORY_PILL = {
    TECH: "pill-tech",
    BILLING: "pill-billing",
    ACCOUNT: "pill-account",
    SECURITY: "pill-security",
    GENERAL: "pill-general",
  };
  const PRIORITY_PILL = {
    LOW: "pill-low",
    MEDIUM: "pill-medium",
    HIGH: "pill-high",
    CRITICAL: "pill-critical",
  };

  const state = {
    model: "",
    lastResult: null,
    chatHistory: [],
    originalQuery: "",
    feedback: null,
    langView: "en",
  };

  const $ = (id) => document.getElementById(id);

  function show(el, on) {
    el.classList.toggle("hidden", !on);
  }

  function setLoading(on) {
    show($("loading"), on);
    $("btn-resolve").disabled = on;
    $("btn-refine").disabled = on || !state.lastResult;
  }

  function setError(msg) {
    const banner = $("error-banner");
    if (!msg) {
      show(banner, false);
      banner.textContent = "";
      return;
    }
    banner.textContent = msg;
    show(banner, true);
  }

  function escapeHtml(text) {
    return String(text || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function simpleMarkdown(text) {
    const escaped = escapeHtml(text);
    return escaped
      .replace(/^### (.+)$/gm, "<strong>$1</strong>")
      .replace(/^## (.+)$/gm, "<strong>$1</strong>")
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/^- (.+)$/gm, "• $1")
      .replace(/\n/g, "<br>");
  }

  async function refreshStatus() {
    try {
      const status = await ResolvixAPI.getStatus(state.model || undefined);
      state.model = status.model || state.model;

      const oracle = $("badge-oracle");
      oracle.textContent = `Oracle 23ai: ${status.oracle_ok ? "🟢" : "🔴"} ${status.oracle_label}`;
      oracle.className = `badge-status ${status.oracle_ok ? "online" : "offline"}`;

      const ollama = $("badge-ollama");
      ollama.textContent = `Ollama LLM: ${status.ollama_ok ? "🟢" : "🔴"} ${status.ollama_label}`;
      ollama.className = `badge-status ${status.ollama_ok ? "online" : "offline"}`;

      const select = $("model-select");
      const models = status.models || [status.model];
      select.innerHTML = "";
      models.forEach((name) => {
        const opt = document.createElement("option");
        opt.value = name;
        opt.textContent = name;
        if (name === state.model) opt.selected = true;
        select.appendChild(opt);
      });
    } catch (err) {
      $("badge-oracle").textContent = "Oracle 23ai: 🔴 status unavailable";
      $("badge-ollama").textContent = `Ollama LLM: 🔴 ${err.message}`;
    }
  }

  function resolutionBody(result) {
    if (
      state.langView === "native" &&
      result.localized_resolution &&
      result.language_code &&
      result.language_code !== "en"
    ) {
      return result.localized_resolution;
    }
    return result.resolution;
  }

  function renderResult(result) {
    state.lastResult = result;
    show($("result-empty"), false);
    show($("result-panel"), true);
    $("btn-refine").disabled = false;

    const backend =
      result.search_backend === "ORACLE_23AI"
        ? "Oracle 23ai VECTOR_DISTANCE"
        : "In-Memory cosine fallback";
    const conf = ((result.confidence || 0) * 100).toFixed(1);
    $("result-meta").textContent =
      `Backend: ${backend} · Language: ${result.detected_language_name || "?"} ` +
      `(${result.language_code || "?"}) · Confidence: ${conf}%`;

    const catClass = CATEGORY_PILL[result.category] || "pill-general";
    const priClass = PRIORITY_PILL[result.priority] || "pill-medium";
    $("result-badges").innerHTML =
      `<span class="pill ${catClass}">${escapeHtml(result.category)}</span>` +
      `<span class="pill ${priClass}">${escapeHtml(result.priority)}</span>`;

    $("classification-reason").textContent = result.classification_reasoning
      ? `Classification: ${result.classification_reasoning}`
      : "";

    const escBox = $("escalation-box");
    if (result.escalation_required) {
      const esc = result.escalation || {};
      escBox.innerHTML =
        `<strong>ESCALATION_REQUIRED = TRUE</strong><br>` +
        `Route to: ${escapeHtml(esc.tier || "—")} ${escapeHtml(esc.department || "TBD")}<br>` +
        `On-call: ${escapeHtml(esc.on_call_specialist || "—")}<br>` +
        `Queue: ${escapeHtml(esc.queue || "—")}<br>` +
        `Reasons: ${escapeHtml((esc.reasons || []).join(", ") || result.escalation_hint || "")}`;
      show(escBox, true);
    } else {
      show(escBox, false);
    }

    const hasNative =
      Boolean(result.localized_resolution) &&
      result.language_code &&
      result.language_code !== "en";
    const toggle = $("lang-toggle");
    show(toggle, hasNative);
    if (hasNative) {
      const nativeLabel = toggle.querySelector('input[value="native"]').parentElement;
      nativeLabel.lastChild.textContent = ` Show ${result.detected_language_name || "native"}`;
    }

    $("resolution-card").innerHTML = simpleMarkdown(resolutionBody(result));

    const similar = $("similar-tickets");
    similar.innerHTML = "";
    const tickets = result.similar_tickets || [];
    if (!tickets.length) {
      similar.innerHTML = `<p class="muted">No similar resolved/closed tickets found.</p>`;
    } else {
      tickets.forEach((match, idx) => {
        const pct = Number(
          match.similarity_pct != null
            ? match.similarity_pct
            : (match.similarity_score || 0) * 100
        );
        const card = document.createElement("div");
        card.className = "ticket-card";
        card.innerHTML =
          `<strong>#${idx + 1} · Ticket ${escapeHtml(match.ticket_id)}</strong> | ` +
          `Language: ${escapeHtml(String(match.language_code || "?").toUpperCase())} | ` +
          `Category: ${escapeHtml(match.category_name || "?")} | ` +
          `Priority: ${escapeHtml(match.priority || "?")}` +
          `<div class="progress"><span style="width:${Math.min(100, pct)}%"></span></div>` +
          `<p class="muted">Similarity: <strong>${pct.toFixed(1)}%</strong></p>` +
          `<p><strong>Original Description:</strong><br>${escapeHtml(match.description || "(empty)")}</p>` +
          `<p><strong>Historical Resolution:</strong><br>${escapeHtml(match.resolution || "No resolution text stored.")}</p>`;
        similar.appendChild(card);
      });
    }

    const trace = $("trace-list");
    trace.innerHTML = "";
    (result.trace_steps || []).forEach((step) => {
      const li = document.createElement("li");
      li.innerHTML =
        `<strong>${escapeHtml(step.step)}</strong> — ${escapeHtml(step.duration_ms)} ms — ` +
        `${escapeHtml(step.details)}`;
      trace.appendChild(li);
    });

    $("live-sql").textContent = result.live_sql || "(no SQL captured)";
    renderChatHistory();
  }

  function renderChatHistory() {
    const box = $("chat-history");
    if (!state.chatHistory.length) {
      show(box, false);
      return;
    }
    box.innerHTML = state.chatHistory
      .map((m) => {
        const preview =
          m.content.length > 240 ? `${m.content.slice(0, 240)}…` : m.content;
        return `<div><strong>${escapeHtml(m.role)}:</strong> ${escapeHtml(preview)}</div>`;
      })
      .join("");
    show(box, true);
  }

  async function runResolve({ query, refine }) {
    const clean = (query || "").trim();
    if (!clean) {
      setError("Please enter a ticket description before searching.");
      return;
    }
    setError("");
    setLoading(true);
    $("file-ticket-msg").textContent = "";

    try {
      const payload = {
        query: clean,
        top_n: 3,
        model: state.model || undefined,
        category_filter: $("category-filter").value || null,
        priority_filter: $("priority-filter").value || null,
        language_override: $("lang-hint").value || null,
      };

      if (refine && state.lastResult) {
        payload.chat_history = state.chatHistory.length
          ? state.chatHistory
          : [
              { role: "user", content: state.lastResult.query || state.originalQuery },
              { role: "assistant", content: state.lastResult.resolution },
            ];
        payload.prior_tickets = state.lastResult.similar_tickets || [];
        payload.original_query = state.originalQuery || state.lastResult.query;
      } else {
        state.chatHistory = [];
        state.originalQuery = clean;
      }

      const result = await ResolvixAPI.resolve(payload);
      state.feedback = null;
      $("feedback-msg").textContent = "";
      state.chatHistory = [
        ...(refine ? payload.chat_history || [] : []),
        { role: "user", content: clean },
        { role: "assistant", content: result.resolution },
      ];
      if (!state.originalQuery) state.originalQuery = clean;
      renderResult(result);
    } catch (err) {
      setError(
        `Agent pipeline failed gracefully — check Oracle / Ollama health.\n${err.message}`
      );
    } finally {
      setLoading(false);
      refreshStatus();
    }
  }

  function wireEvents() {
    $("model-select").addEventListener("change", (e) => {
      state.model = e.target.value;
      refreshStatus();
    });

    $("preset-select").addEventListener("change", (e) => {
      const key = e.target.value;
      if (key && PRESETS[key]) $("query-text").value = PRESETS[key];
    });

    $("followup-preset").addEventListener("change", (e) => {
      if (e.target.value) $("follow-up").value = e.target.value;
    });

    $("btn-resolve").addEventListener("click", () =>
      runResolve({ query: $("query-text").value, refine: false })
    );
    $("btn-refine").addEventListener("click", () =>
      runResolve({ query: $("follow-up").value, refine: true })
    );

    $("btn-clear-query").addEventListener("click", () => {
      $("query-text").value = "";
      $("follow-up").value = "";
      state.lastResult = null;
      state.chatHistory = [];
      state.originalQuery = "";
      state.feedback = null;
      show($("result-panel"), false);
      show($("result-empty"), true);
      $("btn-refine").disabled = true;
      renderChatHistory();
      setError("");
    });

    $("btn-clear-session").addEventListener("click", () => {
      $("btn-clear-query").click();
      $("incident-panel").className = "incident-panel hidden";
      $("incident-panel").textContent = "";
    });

    document.querySelectorAll('input[name="lang-view"]').forEach((input) => {
      input.addEventListener("change", (e) => {
        state.langView = e.target.value;
        if (state.lastResult) {
          $("resolution-card").innerHTML = simpleMarkdown(
            resolutionBody(state.lastResult)
          );
        }
      });
    });

    $("btn-copy").addEventListener("click", async () => {
      if (!state.lastResult) return;
      const text = resolutionBody(state.lastResult);
      try {
        await navigator.clipboard.writeText(text);
        $("feedback-msg").textContent = "Copied to clipboard.";
      } catch {
        $("feedback-msg").textContent = "Copy failed — select text manually.";
      }
    });

    $("btn-up").addEventListener("click", () => {
      state.feedback = "up";
      $("feedback-msg").textContent = "Thanks — feedback recorded.";
    });
    $("btn-down").addEventListener("click", () => {
      state.feedback = "down";
      $("feedback-msg").textContent = "Thanks — we'll use this to improve grounding.";
    });

    $("btn-file-ticket").addEventListener("click", async () => {
      if (!state.lastResult) return;
      $("file-ticket-msg").textContent = "Filing ticket…";
      try {
        const resp = await ResolvixAPI.fileTicket({
          description: state.lastResult.query || state.originalQuery || $("query-text").value,
          category: state.lastResult.category,
          priority: state.lastResult.priority,
          language_code: state.lastResult.language_code || "en",
          resolution: state.lastResult.resolution,
        });
        $("file-ticket-msg").textContent = resp.message;
        refreshStatus();
      } catch (err) {
        $("file-ticket-msg").textContent = err.message;
      }
    });

    $("btn-incident-scan").addEventListener("click", async () => {
      const panel = $("incident-panel");
      panel.className = "incident-panel";
      panel.textContent = "Clustering recent ticket embeddings…";
      try {
        const report = await ResolvixAPI.incidentsLast24h($("cluster-method").value);
        const bursts = report.hourly_burst_alerts || [];
        const clusters = report.alerts || [];
        if (bursts.length) {
          panel.className = "incident-panel alert";
          panel.textContent = bursts[0].message || report.message || "Burst alert";
        } else if (clusters.length) {
          panel.className = "incident-panel warn";
          panel.textContent = clusters[0].message || report.message || "Cluster alert";
        } else {
          panel.className = "incident-panel";
          panel.textContent =
            report.message || "No emerging major incidents detected.";
        }
      } catch (err) {
        panel.className = "incident-panel alert";
        panel.textContent = err.message;
      }
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    wireEvents();
    refreshStatus();
    setInterval(refreshStatus, 15000);
  });
})();
