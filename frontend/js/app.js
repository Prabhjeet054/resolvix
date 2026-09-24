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
    priorTickets: [],
    feedback: null,
    langView: "en",
    view: "resolve",
    incidentReport: null,
  };

  const $ = (id) => document.getElementById(id);

  function show(el, on) {
    el.classList.toggle("hidden", !on);
  }

  function setLoading(on, refine = false) {
    const el = $("loading");
    el.textContent = refine
      ? "Refining with chat history + same retrieved tickets…"
      : "Running agent pipeline…";
    show(el, on);
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
    refreshFeedbackStats();
  }

  async function refreshFeedbackStats() {
    const box = $("feedback-stats");
    if (!box) return;
    try {
      const review = await ResolvixAPI.feedbackReview("open");
      const s = review.stats || {};
      const desktop =
        window.resolvixDesktop && window.resolvixDesktop.isDesktop
          ? " · desktop"
          : "";
      box.textContent =
        `Feedback: 👍${s.up || 0} / 👎${s.down || 0} · ` +
        `${s.open_review_flags || 0} open review · ` +
        `${s.suppressible_tickets || 0} suppressible${desktop}`;
      box.className = "incident-panel";
    } catch (err) {
      box.textContent = `Feedback: unavailable (${err.message})`;
      box.className = "incident-panel warn";
    }
  }

  function clientSource() {
    if (window.resolvixDesktop && window.resolvixDesktop.isDesktop) {
      return "electron";
    }
    return "web";
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

  function renderConfidenceEscalation(result) {
    const panel = $("confidence-panel");
    if (!panel) return;

    const esc = result.escalation || {};
    const simPct =
      Number(
        (esc.top_similarity != null ? esc.top_similarity : result.confidence) || 0
      ) * 100;
    const floorPct = Math.round(
      Number(esc.threshold != null ? esc.threshold : 0.65) * 100
    );
    const required = Boolean(
      result.escalation_required || esc.ESCALATION_REQUIRED
    );
    const reasons = esc.reasons || [];
    const reasonText =
      reasons.length > 0
        ? reasons.join("; ")
        : result.escalation_hint || "";

    panel.classList.toggle("escalate", required);
    panel.classList.toggle("ok", !required);
    show(panel, true);

    const flag = $("confidence-flag");
    flag.textContent = required
      ? "ESCALATION_REQUIRED = TRUE · Auto-escalate"
      : "ESCALATION_REQUIRED = FALSE";
    flag.className = required
      ? "confidence-flag flag-escalate"
      : "confidence-flag flag-ok";

    $("confidence-pct").textContent = `${simPct.toFixed(1)}%`;
    $("confidence-floor").textContent = `${floorPct}%`;
    $("confidence-priority").textContent = result.priority || "—";
    $("confidence-bar").style.width = `${Math.min(100, Math.max(0, simPct))}%`;

    const g = result.groundedness || {};
    const gScore =
      result.groundedness_score != null
        ? Number(result.groundedness_score)
        : g.score != null
          ? Number(g.score)
          : null;
    const gEl = $("confidence-groundedness");
    if (gEl) {
      if (gScore == null) {
        gEl.textContent = "—";
      } else {
        const method = g.method ? ` · ${g.method}` : "";
        const fail = g.escalate ? " · fail" : "";
        gEl.textContent = `${(gScore * 100).toFixed(0)}%${method}${fail}`;
      }
    }

    const hint = panel.querySelector(".confidence-hint");
    if (hint) {
      hint.textContent =
        `Escalate when top similarity < ${floorPct}%, priority is CRITICAL, ` +
        `or groundedness self-check fails (every step must cite a retrieved ticket).`;
    }

    const escBox = $("escalation-box");
    if (required) {
      escBox.innerHTML =
        `<p class="escalate-warn">Human-in-the-loop escalation recommended — do not auto-close.</p>` +
        `<div class="escalate-grid">` +
        `<div><span class="metric-label">Tier / department</span>` +
        `<div><code>${escapeHtml(esc.tier || "—")}</code> · ` +
        `<strong>${escapeHtml(esc.department || "TBD")}</strong></div></div>` +
        `<div><span class="metric-label">On-call specialist</span>` +
        `<div>${escapeHtml(esc.on_call_specialist || "—")}</div></div>` +
        `<div><span class="metric-label">Queue</span>` +
        `<div><code>${escapeHtml(esc.queue || "—")}</code></div></div>` +
        `<div><span class="metric-label">Reasons</span>` +
        `<div>${escapeHtml(reasonText || "—")}</div></div>` +
        `</div>`;
    } else {
      const summary =
        esc.summary ||
        `Top similarity ${simPct.toFixed(1)}% ≥ ${floorPct}% and ` +
          `priority=${result.priority || "?"} — no page required.`;
      escBox.innerHTML = `<p class="escalate-ok">${escapeHtml(summary)}</p>`;
    }
  }

  function renderResult(result) {
    state.lastResult = result;
    show($("result-empty"), false);
    show($("result-panel"), true);
    $("btn-refine").disabled = false;

    const backend =
      result.search_backend === "ORACLE_23AI"
        ? "Oracle 23ai hybrid (vector + keyword)"
        : "In-Memory hybrid (cosine + keyword)";
    $("result-meta").textContent =
      `Backend: ${backend} · Language: ${result.detected_language_name || "?"} ` +
      `(${result.language_code || "?"})`;

    const tickets = result.similar_tickets || [];
    const hybridCount = tickets.filter(
      (t) => t.match_type === "hybrid" || t.match_type === "keyword"
    ).length;
    if (hybridCount) {
      $("result-meta").textContent +=
        ` · Hybrid matches: ${hybridCount}/${tickets.length}`;
    }
    if (result.refine_mode) {
      $("result-meta").textContent += result.reused_prior_tickets
        ? ` · Refine & Clarify (reused ${tickets.length} tickets)`
        : " · Refine & Clarify";
    }
    if (result.pii_redacted) {
      const parts = Object.entries(result.pii_counts || {})
        .map(([k, v]) => `${k}:${v}`)
        .join(", ");
      $("result-meta").textContent +=
        ` · PII redacted (${parts || "yes"})`;
    }
    if (result.groundedness_score != null || result.groundedness) {
      const g = result.groundedness || {};
      const gs =
        result.groundedness_score != null
          ? Number(result.groundedness_score)
          : Number(g.score || 0);
      $("result-meta").textContent +=
        ` · Groundedness: ${(gs * 100).toFixed(0)}%` +
        (g.escalate ? " (escalate)" : "");
    }

    const refineStatus = $("refine-status");
    if (refineStatus) {
      if (result.refine_mode && result.reused_prior_tickets) {
        refineStatus.className = "incident-panel";
        refineStatus.textContent =
          `Using prior conversation + the same ${tickets.length} retrieved ticket(s). ` +
          `Original issue kept for grounding.`;
        show(refineStatus, true);
      } else if (state.lastResult) {
        refineStatus.className = "incident-panel";
        refineStatus.textContent =
          "Ready for follow-ups — Ask follow-up reuses these tickets (no fresh search).";
        show(refineStatus, true);
      } else {
        show(refineStatus, false);
      }
    }

    const catClass = CATEGORY_PILL[result.category] || "pill-general";
    const priClass = PRIORITY_PILL[result.priority] || "pill-medium";
    $("result-badges").innerHTML =
      `<span class="pill ${catClass}">${escapeHtml(result.category)}</span>` +
      `<span class="pill ${priClass}">${escapeHtml(result.priority)}</span>`;

    $("classification-reason").textContent = result.classification_reasoning
      ? `Classification: ${result.classification_reasoning}`
      : "";

    renderConfidenceEscalation(result);

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
        const feedbackNote = match.feedback_flagged
          ? ` <span class="pill pill-critical">prior thumbs-down</span>`
          : "";
        const matchType = match.match_type || "vector";
        const matchPill =
          matchType === "hybrid"
            ? ` <span class="pill pill-tech">hybrid</span>`
            : matchType === "keyword"
              ? ` <span class="pill pill-security">keyword</span>`
              : ` <span class="pill pill-general">vector</span>`;
        const kwHits = (match.keyword_hits || []).slice(0, 4);
        const kwCaption = kwHits.length
          ? ` · hits: ${kwHits.map((h) => escapeHtml(String(h))).join(", ")}`
          : "";
        const votes = match.feedback_votes || {};
        const voteCaption =
          votes.up || votes.down
            ? ` · votes 👍${votes.up || 0} / 👎${votes.down || 0}`
            : "";
        card.className = "ticket-card";
        card.innerHTML =
          `<strong>#${idx + 1} · Ticket ${escapeHtml(match.ticket_id)}</strong> | ` +
          `Language: ${escapeHtml(String(match.language_code || "?").toUpperCase())} | ` +
          `Category: ${escapeHtml(match.category_name || "?")} | ` +
          `Priority: ${escapeHtml(match.priority || "?")}` +
          matchPill +
          feedbackNote +
          `<div class="progress"><span style="width:${Math.min(100, pct)}%"></span></div>` +
          `<p class="muted">Similarity: <strong>${pct.toFixed(1)}%</strong>${kwCaption}${voteCaption}</p>` +
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
    const turns = Math.ceil(state.chatHistory.length / 2);
    box.innerHTML =
      `<div class="muted" style="margin-bottom:0.35rem">Conversation (${turns} turn${
        turns === 1 ? "" : "s"
      })</div>` +
      state.chatHistory
        .map((m) => {
          const preview =
            m.content.length > 280 ? `${m.content.slice(0, 280)}…` : m.content;
          return `<div class="chat-turn"><strong>${escapeHtml(
            m.role
          )}:</strong> ${escapeHtml(preview)}</div>`;
        })
        .join("");
    show(box, true);
  }

  async function runResolve({ query, refine }) {
    const clean = (query || "").trim();
    if (!clean) {
      setError(
        refine
          ? "Enter a follow-up question before refining."
          : "Please enter a ticket description before searching."
      );
      return;
    }
    if (refine && !state.lastResult) {
      setError("Resolve a ticket first, then ask a follow-up.");
      return;
    }
    setError("");
    setLoading(true, Boolean(refine));
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
              {
                role: "user",
                content:
                  state.originalQuery ||
                  state.lastResult.original_query ||
                  state.lastResult.query,
              },
              { role: "assistant", content: state.lastResult.resolution },
            ];
        // Same retrieved tickets as the previous resolve (not re-searched).
        payload.prior_tickets =
          state.priorTickets && state.priorTickets.length
            ? state.priorTickets
            : state.lastResult.similar_tickets || [];
        payload.original_query =
          state.originalQuery ||
          state.lastResult.original_query ||
          state.lastResult.query;
      } else {
        state.chatHistory = [];
        state.originalQuery = clean;
        state.priorTickets = [];
      }

      const result = await ResolvixAPI.resolve(payload);
      state.feedback = null;
      $("feedback-msg").textContent = "";
      $("btn-up").disabled = false;
      $("btn-down").disabled = false;
      state.chatHistory = [
        ...(refine ? payload.chat_history || [] : []),
        { role: "user", content: clean },
        { role: "assistant", content: result.resolution },
      ];
      if (!state.originalQuery) {
        state.originalQuery = result.original_query || clean;
      }
      // Lock evidence set after first resolve; refine reuses it.
      if (!refine || !state.priorTickets.length) {
        state.priorTickets = result.similar_tickets || [];
      } else if (result.reused_prior_tickets) {
        state.priorTickets = result.similar_tickets || state.priorTickets;
      }
      if (refine) {
        $("follow-up").value = "";
        $("followup-preset").value = "";
      }
      renderResult(result);
    } catch (err) {
      setError(
        `Agent pipeline failed gracefully — check Oracle / Ollama health.\n${err.message}`
      );
    } finally {
      setLoading(false, Boolean(refine));
      refreshStatus();
    }
  }

  function wireThemeToggle() {
    const root = document.documentElement;

    function currentTheme() {
      return root.getAttribute("data-theme") === "dark" ? "dark" : "light";
    }

    function syncButtons(theme) {
      document.querySelectorAll("[data-theme-set]").forEach((btn) => {
        const active = btn.getAttribute("data-theme-set") === theme;
        btn.setAttribute("aria-pressed", active ? "true" : "false");
      });
    }

    function setTheme(theme) {
      const next = theme === "dark" ? "dark" : "light";
      root.setAttribute("data-theme", next);
      try {
        localStorage.setItem("resolvix-theme", next);
      } catch {
        // ignore private-mode storage failures
      }
      syncButtons(next);
    }

    document.querySelectorAll("[data-theme-set]").forEach((btn) => {
      btn.addEventListener("click", () => {
        setTheme(btn.getAttribute("data-theme-set"));
      });
    });

    syncButtons(currentTheme());
  }

  function setView(view, opts = {}) {
    const next = view === "incidents" ? "incidents" : "resolve";
    state.view = next;
    show($("view-resolve"), next === "resolve");
    show($("view-incidents"), next === "incidents");
    document.querySelectorAll(".nav-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.getAttribute("data-view") === next);
    });
    // Keep URL hash in sync so Electron / browser deep-links work the same.
    if (!opts.skipHash) {
      const target = next === "incidents" ? "#incidents" : "#resolve";
      if (window.location.hash !== target) {
        history.replaceState(null, "", target);
      }
    }
    if (window.resolvixDesktop && window.resolvixDesktop.isDesktop) {
      document.title =
        next === "incidents"
          ? "Resolvix — Emerging Incidents"
          : "Resolvix — Agentic RAG";
    }
    if (next === "incidents" && !state.incidentReport) {
      runIncidentScan();
    }
  }

  function applyHashRoute() {
    const hash = (window.location.hash || "").toLowerCase();
    if (hash === "#incidents" || hash.startsWith("#cluster-")) {
      setView("incidents", { skipHash: true });
      return;
    }
    if (hash.startsWith("#ticket-")) {
      // Ticket deep-links land on Resolve; chip click handler fills the query.
      setView("resolve", { skipHash: true });
      return;
    }
    setView("resolve", { skipHash: true });
  }

  function ticketChipsHtml(alert) {
    const ids = alert.ticket_ids || [];
    const samples = alert.sample_descriptions || [];
    if (!ids.length) return `<span class="muted">No ticket IDs</span>`;
    return (
      `<div class="ticket-chips">` +
      ids
        .map((tid, idx) => {
          const sample = samples[idx] || samples[0] || "";
          return (
            `<a class="ticket-chip" href="#ticket-${escapeHtml(String(tid))}" ` +
            `data-ticket-id="${escapeHtml(String(tid))}" ` +
            `data-sample="${escapeHtml(sample)}" ` +
            `title="Open in Agent Resolve">#${escapeHtml(String(tid))}</a>`
          );
        })
        .join("") +
      `</div>`
    );
  }

  function renderAlertCard(alert, kind) {
    const sim = Number(alert.avg_similarity || 0) * 100;
    const size = alert.size || (alert.ticket_ids || []).length;
    const windowLabel =
      alert.window_hours != null ? ` · ${alert.window_hours}h window` : "";
    const samples = (alert.sample_descriptions || []).slice(0, 3);
    const sampleHtml = samples.length
      ? `<ul class="sample-list">${samples
          .map((s) => `<li>${escapeHtml(s)}</li>`)
          .join("")}</ul>`
      : "";
    return (
      `<article class="cluster-card ${kind === "burst" ? "burst" : ""}" ` +
      `id="cluster-${escapeHtml(String(alert.cluster_id))}">` +
      `<h4>${kind === "burst" ? "Hourly burst" : "Cluster"} #${escapeHtml(
        String(alert.cluster_id)
      )}</h4>` +
      `<p class="cluster-meta">` +
      `${size} tickets · avg similarity ${sim.toFixed(1)}% · ` +
      `method ${escapeHtml(alert.method || "—")}${windowLabel}` +
      `</p>` +
      `<p>${escapeHtml(alert.message || "")}</p>` +
      `<div class="cluster-meta">Ticket IDs</div>` +
      ticketChipsHtml(alert) +
      sampleHtml +
      `</article>`
    );
  }

  function renderIncidentDashboard(report) {
    state.incidentReport = report;
    const clusters = report.alerts || [];
    const bursts = report.hourly_burst_alerts || [];
    const analyzed = report.tickets_analyzed || 0;

    $("incident-summary").textContent =
      report.message ||
      `Analyzed ${analyzed} tickets in the last ${report.hours || 24}h.`;

    $("incident-metrics").innerHTML =
      `<div class="incident-metric"><span class="metric-label">Tickets analyzed</span>` +
      `<span class="metric-value">${analyzed}</span></div>` +
      `<div class="incident-metric"><span class="metric-label">Cluster alerts</span>` +
      `<span class="metric-value">${clusters.length}</span></div>` +
      `<div class="incident-metric"><span class="metric-label">Hourly bursts</span>` +
      `<span class="metric-value">${bursts.length}</span></div>` +
      `<div class="incident-metric"><span class="metric-label">Method</span>` +
      `<span class="metric-value">${escapeHtml(report.method || "—")}</span></div>`;

    const banners = $("incident-banners");
    banners.innerHTML = "";
    if (bursts.length) {
      bursts.slice(0, 3).forEach((a) => {
        const el = document.createElement("div");
        el.className = "alert-banner critical";
        el.innerHTML =
          `<strong>Emerging Major Incident (burst)</strong> — ` +
          `${escapeHtml(a.message || "")}`;
        banners.appendChild(el);
      });
    }
    if (clusters.length) {
      clusters.slice(0, 3).forEach((a) => {
        const el = document.createElement("div");
        el.className = "alert-banner warning";
        el.innerHTML =
          `<strong>Cluster alert #${escapeHtml(String(a.cluster_id))}</strong> — ` +
          `${escapeHtml(a.message || "")}`;
        banners.appendChild(el);
      });
    }
    if (!bursts.length && !clusters.length) {
      banners.innerHTML =
        `<div class="alert-banner ok">No emerging major incidents detected in the analysis window.</div>`;
    }

    const clusterHost = $("incident-clusters");
    clusterHost.innerHTML = clusters.length
      ? clusters.map((a) => renderAlertCard(a, "cluster")).join("")
      : `<p class="muted">No dense clusters (≥ min size) in the last-24h window.</p>`;

    const burstHost = $("incident-bursts");
    burstHost.innerHTML = bursts.length
      ? bursts.map((a) => renderAlertCard(a, "burst")).join("")
      : `<p class="muted">No hourly burst alerts.</p>`;

    // Sidebar glance
    const side = $("incident-panel");
    if (bursts.length) {
      side.className = "incident-panel alert";
      side.textContent = bursts[0].message || report.message;
    } else if (clusters.length) {
      side.className = "incident-panel warn";
      side.textContent = clusters[0].message || report.message;
    } else {
      side.className = "incident-panel";
      side.textContent = report.message || "No emerging major incidents detected.";
    }

    // Wire ticket deep-links → Agent Resolve
    document.querySelectorAll(".ticket-chip").forEach((chip) => {
      chip.addEventListener("click", (e) => {
        e.preventDefault();
        const tid = chip.getAttribute("data-ticket-id");
        const sample = chip.getAttribute("data-sample") || "";
        const query =
          sample ||
          `Investigate related support ticket #${tid} from the emerging-incident cluster.`;
        $("query-text").value = query;
        setView("resolve");
        $("query-text").focus();
      });
    });
  }

  async function runIncidentScan() {
    const summary = $("incident-summary");
    const side = $("incident-panel");
    summary.textContent = "Clustering recent ticket embeddings…";
    side.className = "incident-panel";
    side.textContent = "Scanning…";
    $("incident-banners").innerHTML = "";
    $("incident-clusters").innerHTML = `<p class="muted">Scanning…</p>`;
    $("incident-bursts").innerHTML = `<p class="muted">Scanning…</p>`;
    try {
      const method = ($("cluster-method") && $("cluster-method").value) || "dbscan";
      const report = await ResolvixAPI.incidentsLast24h(method);
      renderIncidentDashboard(report);
    } catch (err) {
      summary.textContent = err.message;
      side.className = "incident-panel alert";
      side.textContent = err.message;
      $("incident-banners").innerHTML =
        `<div class="alert-banner critical">${escapeHtml(err.message)}</div>`;
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
      state.priorTickets = [];
      state.feedback = null;
      show($("result-panel"), false);
      show($("result-empty"), true);
      $("btn-refine").disabled = true;
      $("btn-up").disabled = false;
      $("btn-down").disabled = false;
      $("feedback-msg").textContent = "";
      const refineStatus = $("refine-status");
      if (refineStatus) show(refineStatus, false);
      renderChatHistory();
      setError("");
    });

    $("btn-clear-session").addEventListener("click", () => {
      $("btn-clear-query").click();
      $("incident-panel").className = "incident-panel hidden";
      $("incident-panel").textContent = "";
      state.incidentReport = null;
    });

    document.querySelectorAll(".nav-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        setView(btn.getAttribute("data-view"));
      });
    });

    const openIncidents = $("btn-open-incidents");
    if (openIncidents) {
      openIncidents.addEventListener("click", () => {
        state.incidentReport = null;
        setView("incidents");
      });
    }

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

    async function sendFeedback(vote) {
      if (!state.lastResult) {
        $("feedback-msg").textContent = "Resolve a ticket before sending feedback.";
        return;
      }
      state.feedback = vote;
      $("feedback-msg").textContent = "Saving feedback…";
      $("btn-up").disabled = true;
      $("btn-down").disabled = true;
      try {
        const ids =
          state.lastResult.similar_ticket_ids ||
          (state.lastResult.similar_tickets || [])
            .map((t) => t.ticket_id)
            .filter((x) => x != null);
        const resp = await ResolvixAPI.submitFeedback({
          vote,
          query:
            state.lastResult.query ||
            state.originalQuery ||
            $("query-text").value,
          resolution: resolutionBody(state.lastResult),
          similar_ticket_ids: ids,
          category: state.lastResult.category,
          priority: state.lastResult.priority,
          search_backend: state.lastResult.search_backend,
          source: clientSource(),
        });
        $("feedback-msg").textContent = resp.message || "Feedback recorded.";
        refreshFeedbackStats();
      } catch (err) {
        $("feedback-msg").textContent = err.message;
        $("btn-up").disabled = false;
        $("btn-down").disabled = false;
      }
    }

    $("btn-up").addEventListener("click", () => sendFeedback("up"));
    $("btn-down").addEventListener("click", () => sendFeedback("down"));

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

    $("btn-incident-scan").addEventListener("click", () => runIncidentScan());
  }

  document.addEventListener("DOMContentLoaded", () => {
    wireThemeToggle();
    wireEvents();
    applyHashRoute();
    window.addEventListener("hashchange", applyHashRoute);
    refreshStatus();
    setInterval(refreshStatus, 15000);
  });
})();
