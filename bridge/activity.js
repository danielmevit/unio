/* Unio — Copyright (C) 2026 Daniel Mitev; Daniel Mevit (@danielmevit).
 * https://github.com/danielmevit/unio
 * SPDX-License-Identifier: AGPL-3.0-only; see LICENSE and NOTICE. No warranty. */
(function () {
  "use strict";

  const SVG_NS = "http://www.w3.org/2000/svg";
  const NODE_WIDTH = 240, NODE_HEIGHT = 80;
  const themeSelector = document.getElementById("theme-selector");
  const STORAGE_KEY = "unio-theme-preference";
  const mql = window.matchMedia("(prefers-color-scheme: dark)");

  // The live selected preference is the authority. Storage only seeds it on
  // load, so a denied or failing store never overrides an explicit choice.
  function normalTheme(value) {
    return value === "light" || value === "dark" ? value : "system";
  }
  function storedTheme() {
    try {
      return normalTheme(localStorage.getItem(STORAGE_KEY));
    } catch (_) {
      return "system";
    }
  }
  let themePreference = storedTheme();

  function applyTheme() {
    const actual = themePreference === "system" ? (mql.matches ? "dark" : "light") : themePreference;
    document.documentElement.dataset.theme = actual;
    document.documentElement.dataset.themePreference = themePreference;
  }

  if (themeSelector) {
    themeSelector.value = themePreference;
    themeSelector.addEventListener("change", () => {
      themePreference = normalTheme(themeSelector.value);
      themeSelector.value = themePreference;
      try {
        localStorage.setItem(STORAGE_KEY, themePreference);
      } catch (_) {}
      applyTheme();
    });
  }
  mql.addEventListener("change", applyTheme);
  applyTheme();

  const status = document.getElementById("status");
  let busy = false;

  // The list is the readable default; a chosen view is remembered.
  const VIEW_KEY = "unio-task-view";
  let currentView = "list";
  try { if (localStorage.getItem(VIEW_KEY) === "map") currentView = "map"; } catch (_) {}
  function rememberView() { try { localStorage.setItem(VIEW_KEY, currentView); } catch (_) {} }
  const FILTERS_KEY = "unio-task-filters:v1";
  const FILTER_STATES = new Set(["", "all", "active", "attention", "finished"]);
  function validFilters(value) {
    if (!value || typeof value !== "object" || Array.isArray(value) || value.version !== 1) return false;
    const fields = { search: 256, worker: 128, state: 16, category: 128 };
    if (Object.keys(value).length !== 5) return false;
    for (const [name, limit] of Object.entries(fields)) {
      if (typeof value[name] !== "string" || value[name].length > limit || /[\x00-\x1f\x7f]/.test(value[name])) return false;
    }
    return FILTER_STATES.has(value.state);
  }
  function storedFilters() {
    try {
      const raw = localStorage.getItem(FILTERS_KEY);
      if (raw === null) return null;
      const value = raw.length <= 2048 ? JSON.parse(raw) : null;
      if (validFilters(value)) return value;
    } catch (_) {}
    try { localStorage.removeItem(FILTERS_KEY); } catch (_) {}
    return null;
  }
  const restoredFilters = storedFilters();
  let reconcileRestoredFilters = restoredFilters !== null;
  let mapCategoryFilter = restoredFilters ? restoredFilters.category : "";
  let mapSearchQuery = restoredFilters ? restoredFilters.search.toLowerCase() : "";
  let mapWorkerFilter = restoredFilters ? restoredFilters.worker : "";
  let mapStateFilter = restoredFilters ? restoredFilters.state : "";
  function rememberFilters() {
    const value = { version: 1, search: document.getElementById("map-search").value,
      worker: mapWorkerFilter, state: mapStateFilter, category: mapCategoryFilter };
    try {
      if (validFilters(value)) localStorage.setItem(FILTERS_KEY, JSON.stringify(value));
      else localStorage.removeItem(FILTERS_KEY);
    } catch (_) {}
  }
  let mapCurrentPage = 0;
  let mapFitView = true;
  const mapCamera = { x: 0, y: 0, scale: 1 };
  let mapBounds = { x: 120, y: 80 };
  let mapDrag = null;
  let suppressMapClick = false;
  const MIN_MAP_SCALE = 0.05, MAX_MAP_SCALE = 3;
  const MAP_PAGE_SIZE = 24;
  const MAP_GRID = 14; // map units between the background dots
  let lastData = null;
  // Selection is an exact node key plus its tuple; never a display label.
  let selected = null;

  function updateViewSwitch() {
    const mapBtn = document.getElementById("view-map");
    const listBtn = document.getElementById("view-list");
    if (mapBtn && listBtn) {
      mapBtn.setAttribute("aria-pressed", currentView === "map" ? "true" : "false");
      listBtn.setAttribute("aria-pressed", currentView === "list" ? "true" : "false");
      document.getElementById("tasks-map-container").hidden = currentView !== "map";
      document.getElementById("tasks").hidden = currentView !== "list";
      // the running-first hint describes the map's order, not the list's
      document.getElementById("map-activity").hidden = currentView !== "map";
    }
  }

  // "?" in the map controls: hover or keyboard focus shows how to read the
  // map; a click or tap keeps it open until clicked again, Escape or a
  // click elsewhere.
  const helpToggle = document.getElementById("map-help-toggle");
  if (helpToggle) {
    const wrap = helpToggle.parentElement;
    const setOpen = (open) => { wrap.classList.toggle("is-open", open); helpToggle.setAttribute("aria-expanded", String(open)); };
    helpToggle.addEventListener("click", () => setOpen(!wrap.classList.contains("is-open")));
    helpToggle.addEventListener("keydown", (event) => { if (event.key === "Escape") { setOpen(false); helpToggle.blur(); } });
    document.addEventListener("pointerdown", (event) => { if (!wrap.contains(event.target)) setOpen(false); });
  }

  const mapBtn = document.getElementById("view-map");
  if (mapBtn) {
    mapBtn.addEventListener("click", () => { currentView = "map"; rememberView(); updateViewSwitch(); if (lastData) render(lastData); });
    document.getElementById("view-list").addEventListener("click", () => { currentView = "list"; rememberView(); updateViewSwitch(); if (lastData) render(lastData); });

    document.getElementById("map-search").addEventListener("input", (e) => { e.target.value = e.target.value.slice(0, 256); mapSearchQuery = e.target.value.toLowerCase(); mapCurrentPage = 0; rememberFilters(); if (lastData) render(lastData); });
    document.getElementById("map-worker-filter").addEventListener("change", (e) => { mapWorkerFilter = e.target.value; mapCurrentPage = 0; rememberFilters(); if (lastData) render(lastData); else syncWorkerOptions([]); });
    document.getElementById("map-state-filter").addEventListener("change", (e) => { mapStateFilter = e.target.value; mapCurrentPage = 0; rememberFilters(); if (lastData) render(lastData); });
    document.getElementById("map-category-filter").addEventListener("change", (e) => { mapCategoryFilter = e.target.value; mapCurrentPage = 0; rememberFilters(); if (lastData) render(lastData); else syncCategoryOptions([]); });

    document.getElementById("map-reset-filters").addEventListener("click", () => {
      mapSearchQuery = "";
      mapWorkerFilter = "";
      mapStateFilter = "";
      mapCategoryFilter = "";
      document.getElementById("map-search").value = "";
      document.getElementById("map-worker-filter").value = "";
      document.getElementById("map-state-filter").value = "";
      document.getElementById("map-category-filter").value = "";
      mapCurrentPage = 0;
      rememberFilters();
      if (lastData) render(lastData);
    });

    for (const button of document.querySelectorAll("#task-summary button")) {
      button.addEventListener("click", () => {
        const state = button.dataset.state;
        mapStateFilter = mapStateFilter === state ? "" : state;
        document.getElementById("map-state-filter").value = mapStateFilter;
        mapCurrentPage = 0;
        rememberFilters();
        if (lastData) render(lastData);
      });
    }

    document.getElementById("map-prev-page").addEventListener("click", () => { mapCurrentPage = Math.max(0, mapCurrentPage - 1); if (lastData) render(lastData); });
    document.getElementById("map-next-page").addEventListener("click", () => { mapCurrentPage++; if (lastData) render(lastData); });
    document.getElementById("map-fit").addEventListener("click", () => { mapFitView = true; applyMapPresentation(); });
    document.getElementById("map-reset").addEventListener("click", resetMapCamera);
    document.getElementById("map-zoom-in").addEventListener("click", () => zoomMap(1.25));
    document.getElementById("map-zoom-out").addEventListener("click", () => zoomMap(1 / 1.25));
    setupMapGestures();
    document.getElementById("map-search").value = restoredFilters ? restoredFilters.search : "";
    document.getElementById("map-state-filter").value = mapStateFilter;
    updateViewSwitch();
    applyMapPresentation();
    new ResizeObserver(applyMapPresentation).observe(document.getElementById("work-map").parentElement);
  }

  function text(tag, value, className = "") {
    const element = document.createElement(tag);
    element.textContent = value;
    element.className = className;
    return element;
  }
  function setText(element, value) {
    if (element.textContent !== value) element.textContent = value;
  }
  function label(value) {
    return String(value).replaceAll("_", " ");
  }

  function render(data) {
    lastData = data;
    // Only restored choices are reconciled once live evidence arrives. Keep
    // existing live-selection behavior when a later observation omits a worker.
    if (reconcileRestoredFilters) {
      reconcileRestoredFilters = false;
      const oldWorker = mapWorkerFilter, oldCategory = mapCategoryFilter;
      if (mapWorkerFilter && !data.results.some((r) => r.worker === mapWorkerFilter)) mapWorkerFilter = "";
      if (mapCategoryFilter && !data.results.some((r) => taskKind(r) === mapCategoryFilter)) mapCategoryFilter = "";
      if (oldWorker !== mapWorkerFilter || oldCategory !== mapCategoryFilter) rememberFilters();
    }
    const { filtered, categories, tally } = getFilteredTasks(data);

    filtered.sort((a, b) => {
      const rank = { active: 0, attention: 1, finished: 2 };
      const priority = rank[categories.get(a).category] - rank[categories.get(b).category];
      if (priority) return priority;
      if (a.worker !== b.worker) return a.worker < b.worker ? -1 : 1;
      return a.task < b.task ? -1 : a.task > b.task ? 1 : 0;
    });

    const totalPages = Math.ceil(filtered.length / MAP_PAGE_SIZE);
    if (mapCurrentPage >= totalPages) mapCurrentPage = Math.max(0, totalPages - 1);
    const pageTasks = filtered.slice(mapCurrentPage * MAP_PAGE_SIZE, (mapCurrentPage + 1) * MAP_PAGE_SIZE);

    // Update shared controls UI
    syncWorkerOptions(data.results.map((r) => r.worker));
    syncCategoryOptions(data.results.map(taskKind));

    let counts = data.results.length + " total tasks (" + tally.attention + " need attention, " + tally.active + " active, " + tally.finished + " finished) · " + filtered.length + " shown";
    if (mapWorkerFilter && !data.results.some((r) => r.worker === mapWorkerFilter))
      counts += " · worker " + mapWorkerFilter + " is not in the current observation";
    if (mapCategoryFilter && !data.results.some((r) => taskKind(r) === mapCategoryFilter))
      counts += " · category " + mapCategoryFilter + " is not in the current observation";
    setText(document.getElementById("map-counts"), counts);

    const pagination = document.getElementById("map-pagination");
    const prevBtn = document.getElementById("map-prev-page");
    const nextBtn = document.getElementById("map-next-page");
    const pageInfo = document.getElementById("map-page-info");
    if (filtered.length > MAP_PAGE_SIZE) {
      pagination.hidden = false;
      setText(pageInfo, "Page " + (mapCurrentPage + 1) + " of " + (totalPages || 1));
      prevBtn.disabled = mapCurrentPage === 0;
      nextBtn.disabled = mapCurrentPage >= totalPages - 1;
    } else {
      pagination.hidden = true;
      setText(pageInfo, "");
    }

    setText(document.getElementById("map-activity"), tally.active
      ? tally.active + " active " + (tally.active === 1 ? "task" : "tasks") + " · Running tasks appear first. Choose Active to focus on them."
      : "No recorded workers are running. These nodes show task history and outstanding checks or reviews. Lead CLI activity is not shown here.");
    const empty = document.getElementById("map-empty");
    empty.hidden = filtered.length !== 0;
    setText(empty, mapStateFilter === "active" ? "No active tasks match these filters."
      : !mapStateFilter && tally.finished ? "No current work matches these filters. Choose All states or Finished to include " + tally.finished + " finished " + (tally.finished === 1 ? "task" : "tasks") + "."
      : "No tasks match these filters.");

    if (currentView === "map") renderMap(data, pageTasks, categories);
    // The list shares the same filtered page and is kept current even while
    // hidden, so switching views never shows an older observation.
    renderSummary(tally);
    renderTaskList(data, pageTasks, categories);
    renderTools(data);
    renderTimeline(data);
    setText(document.getElementById("events-raw"), JSON.stringify(
      { recent_events: data.recent_events, warnings: data.warnings },
      null,
      2,
    ));
    status.className = "";
    status.textContent =
      "Observed " +
      data.observed_at +
      " · STOP " +
      (data.stopped ? "active" : "clear");
  }

  // ---- Plain-language task state ------------------------------------------
  // One state per task, from the same strict verdict as the map: a task is
  // Finished only when its run succeeded, its checks passed and a review
  // approved it. Every state names one next step as a real unio command.
  // Worker and task names come from project files, so a suggested command
  // quotes them: pasting it can only ever run unio with those names. A name
  // with control characters or a leading "-" gets no command at all.
  const SAFE_ARG = /^[A-Za-z0-9._\/@%+=:,][A-Za-z0-9._\/@%+=:,-]*$/;
  function shellArg(value) {
    const v = String(value);
    if (/[\u0000-\u001f\u007f]/.test(v) || v.startsWith("-") || !v) return null;
    return SAFE_ARG.test(v) ? v : "'" + v.replaceAll("'", "'\\''") + "'";
  }
  function unioCommand(verb, ...args) {
    const quoted = args.map(shellArg);
    return quoted.includes(null) ? null : ["unio", verb, ...quoted].join(" ");
  }
  function humanState(r, verdict, latestForWorker = true) {
    const process = sectionState(r, "process"), validation = sectionState(r, "validation"), review = sectionState(r, "review");
    const w = r.worker, t = r.task;
    const v = r.validation || {};
    const exit = r.process && r.process.exit_code !== null && r.process.exit_code !== undefined ? " (exit " + r.process.exit_code + ")" : "";
    if (verdict.category === "active")
      return { label: "Running", sentence: "The worker is running this task now.", next: ["Follow the live log", unioCommand("tail", t)] };
    if (process === "running" || r.activity === "completion_unknown")
      return { label: "Run status unknown", sentence: "The run has no recorded end; it may have been interrupted.", next: ["Read the report", unioCommand("report", t)] };
    if (process !== "succeeded")
      return { label: "Run failed", sentence: (process === "failed" ? "The run failed" : "The run ended: " + label(process)) + exit + ".", next: ["Read the report", unioCommand("report", t)] };
    if (validation === "failed")
      return { label: "Checks failed", sentence: (v.checks_failed ?? "Some") + " of " + (v.checks_run ?? "its") + " checks failed.", next: ["Read why", unioCommand("report", t)] };
    if (validation !== "passed")
      return { label: "Checks not run", sentence: "The run finished; its checks have not run yet.", next: ["Run the checks", unioCommand("verify", w, t)] };
    if (review === "not_run")
      return { label: "Waiting for review", sentence: "Ran and passed its checks; no review yet.", next: ["Ask another lab to review", unioCommand("review", w, t)] };
    if (review === "changes_requested")
      return { label: "Changes requested", sentence: "The reviewer asked for changes.", next: ["Read the review", unioCommand("report", t)] };
    if (review !== "approved")
      return { label: "Review " + label(review), sentence: "The review did not finish with a decision.", next: ["Read the report", unioCommand("report", t)] };
    if (verdict.category !== "finished")
      return { label: "Evidence is stale", sentence: "Approved, but the worktree changed since; check it again.", next: ["Check again", unioCommand("verify", w, t)] };
    const reviewer = r.review && r.review.reviewer;
    // unio diff shows the worker's whole current branch, not one task.
    return { label: "Finished", sentence: (reviewer ? "Approved by " + reviewer + "." : "Approved.") + " Merging is your call.",
      next: [latestForWorker ? "Inspect the branch before you merge" : "Worker's branch (includes later work)", unioCommand("diff", w)] };
  }
  // Run → Checks → Review, each done, failed, waiting or unknown.
  function trackSteps(r) {
    const process = sectionState(r, "process"), validation = sectionState(r, "validation"), review = sectionState(r, "review");
    const v = r.validation || {};
    const run = process === "succeeded" ? "done" : process === "running" ? (r.activity === "running_recorded" ? "running" : "unknown")
      : r.activity === "completion_unknown" ? "unknown" : "failed";
    const checks = validation === "passed" ? "done" : validation === "failed" ? "failed" : "waiting";
    const rev = review === "approved" ? "done" : review === "changes_requested" ? "failed" : review === "not_run" ? "waiting" : "unknown";
    const counted = typeof v.checks_run === "number" && v.checks_run > 0 ? " " + (v.checks_run - (v.checks_failed || 0)) + "/" + v.checks_run : "";
    return [["Run", run], ["Checks" + counted, checks], ["Review", rev]];
  }
  const STEP_WORDS = { done: "done", failed: "failed", waiting: "not yet", running: "running", unknown: "unknown" };
  function trackElement(r) {
    const ol = text("ol", "", "track");
    for (const [name, step] of trackSteps(r)) {
      const li = text("li", name);
      li.dataset.step = step;
      li.title = name + ": " + STEP_WORDS[step];
      ol.append(li);
    }
    return ol;
  }
  // "12 min ago" against the observation time (never the viewer's clock);
  // the exact local time is one hover away.
  function ago(iso, nowIso) {
    const then = Date.parse(iso), now = Date.parse(nowIso);
    if (!Number.isFinite(then) || !Number.isFinite(now)) return "time unknown";
    const s = Math.max(0, Math.round((now - then) / 1000));
    if (s < 60) return "just now";
    if (s < 3600) return Math.round(s / 60) + " min ago";
    if (s < 86400) return Math.round(s / 3600) + " h ago";
    const d = Math.round(s / 86400);
    return d + (d === 1 ? " day ago" : " days ago");
  }
  function exactTime(iso) {
    const t = Date.parse(iso);
    return Number.isFinite(t) ? new Date(t).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "medium" }) : "unknown";
  }
  function agentBadge(worker) {
    const identity = agentIdentity(worker);
    const wrap = text("span", "", "agent-badge");
    wrap.dataset.agentMark = identity.mark;
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("class", "agent-logo");
    const paths = identity.mark && AI_MARKS[identity.mark];
    if (paths) {
      for (const d of paths) {
        const path = document.createElementNS(SVG_NS, "path");
        path.setAttribute("d", d);
        svg.appendChild(path);
      }
    } else {
      const initials = document.createElementNS(SVG_NS, "text");
      initials.setAttribute("x", "12"); initials.setAttribute("y", "16.5");
      initials.setAttribute("text-anchor", "middle"); initials.setAttribute("font-size", "11");
      initials.textContent = identity.initials;
      svg.appendChild(initials);
    }
    wrap.append(svg, text("span", worker, "agent-name"));
    return wrap;
  }
  function nextStep(next) {
    const box = text("div", "", "next-step");
    if (!next[1]) {
      box.append(text("span", "Next step", "next-label"), text("p", "No command shown: this name has characters that cannot be pasted safely.", "small"));
      return box;
    }
    box.append(text("span", next[0], "next-label"));
    const line = text("div", "", "next-line");
    const code = text("code", next[1]);
    const copy = text("button", "Copy", "copy-command");
    copy.type = "button";
    copy.setAttribute("aria-label", "Copy command: " + next[1]);
    copy.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(next[1]); setText(copy, "Copied"); }
      catch (_) { setText(copy, "Select it"); }
      setTimeout(() => setText(copy, "Copy"), 1600);
    });
    line.append(code, copy);
    box.append(line);
    return box;
  }
  function technicalLines(r) {
    const lines = [
      "Process " + label(sectionState(r, "process")) + " · exit " + (r.process && r.process.exit_code !== null && r.process.exit_code !== undefined ? r.process.exit_code : "unknown") + " · worker lock " + r.worker_lock,
      "Validation " + label(sectionState(r, "validation")) + " · " + (r.validation ? r.validation.checks_run : "unknown") + " checks / " + (r.validation ? r.validation.checks_failed : "unknown") + " failed",
      "Review " + label(sectionState(r, "review")) + " · reviewer " + ((r.review && r.review.reviewer) || "not recorded"),
      "Recorded at " + (r.recorded_at || "unknown"),
    ];
    if (r.activity === "completion_unknown") lines.push("No completion recorded; interruption possible. Detached processes are not ruled out.");
    return lines;
  }
  function isLatestForWorker(data, r) {
    const mine = Date.parse(r.recorded_at) || 0;
    return !data.results.some((o) => o !== r && o.worker === r.worker && (Date.parse(o.recorded_at) || 0) > mine);
  }
  // ---- Activity timeline: each recorded event as one plain line ----------
  function eventLine(e) {
    const t = e.task || "a task";
    const n = (v) => (typeof v === "number" ? v : "?");
    switch (e.event) {
      case "run_start": return ["Started " + t, "neutral"];
      case "run": return e.exit === 0
        ? ["Finished the run of " + t + (typeof e.duration_s === "number" ? " in " + span(e.duration_s) : ""), "passed"]
        : ["Run of " + t + " ended with exit " + n(e.exit) + (e.wall ? " (time limit)" : ""), "failed"];
      case "verify": {
        const run = n(e.validate_run), failed = n(e.validate_failed);
        const scope = e.scope && e.scope !== "OK" ? " · scope " + label(String(e.scope)).toLowerCase() : "";
        return e.verdict === "PASS" ? [t + " passed its checks (" + run + "/" + run + ")" + scope, "passed"]
          : e.verdict === "FAIL" ? [t + " failed " + failed + " of " + run + " checks" + scope, "failed"]
            : [t + " checks " + label(String(e.verdict || "unknown")).toLowerCase() + scope, "attention"];
      }
      case "review": return e.decision === "approved"
        ? [(e.reviewer || "A reviewer") + " approved " + t, "passed"]
        : e.decision === "changes_requested" ? [(e.reviewer || "A reviewer") + " asked for changes on " + t, "failed"]
          : ["Review of " + t + ": " + label(String(e.decision || "no decision")), "attention"];
      case "merge": return ["Work from " + (e.worker || "a worker") + " was merged", "neutral"];
      default: return [label(String(e.event || "event")) + (e.task ? " · " + e.task : ""), "neutral"];
    }
  }
  // The closed drawers say whether they are worth opening.
  function setDrawerCount(id, value, tone) {
    const el = document.getElementById(id);
    el.textContent = value;
    el.dataset.tone = tone || "";
  }

  // Tools and limits: what is never observed is said once; below it only
  // what actually happened, one row each: a missing or switched-off tool,
  // or a task with failed attempts and the state of its loop brake.
  function toolRow(badge, name, detail, pill, tone) {
    const row = text("div", "", "tool-row");
    row.dataset.tone = tone || "";
    row.append(badge || text("span", ""), text("strong", name, "tool-name"), text("p", detail, "tool-detail"), text("span", pill, "tool-pill"));
    return row;
  }
  function renderTools(data) {
    const box = document.getElementById("limits");
    box.replaceChildren();
    box.append(text("p", data.agents.length
      ? "Tool activity does not check sign-in or remaining allowance. Cached observations appear in AI agents & limits."
      : "No tool observations recorded. Authentication and capacity remain unknown.", "drawer-note"));
    const missing = data.agents.filter((a) => a.binary && a.binary.present === false);
    for (const a of missing) box.append(toolRow(agentBadge(a.name), a.name, "Its command-line tool is not installed.", "Missing", "failed"));
    const off = data.agents.filter((a) => a.bench.off || a.bench.operator_retry_at !== null);
    for (const a of off) {
      const at = a.bench.operator_retry_at;
      const detail = at === null ? "Switched off by the operator."
        : "Operator retry " + (typeof at === "number" ? new Date(at * 1000).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : String(at)) + "; not a provider reset.";
      box.append(toolRow(agentBadge(a.name), a.name, detail, a.bench.off ? "Off" : "Retry set", "attention"));
    }
    // a task name shown with a lab logo only when exactly one worker has it
    const workersOf = new Map();
    for (const r of data.results || []) workersOf.set(r.task, (workersOf.get(r.task) || new Set()).add(r.worker));
    const troubled = data.retries.filter((retry) => retry.failed_attempts > 0 || retry.blocked || retry.retry_granted);
    for (const retry of troubled) {
      const owners = workersOf.get(retry.task);
      const n = retry.failed_attempts, worker = owners && owners.size === 1 ? [...owners][0] : "";
      box.append(toolRow(worker ? agentBadge(worker) : null, retry.task, n + " failed " + (n === 1 ? "attempt" : "attempts"),
        retry.blocked ? "Blocked" : retry.retry_granted ? "Retry granted" : "Brake clear",
        retry.blocked ? "failed" : retry.retry_granted ? "attention" : ""));
    }
    if (data.agents.length && !missing.length && !off.length && !troubled.length)
      box.append(text("p", "All clear: every tool is installed and on, and no task has failed attempts.", "small"));
    const parts = [];
    if (missing.length) parts.push(missing.length + " missing");
    if (off.length) parts.push(off.length + " off");
    const blocked = troubled.filter((r) => r.blocked).length;
    if (blocked) parts.push(blocked + " blocked");
    const attempts = troubled.reduce((sum, r) => sum + r.failed_attempts, 0);
    if (attempts) parts.push(attempts + " failed " + (attempts === 1 ? "attempt" : "attempts"));
    setDrawerCount("limits-count", parts.length ? parts.join(" · ") : data.agents.length ? "All clear" : "", parts.length ? "attention" : "");
  }

  // Activity log: one row per task run instead of one per event, newest
  // first and read left to right ("T7-glm started 01:07 · ran 16s ·
  // checks 1/1 · approved by qwen · merged"). Warnings stay pinned above.
  const LOG_VISIBLE = 8;
  let logShowAll = false;
  const clock = (at) => new Date(at).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
  function stepText(e) {
    const n = (v) => (typeof v === "number" ? v : "?");
    const at = Date.parse(e.ts);
    switch (e.event) {
      case "run_start": return "started" + (Number.isFinite(at) ? " " + clock(at) : "");
      case "run": return e.exit === 0 ? "ran" + (typeof e.duration_s === "number" ? " " + span(e.duration_s) : " to the end")
        : "ended with exit " + n(e.exit) + (e.wall ? " (time limit)" : "");
      case "verify": {
        const run = n(e.validate_run), failed = n(e.validate_failed);
        const scope = e.scope && e.scope !== "OK" ? " (scope " + label(String(e.scope)).toLowerCase() + ")" : "";
        return (e.verdict === "PASS" ? "checks " + run + "/" + run : e.verdict === "FAIL" ? "failed " + failed + " of " + run + " checks"
          : "checks " + label(String(e.verdict || "unknown")).toLowerCase()) + scope;
      }
      case "review": return e.decision === "approved" ? "approved by " + (e.reviewer || "a reviewer")
        : e.decision === "changes_requested" ? "changes asked by " + (e.reviewer || "a reviewer")
          : "review " + label(String(e.decision || "no decision")).toLowerCase();
      case "merge": return "merged";
      default: return label(String(e.event || "event")).toLowerCase();
    }
  }
  function renderTimeline(data) {
    const box = document.getElementById("events");
    box.replaceChildren();
    const warnings = data.warnings || [];
    for (const warning of warnings) {
      const row = text("div", "", "timeline-row timeline-warning");
      row.append(text("span", "Warning", "timeline-time"), text("p", String(warning), "timeline-text"));
      box.append(row);
    }
    // Oldest first, so each run collects its events in order. A row is one
    // run of one task on one worker: a start, or a second run end, opens a
    // new row, so a later result never covers an earlier one. A merge takes
    // the worker's whole branch, so it is a row of its own.
    const events = (data.recent_events || []).slice().sort((a, b) => (Date.parse(a.ts) || 0) - (Date.parse(b.ts) || 0));
    const runs = [], open = new Map();
    for (const e of events) {
      const key = JSON.stringify([e.worker || "", e.task || ""]);
      let run = e.task && e.event !== "run_start" && e.event !== "merge" ? open.get(key) : null;
      if (run && e.event === "run" && run.events.some((x) => x.event === "run")) run = null;
      if (!run) {
        run = { task: e.task || "", worker: e.worker || "", events: [], at: 0 };
        runs.push(run);
        if (e.task && e.event !== "merge") open.set(key, run);
      }
      run.events.push(e);
      run.at = Math.max(run.at, Date.parse(e.ts) || 0);
    }
    for (const run of runs) {
      // the row's color is the latest event that decided something
      const tones = run.events.map((e) => eventLine(e)[1]).filter((t) => t !== "neutral");
      run.tone = tones.length ? tones[tones.length - 1] : "neutral";
    }
    runs.sort((a, b) => b.at - a.at);
    // the newest few, plus every failed run: a failure is never folded away
    const shown = logShowAll ? runs : runs.filter((run, i) => i < LOG_VISIBLE || run.tone === "failed");
    let day = "";
    for (const run of shown) {
      const last = run.events[run.events.length - 1];
      const at = Date.parse(last.ts);
      const thisDay = Number.isFinite(at) ? new Date(at).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" }) : "Unknown day";
      if (thisDay !== day) { day = thisDay; box.append(text("p", day, "timeline-day")); }
      const row = text("div", "", "timeline-row");
      row.dataset.tone = run.tone;
      const when = text("time", Number.isFinite(at) ? clock(at) : "--:--", "timeline-time");
      when.dateTime = last.ts || "";
      when.title = exactTime(last.ts);
      const line = text("p", "", "timeline-text");
      const merge = run.events.length === 1 && run.events[0].event === "merge";
      line.append(text("strong", merge ? (run.worker || "A worker") + "'s branch" : run.task || run.worker || "Unknown task", "timeline-task"),
        document.createTextNode(run.events.map(stepText).join(" · ")));
      row.append(when, run.worker ? agentBadge(run.worker) : text("span", ""), line);
      box.append(row);
    }
    if (shown.length < runs.length || logShowAll && runs.length > LOG_VISIBLE) {
      const more = text("button", logShowAll ? "Show the newest " + LOG_VISIBLE : "Show all " + runs.length + " rows", "log-more");
      more.type = "button";
      more.addEventListener("click", () => { logShowAll = !logShowAll; renderTimeline(data); });
      box.append(more);
    }
    if (!events.length && !warnings.length) box.append(text("p", "No recorded events yet.", "small"));
    const parts = [];
    if (runs.length) parts.push(runs.length + (runs.length === 1 ? " row" : " rows"));
    const failedRuns = runs.filter((run) => run.tone === "failed").length;
    if (failedRuns) parts.push(failedRuns + " failed");
    if (warnings.length) parts.push(warnings.length + (warnings.length === 1 ? " warning" : " warnings"));
    setDrawerCount("events-count", parts.join(" · "), warnings.length || failedRuns ? "attention" : "");
  }

  const GROUPS = [["attention", "Needs you"], ["active", "Running"], ["finished", "Finished"]];
  function renderSummary(tally) {
    for (const button of document.querySelectorAll("#task-summary button")) {
      const state = button.dataset.state;
      setText(button.querySelector(".summary-count"), String(tally[state]));
      button.setAttribute("aria-pressed", mapStateFilter === state ? "true" : "false");
    }
  }
  // The list is rebuilt only when what it shows changes (the relative times
  // count as a change once a minute), and a reader's open "Technical details"
  // stay open across a rebuild, so polling never closes what someone opened.
  let taskListSignature = "";
  function renderTaskList(data, pageTasks, categories) {
    const tasks = document.getElementById("tasks");
    const minute = Math.floor((Date.parse(data.observed_at) || 0) / 60000);
    const signature = JSON.stringify([minute, data.results.length, pageTasks.map((r) => [r, categories.get(r).category, isLatestForWorker(data, r)])]);
    if (signature === taskListSignature && tasks.childElementCount) return;
    taskListSignature = signature;
    const rowKey = (row) => JSON.stringify([row.dataset.worker, row.dataset.task]);
    const open = new Set([...tasks.querySelectorAll(".task-row")].filter((row) => row.querySelector(".task-tech[open]")).map(rowKey));
    tasks.replaceChildren();
    for (const [category, title] of GROUPS) {
      const records = pageTasks.filter((r) => categories.get(r).category === category);
      if (!records.length) continue;
      // Newest first; in Needs you, failures come before work that is only
      // waiting for its next step (a review, a check), so they never get buried.
      const failedFirst = (r) => (category === "attention" && taskSignal(r, categories.get(r)) === "failed" ? 0 : 1);
      records.sort((a, b) => failedFirst(a) - failedFirst(b) || (Date.parse(b.recorded_at) || 0) - (Date.parse(a.recorded_at) || 0));
      const group = text("section", "", "task-group");
      group.dataset.group = category;
      const heading = text("h3", "", "task-group-title");
      heading.append(text("span", title), text("span", String(records.length), "task-group-count"));
      group.append(heading);
      for (const r of records) {
        const verdict = categories.get(r);
        const state = humanState(r, verdict, isLatestForWorker(data, r));
        const row = text("article", "", "row task-row");
        row.dataset.worker = r.worker;
        row.dataset.task = r.task;
        row.dataset.signal = taskSignal(r, verdict);
        const main = text("div", "", "task-main");
        // The logo alone identifies the agent here; the name stays available
        // to screen readers and as the hover title.
        const badge = agentBadge(r.worker);
        badge.classList.add("logo-only");
        badge.title = r.worker;
        main.append(badge, text("strong", r.task, "task-name"), text("p", state.sentence, "task-sentence"));
        const status = text("div", "", "task-status");
        const pill = text("span", state.label, "state-pill");
        const when = text("time", ago(r.recorded_at, data.observed_at), "task-when");
        when.dateTime = r.recorded_at || "";
        when.title = "Recorded " + exactTime(r.recorded_at);
        status.append(pill, when);
        const tech = document.createElement("details");
        tech.className = "task-tech";
        tech.append(text("summary", "Technical details"));
        for (const line of technicalLines(r)) tech.append(text("p", line));
        row.append(main, trackElement(r), status, nextStep(state.next), tech);
        group.append(row);
      }
      tasks.append(group);
    }
    if (!data.results.length) tasks.append(text("p", "No structured task evidence yet.", "small"));
    for (const row of tasks.querySelectorAll(".task-row")) if (open.has(rowKey(row))) row.querySelector(".task-tech").open = true;
  }

  // JSON arrays cannot collide for different tuples, whatever the names hold.
  function taskKey(worker, task) { return JSON.stringify(["task", worker, task]); }
  function workerKey(worker) { return JSON.stringify(["worker", worker]); }
  const HUB_KEY = JSON.stringify(["hub"]);

  function sectionState(r, name) {
    const section = r && r[name];
    return section && typeof section.state === "string" ? section.state : "unavailable";
  }

  // Category comes from an explicit kind, else from whole task-name tokens
  // (never substrings: SIMPLIFY and NETWORK are Other). Review and check
  // conventions outrank incidental fix/build words in the same name.
  const KIND_NAMES = { implementation: "Implementation", review: "Review", check: "Checks", checks: "Checks" };
  const REVIEW_TOKENS = new Set(["review", "reviews", "reviewer", "audit"]);
  const CHECK_TOKENS = new Set(["check", "checks", "test", "tests", "lint", "verify", "validation", "validate", "gate"]);
  const IMPLEMENTATION_TOKENS = new Set(["impl", "implement", "implementation", "feature", "feat", "fix", "bugfix", "build"]);
  function taskKind(r) {
    const kind = typeof r.kind === "string" ? r.kind.toLowerCase() : "";
    if (Object.prototype.hasOwnProperty.call(KIND_NAMES, kind)) return KIND_NAMES[kind];
    const tokens = String(r.task || "").toLowerCase().split(/[^a-z0-9]+/);
    if (tokens.some((t) => REVIEW_TOKENS.has(t))) return "Review";
    if (tokens.some((t) => CHECK_TOKENS.has(t))) return "Checks";
    if (tokens.some((t) => IMPLEMENTATION_TOKENS.has(t))) return "Implementation";
    return "Other";
  }

  // "" is Current work (active + attention); "all" includes every recorded
  // task; a direct Finished choice shows finished history without a toggle.
  function stateMatches(category) {
    if (mapStateFilter === "all") return true;
    if (!mapStateFilter) return category !== "finished";
    return category === mapStateFilter;
  }

  function getFilteredTasks(data) {
    const filtered = [];
    const categories = new Map();
    const tally = { active: 0, attention: 0, finished: 0 };
    for (const r of data.results) {
      const verdict = classify(r);
      categories.set(r, verdict);
      tally[verdict.category]++;
      if (mapWorkerFilter && r.worker !== mapWorkerFilter) continue;
      if (!stateMatches(verdict.category)) continue;
      if (mapCategoryFilter && taskKind(r) !== mapCategoryFilter) continue;
      const stateStr = (sectionState(r, "process") + " " + r.activity + " " + sectionState(r, "validation") + " " + sectionState(r, "review") + " " + verdict.category + " " + taskKind(r)).toLowerCase();
      const searchMatch = !mapSearchQuery ||
          r.worker.toLowerCase().includes(mapSearchQuery) ||
          r.task.toLowerCase().includes(mapSearchQuery) ||
          stateStr.includes(mapSearchQuery);
      if (searchMatch) filtered.push(r);
    }
    return { filtered, categories, tally };
  }

  // Process success is not acceptance. Only fully passed and approved records
  // collapse into history; every failed, unknown, incomplete, stale or
  // unreviewed record stays visible as needing attention.
  function classify(r) {
    const process = sectionState(r, "process");
    const validation = sectionState(r, "validation");
    const review = sectionState(r, "review");
    const reasons = [];
    if (process === "running") {
      if (r.activity === "running_recorded") return { category: "active", reasons: ["process running"] };
      reasons.push("process running without a held worker lock; completion unknown");
    } else if (process !== "succeeded") {
      reasons.push("process " + label(process));
    }
    if (r.activity === "completion_unknown" && process !== "running") reasons.push("completion unknown");
    if (validation !== "passed") reasons.push("validation " + label(validation));
    if (review !== "approved") reasons.push("review " + label(review));
    if (r.stale === true) reasons.push("recorded evidence stale");
    return reasons.length ? { category: "attention", reasons } : { category: "finished", reasons: [] };
  }
  const CATEGORY_TEXT = {
    active: "Active",
    attention: "Needs attention",
    finished: "Finished (checks passed and review approved; not your acceptance)",
  };

  function taskSignal(r, verdict) {
    if (verdict.category === "active") return "active";
    if (["process", "validation", "review"].some(name => sectionState(r, name) === "failed")) return "failed";
    return verdict.category === "finished" ? "passed" : "attention";
  }
  function summarySignal(records, categories) {
    // A grouping node is not a process. Old failures must not masquerade as
    // project health or obscure a worker's current activity.
    return records.some(r => categories.get(r).category === "active") ? "active" : "none";
  }
  function historySummary(records, categories) {
    const active = records.filter(r => categories.get(r).category === "active").length;
    const failed = records.filter(r => ["process", "validation", "review"].some(name => sectionState(r, name) === "failed")).length;
    return active + " active " + (active === 1 ? "task" : "tasks") + "; "
      + failed + " recorded task " + (failed === 1 ? "failure" : "failures")
      + " in history. This is an activity summary, not project health.";
  }
  function mapLayer(svg, name) {
    let layer = svg.querySelector(':scope > g[data-layer="' + name + '"]');
    if (!layer) {
      layer = document.createElementNS(SVG_NS, "g");
      layer.dataset.layer = name;
      if (name === "links") svg.insertBefore(layer, svg.firstChild);
      else svg.appendChild(layer);
    }
    return layer;
  }

  function applyMapPresentation() {
    const svg = document.getElementById("work-map");
    if (!svg) return;
    const { width, height } = svg.getBoundingClientRect();
    // Hidden List view must not replace the last usable camera dimensions.
    if (!width || !height) return;
    if (mapFitView) {
      mapCamera.x = 0;
      mapCamera.y = 0;
      mapCamera.scale = Math.max(MIN_MAP_SCALE, Math.min(1, width / (2 * mapBounds.x), height / (2 * mapBounds.y)));
    }
    const w = width / mapCamera.scale, h = height / mapCamera.scale;
    svg.setAttribute("viewBox", [mapCamera.x - w / 2, mapCamera.y - h / 2, w, h].join(" "));
    // The dot grid lives in map space, so it pans and zooms with the nodes;
    // far out, every other dot drops away so it never turns dense.
    let tile = MAP_GRID * mapCamera.scale;
    while (tile < 9) tile *= 2;
    svg.parentElement.style.backgroundSize = tile + "px " + tile + "px";
    svg.parentElement.style.backgroundPosition = (width / 2 - mapCamera.x * mapCamera.scale) + "px " + (height / 2 - mapCamera.y * mapCamera.scale) + "px";
    svg.dataset.view = mapFitView ? "fit" : "actual";
    svg.dataset.cameraX = String(mapCamera.x);
    svg.dataset.cameraY = String(mapCamera.y);
    svg.dataset.scale = String(mapCamera.scale);
    document.getElementById("map-fit").setAttribute("aria-pressed", String(mapFitView));
    setText(document.getElementById("map-zoom-level"), Math.round(mapCamera.scale * 100) + "%");
    document.getElementById("map-zoom-in").disabled = mapCamera.scale >= MAX_MAP_SCALE;
    document.getElementById("map-zoom-out").disabled = mapCamera.scale <= MIN_MAP_SCALE;
  }

  function resetMapCamera() {
    mapFitView = false;
    Object.assign(mapCamera, { x: 0, y: 0, scale: 1 });
    applyMapPresentation();
  }

  function zoomMap(factor, pointer) {
    const rect = document.getElementById("work-map").getBoundingClientRect();
    const scale = Math.max(MIN_MAP_SCALE, Math.min(MAX_MAP_SCALE, mapCamera.scale * factor));
    if (pointer && rect.width && rect.height) {
      // Keep the world point under the pointer in the same screen position.
      const dx = pointer.clientX - rect.left - rect.width / 2;
      const dy = pointer.clientY - rect.top - rect.height / 2;
      mapCamera.x += dx / mapCamera.scale - dx / scale;
      mapCamera.y += dy / mapCamera.scale - dy / scale;
    }
    mapCamera.scale = scale;
    mapFitView = false;
    applyMapPresentation();
  }

  function setupMapGestures() {
    const svg = document.getElementById("work-map");
    svg.addEventListener("wheel", (event) => {
      // Wheel zoom belongs only to the map; the rest of the page scrolls normally.
      event.preventDefault();
      if (!mapDrag && event.deltaY) zoomMap(event.deltaY < 0 ? 1.25 : 1 / 1.25, event);
    }, { passive: false });
    svg.addEventListener("keydown", (event) => {
      const step = 80 / mapCamera.scale;
      if (event.key === "+" || event.key === "=") zoomMap(1.25);
      else if (event.key === "-") zoomMap(1 / 1.25);
      else if (event.key === "0") { mapFitView = true; applyMapPresentation(); }
      else if (event.key === "Home") resetMapCamera();
      else if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) {
        if (event.key === "ArrowLeft") mapCamera.x -= step;
        if (event.key === "ArrowRight") mapCamera.x += step;
        if (event.key === "ArrowUp") mapCamera.y -= step;
        if (event.key === "ArrowDown") mapCamera.y += step;
        mapFitView = false;
        applyMapPresentation();
      } else return;
      event.preventDefault();
    });
    svg.addEventListener("pointerdown", (event) => {
      if (!event.isPrimary || ![0, 1].includes(event.button) || mapDrag) return;
      if (event.button === 1) event.preventDefault(); // Suppress browser autoscroll.
      suppressMapClick = false;
      mapDrag = { id: event.pointerId, button: event.button, clientX: event.clientX, clientY: event.clientY,
        x: mapCamera.x, y: mapCamera.y, scale: mapCamera.scale, moved: false };
    });
    svg.addEventListener("pointermove", (event) => {
      if (!mapDrag || event.pointerId !== mapDrag.id) return;
      const dx = event.clientX - mapDrag.clientX, dy = event.clientY - mapDrag.clientY;
      if (!mapDrag.moved && Math.hypot(dx, dy) < 4) return;
      if (!mapDrag.moved) {
        mapDrag.moved = true;
        svg.setPointerCapture(event.pointerId);
        svg.classList.add("is-panning");
      }
      mapFitView = false;
      mapCamera.x = mapDrag.x - dx / mapDrag.scale;
      mapCamera.y = mapDrag.y - dy / mapDrag.scale;
      suppressMapClick = mapDrag.button === 0;
      applyMapPresentation();
    });
    const endDrag = (event) => {
      if (!mapDrag || event.pointerId !== mapDrag.id) return;
      mapDrag = null;
      svg.classList.remove("is-panning");
      if (svg.hasPointerCapture(event.pointerId)) svg.releasePointerCapture(event.pointerId);
    };
    svg.addEventListener("pointerup", endDrag);
    svg.addEventListener("pointercancel", endDrag);
    svg.addEventListener("lostpointercapture", endDrag);
    svg.addEventListener("auxclick", event => {
      if (event.button === 1) event.preventDefault();
    });
    svg.addEventListener("pointerleave", (event) => {
      if (mapDrag && !mapDrag.moved) endDrag(event);
    });
    svg.addEventListener("click", (event) => {
      if (!suppressMapClick) return;
      suppressMapClick = false;
      event.preventDefault();
      event.stopPropagation();
    }, true);
  }

  function revealMapNode(g) {
    const svg = document.getElementById("work-map");
    const view = svg.viewBox.baseVal;
    const { e: x, f: y } = g.transform.baseVal.getItem(0).matrix;
    // Keyboard focus can reach a node beyond the current camera. Reveal its
    // centre without zooming or changing the selected task.
    if (x >= view.x + NODE_WIDTH / 2 + 5 && x <= view.x + view.width - NODE_WIDTH / 2 - 5 &&
        y >= view.y + NODE_HEIGHT / 2 + 4 && y <= view.y + view.height - NODE_HEIGHT / 2 - 4) return;
    mapFitView = false;
    mapCamera.x = x;
    mapCamera.y = y;
    applyMapPresentation();
  }

  function optionLogo(worker) {
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("class", "option-logo");
    const mark = agentIdentity(worker).mark;
    const paths = mark && AI_MARKS[mark];
    if (paths) {
      for (const d of paths) {
        const path = document.createElementNS(SVG_NS, "path");
        path.setAttribute("d", d);
        svg.appendChild(path);
      }
    } else {
      const dot = document.createElementNS(SVG_NS, "rect");
      for (const [k, v] of [["x", "7"], ["y", "7"], ["width", "10"], ["height", "10"], ["rx", "2.5"]]) dot.setAttribute(k, v);
      svg.appendChild(dot);
    }
    return svg;
  }

  function syncWorkerOptions(names) {
    const select = document.getElementById("map-worker-filter");
    const wanted = Array.from(new Set(names)).sort();
    const desired = [{ value: "", text: "All Workers" }].concat(wanted.map((w) => ({ value: w, text: w })));
    if (mapWorkerFilter && !wanted.includes(mapWorkerFilter))
      desired.push({ value: mapWorkerFilter, text: mapWorkerFilter + " (not in current observation)" });
    const existing = new Map(Array.from(select.options).map((option) => [option.value, option]));
    desired.forEach((want, index) => {
      let option = existing.get(want.value);
      existing.delete(want.value);
      if (!option) {
        option = document.createElement("option");
        option.value = want.value;
        // Each worker shows its lab's logo where the browser can draw rich
        // options; elsewhere the option is just its name, as before.
        if (want.value) option.append(optionLogo(want.value), text("span", "", "option-label"));
      }
      setText(option.querySelector(".option-label") || option, want.text);
      if (want.value) option.dataset.agentMark = agentIdentity(want.value).mark;
      if (select.options[index] !== option) select.insertBefore(option, select.options[index] || null);
    });
    for (const option of existing.values()) option.remove();
    if (select.value !== mapWorkerFilter) select.value = mapWorkerFilter;
    updateWorkerLogo();
  }
  // The closed worker filter shows the chosen worker's logo beside its name.
  function updateWorkerLogo() {
    const slot = document.getElementById("map-worker-logo");
    if (!slot) return;
    const worker = mapWorkerFilter;
    if (slot.dataset.worker === worker) return;
    slot.dataset.worker = worker;
    slot.replaceChildren(...(worker ? [optionLogo(worker)] : []));
    slot.dataset.agentMark = worker ? agentIdentity(worker).mark : "";
    slot.parentElement.classList.toggle("has-logo", !!worker);
  }

  function syncCategoryOptions(categoriesList) {
    const select = document.getElementById("map-category-filter");
    const wanted = Array.from(new Set(categoriesList)).sort();
    const desired = [{ value: "", text: "All Categories" }].concat(wanted.map((c) => ({ value: c, text: c })));
    if (mapCategoryFilter && !wanted.includes(mapCategoryFilter))
      desired.push({ value: mapCategoryFilter, text: mapCategoryFilter + " (not in current observation)" });
    const existing = new Map(Array.from(select.options).map((option) => [option.value, option]));
    desired.forEach((want, index) => {
      let option = existing.get(want.value);
      existing.delete(want.value);
      if (!option) {
        option = document.createElement("option");
        option.value = want.value;
      }
      setText(option, want.text);
      if (select.options[index] !== option) select.insertBefore(option, select.options[index] || null);
    });
    for (const option of existing.values()) option.remove();
    if (select.value !== mapCategoryFilter) select.value = mapCategoryFilter;
  }

  /* Brand paths: Lobe Icons @ c385b2b8d1f9e19aa86e628d4e23c91ee1111a47.
   * MIT License
   *
   * Copyright (c) 2023 LobeHub
   *
   * Permission is hereby granted, free of charge, to any person obtaining a copy
   * of this software and associated documentation files (the "Software"), to deal
   * in the Software without restriction, including without limitation the rights
   * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
   * copies of the Software, and to permit persons to whom the Software is
   * furnished to do so, subject to the following conditions:
   *
   * The above copyright notice and this permission notice shall be included in all
   * copies or substantial portions of the Software.
   *
   * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
   * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
   * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
   * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
   * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
   * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
   * SOFTWARE.
   */
  const AI_MARKS = {
    "openai": [
      "M9.205 8.658v-2.26c0-.19.072-.333.238-.428l4.543-2.616c.619-.357 1.356-.523 2.117-.523 2.854 0 4.662 2.212 4.662 4.566 0 .167 0 .357-.024.547l-4.71-2.759a.797.797 0 00-.856 0l-5.97 3.473zm10.609 8.8V12.06c0-.333-.143-.57-.429-.737l-5.97-3.473 1.95-1.118a.433.433 0 01.476 0l4.543 2.617c1.309.76 2.189 2.378 2.189 3.948 0 1.808-1.07 3.473-2.76 4.163zM7.802 12.703l-1.95-1.142c-.167-.095-.239-.238-.239-.428V5.899c0-2.545 1.95-4.472 4.591-4.472 1 0 1.927.333 2.712.928L8.23 5.067c-.285.166-.428.404-.428.737v6.898zM12 15.128l-2.795-1.57v-3.33L12 8.658l2.795 1.57v3.33L12 15.128zm1.796 7.23c-1 0-1.927-.332-2.712-.927l4.686-2.712c.285-.166.428-.404.428-.737v-6.898l1.974 1.142c.167.095.238.238.238.428v5.233c0 2.545-1.974 4.472-4.614 4.472zm-5.637-5.303l-4.544-2.617c-1.308-.761-2.188-2.378-2.188-3.948A4.482 4.482 0 014.21 6.327v5.423c0 .333.143.571.428.738l5.947 3.449-1.95 1.118a.432.432 0 01-.476 0zm-.262 3.9c-2.688 0-4.662-2.021-4.662-4.519 0-.19.024-.38.047-.57l4.686 2.71c.286.167.571.167.856 0l5.97-3.448v2.26c0 .19-.07.333-.237.428l-4.543 2.616c-.619.357-1.356.523-2.117.523zm5.899 2.83a5.947 5.947 0 005.827-4.756C22.287 18.339 24 15.84 24 13.296c0-1.665-.713-3.282-1.998-4.448.119-.5.19-.999.19-1.498 0-3.401-2.759-5.947-5.946-5.947-.642 0-1.26.095-1.88.31A5.962 5.962 0 0010.205 0a5.947 5.947 0 00-5.827 4.757C1.713 5.447 0 7.945 0 10.49c0 1.666.713 3.283 1.998 4.448-.119.5-.19 1-.19 1.499 0 3.401 2.759 5.946 5.946 5.946.642 0 1.26-.095 1.88-.309a5.96 5.96 0 004.162 1.713z"
    ],
    "claude": [
      "M4.709 15.955l4.72-2.647.08-.23-.08-.128H9.2l-.79-.048-2.698-.073-2.339-.097-2.266-.122-.571-.121L0 11.784l.055-.352.48-.321.686.06 1.52.103 2.278.158 1.652.097 2.449.255h.389l.055-.157-.134-.098-.103-.097-2.358-1.596-2.552-1.688-1.336-.972-.724-.491-.364-.462-.158-1.008.656-.722.881.06.225.061.893.686 1.908 1.476 2.491 1.833.365.304.145-.103.019-.073-.164-.274-1.355-2.446-1.446-2.49-.644-1.032-.17-.619a2.97 2.97 0 01-.104-.729L6.283.134 6.696 0l.996.134.42.364.62 1.414 1.002 2.229 1.555 3.03.456.898.243.832.091.255h.158V9.01l.128-1.706.237-2.095.23-2.695.08-.76.376-.91.747-.492.584.28.48.685-.067.444-.286 1.851-.559 2.903-.364 1.942h.212l.243-.242.985-1.306 1.652-2.064.73-.82.85-.904.547-.431h1.033l.76 1.129-.34 1.166-1.064 1.347-.881 1.142-1.264 1.7-.79 1.36.073.11.188-.02 2.856-.606 1.543-.28 1.841-.315.833.388.091.395-.328.807-1.969.486-2.309.462-3.439.813-.042.03.049.061 1.549.146.662.036h1.622l3.02.225.79.522.474.638-.079.485-1.215.62-1.64-.389-3.829-.91-1.312-.329h-.182v.11l1.093 1.068 2.006 1.81 2.509 2.33.127.578-.322.455-.34-.049-2.205-1.657-.851-.747-1.926-1.62h-.128v.17l.444.649 2.345 3.521.122 1.08-.17.353-.608.213-.668-.122-1.374-1.925-1.415-2.167-1.143-1.943-.14.08-.674 7.254-.316.37-.729.28-.607-.461-.322-.747.322-1.476.389-1.924.315-1.53.286-1.9.17-.632-.012-.042-.14.018-1.434 1.967-2.18 2.945-1.726 1.845-.414.164-.717-.37.067-.662.401-.589 2.388-3.036 1.44-1.882.93-1.086-.006-.158h-.055L4.132 18.56l-1.13.146-.487-.456.061-.746.231-.243 1.908-1.312-.006.006z"
    ],
    "gemini": [
      "M20.616 10.835a14.147 14.147 0 01-4.45-3.001 14.111 14.111 0 01-3.678-6.452.503.503 0 00-.975 0 14.134 14.134 0 01-3.679 6.452 14.155 14.155 0 01-4.45 3.001c-.65.28-1.318.505-2.002.678a.502.502 0 000 .975c.684.172 1.35.397 2.002.677a14.147 14.147 0 014.45 3.001 14.112 14.112 0 013.679 6.453.502.502 0 00.975 0c.172-.685.397-1.351.677-2.003a14.145 14.145 0 013.001-4.45 14.113 14.113 0 016.453-3.678.503.503 0 000-.975 13.245 13.245 0 01-2.003-.678z"
    ],
    "grok": [
      "M9.27 15.29l7.978-5.897c.391-.29.95-.177 1.137.272.98 2.369.542 5.215-1.41 7.169-1.951 1.954-4.667 2.382-7.149 1.406l-2.711 1.257c3.889 2.661 8.611 2.003 11.562-.953 2.341-2.344 3.066-5.539 2.388-8.42l.006.007c-.983-4.232.242-5.924 2.75-9.383.06-.082.12-.164.179-.248l-3.301 3.305v-.01L9.267 15.292M7.623 16.723c-2.792-2.67-2.31-6.801.071-9.184 1.761-1.763 4.647-2.483 7.166-1.425l2.705-1.25a7.808 7.808 0 00-1.829-1A8.975 8.975 0 005.984 5.83c-2.533 2.536-3.33 6.436-1.962 9.764 1.022 2.487-.653 4.246-2.34 6.022-.599.63-1.199 1.259-1.682 1.925l7.62-6.815"
    ],
    "opencode": [
      "M16 6H8v12h8V6zm4 16H4V2h16v20z"
    ],
    "antigravity": [
      "M21.751 22.607c1.34 1.005 3.35.335 1.508-1.508C17.73 15.74 18.904 1 12.037 1 5.17 1 6.342 15.74.815 21.1c-2.01 2.009.167 2.511 1.507 1.506 5.192-3.517 4.857-9.714 9.715-9.714 4.857 0 4.522 6.197 9.714 9.715z"
    ],
    "kimi": [
      "M21.846 0a1.923 1.923 0 110 3.846H20.15a.226.226 0 01-.227-.226V1.923C19.923.861 20.784 0 21.846 0z",
      "M11.065 11.199l7.257-7.2c.137-.136.06-.41-.116-.41H14.3a.164.164 0 00-.117.051l-7.82 7.756c-.122.12-.302.013-.302-.179V3.82c0-.127-.083-.23-.185-.23H3.186c-.103 0-.186.103-.186.23V19.77c0 .128.083.23.186.23h2.69c.103 0 .186-.102.186-.23v-3.25c0-.069.025-.135.069-.178l2.424-2.406a.158.158 0 01.205-.023l6.484 4.772a7.677 7.677 0 003.453 1.283c.108.012.2-.095.2-.23v-3.06c0-.117-.07-.212-.164-.227a5.028 5.028 0 01-2.027-.807l-5.613-4.064c-.117-.078-.132-.279-.028-.381z"
    ],
    "deepseek": [
      "M23.748 4.482c-.254-.124-.364.113-.512.234-.051.039-.094.09-.137.136-.372.397-.806.657-1.373.626-.829-.046-1.537.214-2.163.848-.133-.782-.575-1.248-1.247-1.548-.352-.156-.708-.311-.955-.65-.172-.241-.219-.51-.305-.774-.055-.16-.11-.323-.293-.35-.2-.031-.278.136-.356.276-.313.572-.434 1.202-.422 1.84.027 1.436.633 2.58 1.838 3.393.137.093.172.187.129.323-.082.28-.18.552-.266.833-.055.179-.137.217-.329.14a5.526 5.526 0 01-1.736-1.18c-.857-.828-1.631-1.742-2.597-2.458a11.365 11.365 0 00-.689-.471c-.985-.957.13-1.743.388-1.836.27-.098.093-.432-.779-.428-.872.004-1.67.295-2.687.684a3.055 3.055 0 01-.465.137 9.597 9.597 0 00-2.883-.102c-1.885.21-3.39 1.102-4.497 2.623C.082 8.606-.231 10.684.152 12.85c.403 2.284 1.569 4.175 3.36 5.653 1.858 1.533 3.997 2.284 6.438 2.14 1.482-.085 3.133-.284 4.994-1.86.47.234.962.327 1.78.397.63.059 1.236-.03 1.705-.128.735-.156.684-.837.419-.961-2.155-1.004-1.682-.595-2.113-.926 1.096-1.296 2.746-2.642 3.392-7.003.05-.347.007-.565 0-.845-.004-.17.035-.237.23-.256a4.173 4.173 0 001.545-.475c1.396-.763 1.96-2.015 2.093-3.517.02-.23-.004-.467-.247-.588zM11.581 18c-2.089-1.642-3.102-2.183-3.52-2.16-.392.024-.321.471-.235.763.09.288.207.486.371.739.114.167.192.416-.113.603-.673.416-1.842-.14-1.897-.167-1.361-.802-2.5-1.86-3.301-3.307-.774-1.393-1.224-2.887-1.298-4.482-.02-.386.093-.522.477-.592a4.696 4.696 0 011.529-.039c2.132.312 3.946 1.265 5.468 2.774.868.86 1.525 1.887 2.202 2.891.72 1.066 1.494 2.082 2.48 2.914.348.292.625.514.891.677-.802.09-2.14.11-3.054-.614zm1-6.44a.306.306 0 01.415-.287.302.302 0 01.2.288.306.306 0 01-.31.307.303.303 0 01-.304-.308zm3.11 1.596c-.2.081-.399.151-.59.16a1.245 1.245 0 01-.798-.254c-.274-.23-.47-.358-.552-.758a1.73 1.73 0 01.016-.588c.07-.327-.008-.537-.239-.727-.187-.156-.426-.199-.688-.199a.559.559 0 01-.254-.078c-.11-.054-.2-.19-.114-.358.028-.054.16-.186.192-.21.356-.202.767-.136 1.146.016.352.144.618.408 1.001.782.391.451.462.576.685.914.176.265.336.537.445.848.067.195-.019.354-.25.452z"
    ],
    "zai": [
      "M12.105 2L9.927 4.953H.653L2.83 2h9.276zM23.254 19.048L21.078 22h-9.242l2.174-2.952h9.244zM24 2L9.264 22H0L14.736 2H24z"
    ],
    "qwen": [
      "M12.604 1.34c.393.69.784 1.382 1.174 2.075a.18.18 0 00.157.091h5.552c.174 0 .322.11.446.327l1.454 2.57c.19.337.24.478.024.837-.26.43-.513.864-.76 1.3l-.367.658c-.106.196-.223.28-.04.512l2.652 4.637c.172.301.111.494-.043.77-.437.785-.882 1.564-1.335 2.34-.159.272-.352.375-.68.37-.777-.016-1.552-.01-2.327.016a.099.099 0 00-.081.05 575.097 575.097 0 01-2.705 4.74c-.169.293-.38.363-.725.364-.997.003-2.002.004-3.017.002a.537.537 0 01-.465-.271l-1.335-2.323a.09.09 0 00-.083-.049H4.982c-.285.03-.553-.001-.805-.092l-1.603-2.77a.543.543 0 01-.002-.54l1.207-2.12a.198.198 0 000-.197 550.951 550.951 0 01-1.875-3.272l-.79-1.395c-.16-.31-.173-.496.095-.965.465-.813.927-1.625 1.387-2.436.132-.234.304-.334.584-.335a338.3 338.3 0 012.589-.001.124.124 0 00.107-.063l2.806-4.895a.488.488 0 01.422-.246c.524-.001 1.053 0 1.583-.006L11.704 1c.341-.003.724.032.9.34zm-3.432.403a.06.06 0 00-.052.03L6.254 6.788a.157.157 0 01-.135.078H3.253c-.056 0-.07.025-.041.074l5.81 10.156c.025.042.013.062-.034.063l-2.795.015a.218.218 0 00-.2.116l-1.32 2.31c-.044.078-.021.118.068.118l5.716.008c.046 0 .08.02.104.061l1.403 2.454c.046.081.092.082.139 0l5.006-8.76.783-1.382a.055.055 0 01.096 0l1.424 2.53a.122.122 0 00.107.062l2.763-.02a.04.04 0 00.035-.02.041.041 0 000-.04l-2.9-5.086a.108.108 0 010-.113l.293-.507 1.12-1.977c.024-.041.012-.062-.035-.062H9.2c-.059 0-.073-.026-.043-.077l1.434-2.505a.107.107 0 000-.114L9.225 1.774a.06.06 0 00-.053-.031zm6.29 8.02c.046 0 .058.02.034.06l-.832 1.465-2.613 4.585a.056.056 0 01-.05.029.058.058 0 01-.05-.029L8.498 9.841c-.02-.034-.01-.052.028-.054l.216-.012 6.722-.012z"
    ],
    "minimax": [
      "M16.278 2c1.156 0 2.093.927 2.093 2.07v12.501a.74.74 0 00.744.709.74.74 0 00.743-.709V9.099a2.06 2.06 0 012.071-2.049A2.06 2.06 0 0124 9.1v6.561a.649.649 0 01-.652.645.649.649 0 01-.653-.645V9.1a.762.762 0 00-.766-.758.762.762 0 00-.766.758v7.472a2.037 2.037 0 01-2.048 2.026 2.037 2.037 0 01-2.048-2.026v-12.5a.785.785 0 00-.788-.753.785.785 0 00-.789.752l-.001 15.904A2.037 2.037 0 0113.441 22a2.037 2.037 0 01-2.048-2.026V18.04c0-.356.292-.645.652-.645.36 0 .652.289.652.645v1.934c0 .263.142.506.372.638.23.131.514.131.744 0a.734.734 0 00.372-.638V4.07c0-1.143.937-2.07 2.093-2.07zm-5.674 0c1.156 0 2.093.927 2.093 2.07v11.523a.648.648 0 01-.652.645.648.648 0 01-.652-.645V4.07a.785.785 0 00-.789-.78.785.785 0 00-.789.78v14.013a2.06 2.06 0 01-2.07 2.048 2.06 2.06 0 01-2.071-2.048V9.1a.762.762 0 00-.766-.758.762.762 0 00-.766.758v3.8a2.06 2.06 0 01-2.071 2.049A2.06 2.06 0 010 12.9v-1.378c0-.357.292-.646.652-.646.36 0 .653.29.653.646V12.9c0 .418.343.757.766.757s.766-.339.766-.757V9.099a2.06 2.06 0 012.07-2.048 2.06 2.06 0 012.071 2.048v8.984c0 .419.343.758.767.758.423 0 .766-.339.766-.758V4.07c0-1.143.937-2.07 2.093-2.07z"
    ]
  };

  const AI_ROUTES = {
    codex: ["Codex", "openai"], openai: ["OpenAI", "openai"],
    claude: ["Claude", "claude"], grok: ["Grok", "grok"],
    antigravity: ["Antigravity", "antigravity"], gemini: ["Gemini", "gemini"],
    opencode: ["OpenCode", "opencode"], kimi: ["Kimi", "kimi"],
    deepseek: ["DeepSeek", "deepseek"], glm: ["GLM", "zai"],
    qwen: ["Qwen", "qwen"], minimax: ["MiniMax", "minimax"],
    mimo: ["MiMo", ""], fledge: ["Fledge", ""], muse: ["Muse", ""],
  };

  function agentIdentity(worker) {
    if (worker === undefined) return { name: "Unio", mark: "", initials: "U" };
    const route = worker.split("-")[0].toLowerCase();
    const known = Object.hasOwn(AI_ROUTES, route) ? AI_ROUTES[route] : null;
    const name = known ? known[0] : route || "Unknown";
    return { name, mark: known ? known[1] : "", initials: name.substring(0, 2).toUpperCase() };
  }

  function updateNodeIdentity(g, worker) {
    const identity = agentIdentity(worker);
    const logo = g.querySelector(".node-logo");
    if (g.dataset.agentMark !== identity.mark || g.dataset.agentName !== identity.name) {
      const paths = identity.mark && AI_MARKS[identity.mark];
      logo.replaceChildren();
      if (paths) {
        for (const d of paths) {
          const path = document.createElementNS(SVG_NS, "path");
          path.setAttribute("d", d);
          logo.appendChild(path);
        }
      } else {
        const initials = document.createElementNS(SVG_NS, "text");
        initials.setAttribute("x", "12"); initials.setAttribute("y", "17");
        initials.setAttribute("text-anchor", "middle"); initials.setAttribute("font-size", "13");
        initials.textContent = identity.initials;
        logo.appendChild(initials);
      }
      g.dataset.agentMark = identity.mark;
      g.dataset.agentName = identity.name;
    }
    setText(g.querySelector(".node-agent"), identity.name.length > 12 ? identity.name.substring(0, 10) + "…" : identity.name);
  }

  function recordedSubtitle(r) {
    const raw = r && r.recorded_at;
    const date = typeof raw === "string" && /^\d{4}-\d{2}-\d{2}T/.test(raw) ? new Date(raw) : null;
    if (!date || !Number.isFinite(date.getTime())) return "Recorded time unknown";
    return "Recorded " + new Intl.DateTimeFormat("en", {
      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false,
    }).format(date);
  }

  function latestTask(records, categories) {
    return records.reduce((best, r) => {
      if (!best || categories.get(r).category === "active") return r;
      if (categories.get(best).category === "active") return best;
      const time = value => typeof value.recorded_at === "string" ? Date.parse(value.recorded_at) || 0 : 0;
      return time(r) > time(best) ? r : best;
    }, null);
  }

  function setNodeTitle(element, value) {
    if (element.dataset.fullTitle === value) return;
    element.dataset.fullTitle = value;
    let split = value.length > 23 ? value.lastIndexOf("-", 22) + 1 : value.length;
    if (split < 10) split = Math.min(23, value.length);
    const lines = [value.substring(0, split)];
    if (split < value.length) {
      const rest = value.substring(split);
      lines.push(rest.length > 23 ? rest.substring(0, 22) + "…" : rest);
    }
    element.replaceChildren(...lines.map((line, i) => {
      const span = document.createElementNS(SVG_NS, "tspan");
      span.setAttribute("x", "-48"); span.setAttribute("y", String((lines.length === 1 ? -6 : -18) + i * 16));
      span.textContent = line;
      return span;
    }));
  }

  function createNodeGroup() {
    const g = document.createElementNS(SVG_NS, "g");
    const rect = document.createElementNS(SVG_NS, "rect");
    const signal = document.createElementNS(SVG_NS, "line");
    signal.setAttribute("class", "node-status");
    signal.setAttribute("x1", "118");
    signal.setAttribute("x2", "118");
    signal.setAttribute("y1", "-33");
    signal.setAttribute("y2", "33");
    signal.setAttribute("vector-effect", "non-scaling-stroke");
    signal.setAttribute("aria-hidden", "true");
    const title = document.createElementNS(SVG_NS, "title");
    const textLabel = document.createElementNS(SVG_NS, "text");
    const textState = document.createElementNS(SVG_NS, "text");
    const agent = document.createElementNS(SVG_NS, "text");
    agent.setAttribute("class", "node-agent");
    agent.setAttribute("x", "-90"); agent.setAttribute("y", "25");
    agent.setAttribute("text-anchor", "middle"); agent.setAttribute("font-size", "8.5px");
    const logo = document.createElementNS(SVG_NS, "svg");
    logo.setAttribute("class", "node-logo"); logo.setAttribute("viewBox", "0 0 24 24");
    logo.setAttribute("x", "-106"); logo.setAttribute("y", "-27");
    logo.setAttribute("width", "32"); logo.setAttribute("height", "32");
    logo.setAttribute("aria-hidden", "true");
    const divider = document.createElementNS(SVG_NS, "line");
    divider.setAttribute("class", "node-divider");
    divider.setAttribute("x1", "-60"); divider.setAttribute("x2", "-60");
    divider.setAttribute("y1", "-32"); divider.setAttribute("y2", "32");
    textLabel.setAttribute("class", "node-label");
    textState.setAttribute("class", "node-state");
    rect.setAttribute("x", -NODE_WIDTH / 2);
    rect.setAttribute("y", -NODE_HEIGHT / 2);
    rect.setAttribute("width", NODE_WIDTH);
    rect.setAttribute("height", NODE_HEIGHT);
    rect.setAttribute("rx", 5);
    rect.setAttribute("fill", "var(--paper)");
    for (const node of [textLabel, textState]) {
      node.setAttribute("text-anchor", "start");
      node.setAttribute("x", "-48");
      node.style.pointerEvents = "none";
    }
    textLabel.setAttribute("y", "-3");
    textLabel.setAttribute("fill", "var(--text-main)");
    textLabel.setAttribute("font-size", "12px");
    textState.setAttribute("y", "24");
    textState.setAttribute("fill", "var(--muted)");
    textState.setAttribute("font-size", "10px");
    g.append(rect, divider, logo, agent, title, textLabel, textState, signal);
    g.setAttribute("role", "button");
    g.setAttribute("tabindex", "0");
    g.style.cursor = "pointer";
    // Handlers read the group's current dataset, never a captured record.
    g.addEventListener("click", () => selectNode(g));
    g.addEventListener("focus", () => revealMapNode(g));
    g.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        selectNode(g);
      }
    });
    return g;
  }

  function selectNode(g) {
    if (!lastData || !g.isConnected) return;
    selected = {
      key: g.dataset.nodeKey,
      kind: g.dataset.kind,
      worker: g.dataset.worker,
      task: g.dataset.task,
    };
    render(lastData);
  }

  function clearSelection() {
    selected = null;
    clearDetails();
    const svg = document.getElementById("work-map");
    if (svg) svg.focus({ preventScroll: true });
    if (lastData) render(lastData);
  }

  // Order children without moving the focused group, so focus survives.
  function orderGroups(layer, ordered) {
    const current = Array.from(layer.children);
    if (current.length === ordered.length && current.every((g, i) => g === ordered[i])) return;
    const active = document.activeElement;
    const anchorIndex = ordered.indexOf(active);
    if (anchorIndex < 0) {
      for (const g of ordered) layer.appendChild(g);
      return;
    }
    const anchor = ordered[anchorIndex];
    for (let i = 0; i < anchorIndex; i++) layer.insertBefore(ordered[i], anchor);
    let previous = anchor;
    for (let i = anchorIndex + 1; i < ordered.length; i++) {
      layer.insertBefore(ordered[i], previous.nextSibling);
      previous = ordered[i];
    }
  }

  // An orthogonal polyline whose corners are rounded by up to `radius`
  // (never more than half of either neighboring segment).
  function roundedPath(points, radius) {
    const pts = points.filter((p, i) => i === 0 || p[0] !== points[i - 1][0] || p[1] !== points[i - 1][1]);
    let d = "M " + pts[0][0] + " " + pts[0][1];
    for (let i = 1; i < pts.length - 1; i++) {
      const [px, py] = pts[i - 1], [x, y] = pts[i], [nx, ny] = pts[i + 1];
      const r = Math.min(radius, Math.hypot(x - px, y - py) / 2, Math.hypot(nx - x, ny - y) / 2);
      const ax = x - Math.sign(x - px) * r, ay = y - Math.sign(y - py) * r;
      const bx = x + Math.sign(nx - x) * r, by = y + Math.sign(ny - y) * r;
      d += " L " + ax + " " + ay + " Q " + x + " " + y + " " + bx + " " + by;
    }
    const last = pts[pts.length - 1];
    return d + " L " + last[0] + " " + last[1];
  }

  function renderMap(data, pageTasks, categories) {
    const svg = document.getElementById("work-map");
    // First appearance preserves active-first priority across worker lanes.
    const workers = Array.from(new Set(pageTasks.map((r) => r.worker)));
    const nodes = [];
    const links = [];
    const hub = { key: HUB_KEY, kind: "hub", label: "Project hub", x: -600, y: 0 };
    nodes.push(hub);
    const lanes = workers.map(w => {
      const own = pageTasks.filter(r => r.worker === w);
      const columns = Math.min(4, own.length);
      const rows = Math.ceil(own.length / columns);
      return { w, own, columns, height: Math.max(136, rows * 112) };
    });
    let laneTop = -lanes.reduce((sum, lane) => sum + lane.height, 0) / 2;
    lanes.forEach(({ w, own, columns, height }) => {
      const center = laneTop + height / 2;
      const latest = latestTask(data.results.filter(r => r.worker === w), categories);
      const workerNode = { key: workerKey(w), kind: "worker", label: latest ? latest.task : "No observed task", worker: w,
        x: -280, y: center, count: own.length, latest };
      nodes.push(workerNode);
      links.push([hub, workerNode]);
      const rows = Math.ceil(own.length / columns);
      own.forEach((r, index) => {
        const row = Math.floor(index / columns);
        const taskNode = { key: taskKey(r.worker, r.task), kind: "task", label: r.task,
          worker: r.worker, task: r.task, x: 80 + (index % columns) * 286,
          y: center + (row - (rows - 1) / 2) * 112, data: r, verdict: categories.get(r) };
        nodes.push(taskNode);
        links.push([workerNode, taskNode]);
      });
      laneTop += height;
    });

    const centerX = (Math.min(...nodes.map(n => n.x)) + Math.max(...nodes.map(n => n.x))) / 2;
    for (const n of nodes) n.x -= centerX;
    mapBounds = { x: Math.max(...nodes.map((n) => Math.abs(n.x))) + NODE_WIDTH / 2 + 30,
      y: Math.max(...nodes.map((n) => Math.abs(n.y))) + NODE_HEIGHT / 2 + 26 };
    applyMapPresentation();

    const linkLayer = mapLayer(svg, "links");
    const nodeLayer = mapLayer(svg, "nodes");
    linkLayer.replaceChildren(...links.map(([src, tgt]) => {
      const line = document.createElementNS(SVG_NS, "path");
      const start = src.x + NODE_WIDTH / 2, end = tgt.x - NODE_WIDTH / 2, bend = (start + end) / 2;
      // One line style: right angles with softly rounded corners. Task
      // branches use the gaps above each row rather than crossing cards.
      // A task right beside its worker on the same row gets a straight line;
      // only branches that would pass other cards detour through the gap.
      const besideWorker = tgt.kind === "task" && Math.abs(tgt.y - src.y) < 1 && end - start < NODE_WIDTH;
      line.setAttribute("d", roundedPath(besideWorker ? [[start, src.y], [end, tgt.y]]
        : tgt.kind === "task"
          ? [[start, src.y], [start + 60, src.y], [start + 60, tgt.y - 52], [end - 24, tgt.y - 52], [end - 24, tgt.y], [end, tgt.y]]
          : [[start, src.y], [bend, src.y], [bend, tgt.y], [end, tgt.y]], 12));
      line.setAttribute("fill", "none");
      line.setAttribute("stroke", "var(--line-alt)");
      line.setAttribute("stroke-width", "2");
      line.setAttribute("vector-effect", "non-scaling-stroke");
      return line;
    }));

    // Reuse the same group for the same exact key; remove only obsolete ones.
    const existing = new Map();
    for (const g of Array.from(nodeLayer.children)) {
      if (g.dataset.nodeKey && !existing.has(g.dataset.nodeKey)) existing.set(g.dataset.nodeKey, g);
      else g.remove();
    }
    const ordered = [];
    for (const n of nodes) {
      let g = existing.get(n.key);
      existing.delete(n.key);
      if (!g) g = createNodeGroup();
      g.dataset.nodeKey = n.key;
      g.dataset.kind = n.kind;
      if (n.worker !== undefined) g.dataset.worker = n.worker; else delete g.dataset.worker;
      if (n.task !== undefined) g.dataset.task = n.task; else delete g.dataset.task;
      updateNodeIdentity(g, n.worker);
      const isSelected = !!selected && selected.key === n.key;
      g.setAttribute("transform", "translate(" + n.x + ", " + n.y + ")");
      g.setAttribute("aria-pressed", isSelected ? "true" : "false");
      let description = n.label;
      let stateText = "";
      let aria = "Project hub";
      if (n.kind === "worker") {
        aria = "Worker " + n.worker + ", " + n.count + (n.count === 1 ? " task" : " tasks") + " shown";
        stateText = n.count + (n.count === 1 ? " task shown" : " tasks shown");
        description = n.worker + "\nCurrent/latest task: " + n.label;
      } else if (n.kind === "task") {
        const r = n.data;
        const facts = "process " + label(sectionState(r, "process")) + ", validation " + label(sectionState(r, "validation")) + ", review " + label(sectionState(r, "review"));
        aria = "Task " + r.task + " on worker " + r.worker + ". " + (n.verdict.category === "finished" ? "Finished" : CATEGORY_TEXT[n.verdict.category]) + ": " + facts + ".";
        description = r.worker + " / " + r.task + "\nProcess: " + sectionState(r, "process") + "\nValidation: " + sectionState(r, "validation") + "\nReview: " + sectionState(r, "review");
        stateText = recordedSubtitle(r);
        g.dataset.category = n.verdict.category;
      }
      if (n.kind !== "task") delete g.dataset.category;
      g.dataset.inactive = String(n.kind === "task" ? n.verdict.category !== "active"
        : n.kind === "worker" && !data.results.some(r => r.worker === n.worker && categories.get(r).category === "active"));
      const signal = n.kind === "task" ? taskSignal(n.data, n.verdict)
        : n.kind === "worker" && n.latest ? taskSignal(n.latest, categories.get(n.latest))
          : summarySignal(data.results, categories);
      g.dataset.signal = signal;
      if (n.kind !== "task") {
        const records = n.kind === "worker" ? data.results.filter(r => r.worker === n.worker) : data.results;
        const active = records.filter(r => categories.get(r).category === "active").length;
        if (n.kind === "hub") stateText = records.length + " tasks · " + active + " active";
        const summary = historySummary(records, categories);
        aria += ". " + summary;
        description += "\n" + summary;
        if (n.kind === "worker" && n.latest) {
          const outcome = "Current/latest task " + n.latest.task + ": process " + label(sectionState(n.latest, "process"))
            + ", validation " + label(sectionState(n.latest, "validation")) + ", review " + label(sectionState(n.latest, "review"))
            + ". Right edge describes this task only.";
          aria += " " + outcome;
          description += "\n" + outcome;
        }
      }
      if (g.getAttribute("aria-label") !== aria) g.setAttribute("aria-label", aria);
      const rect = g.querySelector("rect");
      rect.setAttribute("stroke", isSelected ? "var(--focus-ring)" : signal === "active" ? "var(--text-main)" : "var(--btn-border)");
      rect.setAttribute("stroke-width", isSelected ? "3" : signal === "active" ? "2.5" : "1");
      setText(g.querySelector("title"), description);
      setNodeTitle(g.querySelector(".node-label"), n.label);
      setText(g.querySelector(".node-state"), stateText);
      ordered.push(g);
    }
    let lostFocus = false;
    for (const g of existing.values()) {
      if (g === document.activeElement) lostFocus = true;
      g.remove();
    }
    if (lostFocus) svg.focus({ preventScroll: true });
    orderGroups(nodeLayer, ordered);
    for (const g of ordered) {
      for (const span of g.querySelectorAll(".node-label tspan")) {
        if (span.getComputedTextLength() > 156) {
          span.setAttribute("textLength", "156");
          span.setAttribute("lengthAdjust", "spacingAndGlyphs");
        }
      }
    }

    renderDetails(data, pageTasks, categories);
  }

  function clearDetails() {
    const details = document.getElementById("map-details");
    details.replaceChildren();
    details.hidden = true;
    delete details.dataset.key;
    delete details.dataset.mode;
  }

  function renderDetails(data, pageTasks, categories) {
    if (!selected) {
      clearDetails();
      return;
    }
    if (selected.kind !== "task") {
      showOverview(data, pageTasks, categories);
      return;
    }
    const r = data.results.find((t) => t.worker === selected.worker && t.task === selected.task);
    if (r && pageTasks.includes(r)) showDetails(r, data, categories.get(r));
    else showMissing(r ? "filtered" : "absent");
  }

  // Build the detail skeleton once per exact selection and mode; later polls
  // only update text, so focused controls are never replaced.
  function detailsFor(mode, build) {
    const details = document.getElementById("map-details");
    details.hidden = false;
    details.setAttribute("aria-label", selected.kind === "task" ? "Task details"
      : selected.kind === "worker" ? "Worker details" : "Project details");
    if (details.dataset.key !== selected.key || details.dataset.mode !== mode) {
      details.replaceChildren();
      details.dataset.key = selected.key;
      details.dataset.mode = mode;
      build(details);
    }
    return details;
  }
  function clearButton() {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.id = "map-clear-sel";
    // a plain X; its name stays "Clear selection" for screen readers
    btn.setAttribute("aria-label", "Clear selection");
    btn.title = "Close";
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", "0 0 14 14");
    svg.setAttribute("aria-hidden", "true");
    const path = document.createElementNS(SVG_NS, "path");
    path.setAttribute("d", "M3 3l8 8M11 3l-8 8");
    svg.appendChild(path);
    btn.appendChild(svg);
    btn.addEventListener("click", clearSelection);
    return btn;
  }

  function showMissing(reason) {
    const details = detailsFor("missing", (root) => {
      appendDetailsHeader(root);
      const p = document.createElement("p");
      p.className = "warnings";
      p.dataset.field = "missing";
      root.appendChild(p);
    });
    const name = selected.worker + " / " + selected.task;
    setText(details.querySelector('[data-field="title"]'), name);
    setText(details.querySelector('[data-field="missing"]'), reason === "filtered"
      ? "Selected task " + name + " is off-page or filtered out."
      : "Selected task " + name + " is not in the current observation.");
    updateConsoleControl(details, { text: "Output and files are unavailable here until this task is visible in the current observation.", action: null });
  }

  function appendDetailsHeader(root) {
    const header = document.createElement("div");
    header.className = "map-details-header";
    const h3 = document.createElement("h3");
    h3.dataset.field = "title";
    header.append(h3, clearButton());
    root.appendChild(header);
  }

  function showOverview(data, pageTasks, categories) {
    const isWorker = selected.kind === "worker";
    const records = isWorker ? data.results.filter(r => r.worker === selected.worker) : data.results;
    const visible = isWorker ? pageTasks.filter(r => r.worker === selected.worker) : pageTasks;
    const details = detailsFor(selected.kind, root => {
      appendDetailsHeader(root);
      for (const name of ["observed", "summary", "history", "scope"]) {
        const p = text("p", "", "small");
        p.dataset.field = name;
        root.appendChild(p);
      }
    });
    const field = name => details.querySelector('[data-field="' + name + '"]');
    setText(field("title"), isWorker ? selected.worker : "Project hub");
    setText(field("observed"), "Current observation " + (data.observed_at || "unknown"));
    const tally = { active: 0, attention: 0, finished: 0 };
    for (const r of records) tally[categories.get(r).category]++;
    setText(field("summary"), records.length
      ? records.length + " observed tasks · " + tally.active + " active · " + tally.attention + " need attention · " + tally.finished + " finished."
      : isWorker ? "No task evidence for this worker in the current observation."
        : "No structured task evidence in the current observation.");
    setText(field("scope"), visible.length + " tasks on this map page. "
      + (isWorker ? "Select a task node for its process, validation and review details."
        : "The hub groups workers and tasks; it has no task process or worker session of its own."));
    setText(field("history"), historySummary(records, categories));
    const button = isWorker && Array.from(document.querySelectorAll("#console-workers button.console-worker"))
      .find(b => b.dataset.worker === selected.worker);
    updateConsoleControl(details, isWorker
      ? consoleRoute({ worker: selected.worker, task: button ? button.dataset.task || "" : "" })
      : { text: "The project hub has no output or worktree files of its own. Select a worker or task to inspect available output and files.", action: null });
  }

  function consoleRoute(r) {
    const button = Array.from(document.querySelectorAll("#console-workers button.console-worker"))
      .find((b) => b.dataset.worker === r.worker);
    if (!button) return { text: "Protected output and worktree files are unavailable for this worker in the current session.", action: null };
    const output = button.dataset.output === "true";
    const files = button.dataset.files === "true";
    const latest = button.dataset.task || "";
    const event = { worker: r.worker, task: latest };
    if (output && latest === r.task) {
      return {
        text: files ? "Source output and tracked worktree files are available for this task."
          : "Source output is available for this task. Worktree files are not enabled.",
        action: { label: "Open Source console for " + r.worker + " / " + r.task, event },
      };
    }
    if (output && latest) {
      return {
        text: "Protected output is currently showing a different/latest task (" + latest + "), not this historical record."
          + (files ? " Tracked worktree files show the worker's current worktree, not this record." : " Worktree files are not enabled."),
        action: { label: "Open console for different/latest task " + latest, event },
      };
    }
    if (files) {
      return {
        text: (output ? "Source output has no recorded task for this worker. " : "Source output is not available for this worker. ")
          + "Only tracked worktree files are available; they show the worker's current worktree, not this record.",
        action: { label: "Open worktree files for " + r.worker, event },
      };
    }
    return { text: "Source output has no recorded task for this worker, and worktree files are not enabled.", action: null };
  }

  function showDetails(r, data, verdict) {
    const details = detailsFor("task", (root) => {
      appendDetailsHeader(root);
      const brief = text("div", "", "task-brief");
      brief.dataset.field = "brief";
      root.appendChild(brief);
      const fold = document.createElement("details");
      fold.className = "task-tech";
      fold.append(text("summary", "Technical details"));
      root.appendChild(fold);
      const grid = document.createElement("dl");
      grid.className = "evidence-grid";
      grid.style.margin = "16px 0";
      for (const [name, title] of [["observed", "Observed"], ["recorded", "Recorded"], ["status", "Status"], ["activity", "Activity"], ["process", "Process"], ["validation", "Validation"], ["review", "Review"]]) {
        const row = document.createElement("div");
        const dt = document.createElement("dt");
        dt.textContent = title;
        const dd = document.createElement("dd");
        dd.dataset.field = name;
        row.append(dt, dd);
        grid.appendChild(row);
      }
      fold.appendChild(grid);
    });
    const field = (name) => details.querySelector('[data-field="' + name + '"]');
    setText(field("title"), r.worker + " / " + r.task);
    const state = humanState(r, verdict, isLatestForWorker(data, r));
    const brief = field("brief");
    const signature = JSON.stringify([state, trackSteps(r)]);
    if (brief.dataset.signature !== signature) {
      brief.dataset.signature = signature;
      brief.dataset.signal = taskSignal(r, verdict);
      const head = text("div", "", "task-status");
      head.append(text("span", state.label, "state-pill"));
      brief.replaceChildren(head, text("p", state.sentence, "task-sentence"), trackElement(r), nextStep(state.next));
    }
    setText(field("observed"), "Current observation " + (data.observed_at || "unknown"));
    setText(field("recorded"), "Task evidence recorded " + (r.recorded_at || "unknown"));
    setText(field("status"), CATEGORY_TEXT[verdict.category] + (verdict.reasons.length ? " · " + verdict.reasons.join("; ") : ""));
    setText(field("activity"), label(r.activity));
    setText(field("process"), label(sectionState(r, "process")) + " · exit " + (r.process && r.process.exit_code !== null && r.process.exit_code !== undefined ? r.process.exit_code : "unknown"));
    setText(field("validation"), label(sectionState(r, "validation")) + " · " + (r.validation ? r.validation.checks_run : "unknown") + " checks / " + (r.validation ? r.validation.checks_failed : "unknown") + " failed");
    setText(field("review"), label(sectionState(r, "review")) + " · reviewer " + ((r.review && r.review.reviewer) || "not recorded"));

    updateConsoleControl(details, consoleRoute(r));
  }

  function updateConsoleControl(details, route) {
    let consoleText = details.querySelector('[data-field="console"]');
    if (!consoleText) {
      const consoleDiv = text("div", "", "map-details-console");
      consoleText = text("p", "", "small");
      consoleText.dataset.field = "console";
      consoleText.id = "map-console-reason";
      consoleDiv.appendChild(consoleText);
      details.appendChild(consoleDiv);
    }
    setText(consoleText, route.text);
    let open = details.querySelector('[data-field="console-open"]');
    if (!open) {
      open = document.createElement("button");
      open.type = "button";
      open.dataset.field = "console-open";
      open.setAttribute("aria-describedby", "map-console-reason");
      open.addEventListener("click", () => {
        if (open.disabled || !lastData || open.dataset.worker === undefined) return;
        document.dispatchEvent(new CustomEvent("unio-open-console", {
          detail: { worker: open.dataset.worker, task: open.dataset.task },
        }));
      });
      consoleText.parentElement.appendChild(open);
    }
    open.disabled = !route.action;
    open.className = route.action ? "primary" : "";
    if (!route.action) {
      delete open.dataset.worker;
      delete open.dataset.task;
      setText(open, "Open output or files");
      return;
    }
    open.dataset.worker = route.action.event.worker;
    open.dataset.task = route.action.event.task;
    setText(open, route.action.label);
  }

  function clearMapAfterFailure() {
    const svg = document.getElementById("work-map");
    svg.replaceChildren();
    if (mapDrag) svg.dispatchEvent(new PointerEvent("pointercancel", { pointerId: mapDrag.id }));
    mapBounds = { x: 120, y: 80 };
    applyMapPresentation();
    clearDetails();
    setText(document.getElementById("map-counts"), "");
    setText(document.getElementById("map-activity"), "");
    document.getElementById("map-empty").hidden = true;
    document.getElementById("map-pagination").hidden = true;
    setText(document.getElementById("map-page-info"), "");
    document.getElementById("map-prev-page").disabled = true;
    document.getElementById("map-next-page").disabled = true;
    syncWorkerOptions([]);
  }

  // ---------------------------------------------------------- limits
  // Designated AI agents & limits. /api/limits is a cached read-only view of
  // fixed native reads; every label is set through textContent. Missing,
  // stale, expired or invalid readings stay Unknown; nothing is summed across
  // windows and a shared budget group is shown once.
  let lastLimits = null;
  let limitsBusy = false;

  function windowName(minutes) {
    if (minutes === 300) return "5h";
    if (minutes === 10080) return "weekly";
    if (minutes % 1440 === 0) return minutes / 1440 + "d";
    if (minutes % 60 === 0) return minutes / 60 + "h";
    return minutes + " min";
  }

  function span(seconds) {
    const total = Math.max(0, Math.round(seconds));
    const days = Math.floor(total / 86400), hours = Math.floor(total % 86400 / 3600);
    const minutes = Math.floor(total % 3600 / 60);
    if (days) return days + "d " + hours + "h";
    if (hours) return hours + "h " + String(minutes).padStart(2, "0") + "m";
    if (minutes) return minutes + "m";
    return total + "s";
  }

  function section(view, name) {
    const value = view && view[name];
    return value && typeof value === "object" && value.state !== "unknown" ? value : null;
  }

  function limitsWindow(label, w) {
    const box = text("div", "", "limits-window");
    const source = w.source === "codex" ? "Automatic Codex" : w.source === "manual" ? "Manual" : "Unknown source";
    box.dataset.status = w.status;
    box.dataset.source = w.source || "unknown";
    if (w.status === "invalid" || typeof w.remaining_percent !== "number") {
      box.dataset.status = w.status === "invalid" ? "invalid" : "unknown";
      box.append(text("strong", label + " · " + (w.status === "invalid" ? "invalid reading · remaining Unknown" : "remaining Unknown")));
      box.append(text("p", "Source " + source + ". No usable value is shown for this reading."));
      return box;
    }
    const duration = windowName(w.window_minutes);
    const usable = w.status === "fresh" && typeof w.usable_remaining_percent === "number";
    box.append(text("strong", label + " · " + duration + " · " + (usable
      ? w.remaining_percent + "% remaining"
      : "last reading " + w.remaining_percent + "% · usable Unknown (" + w.status + ")")));
    const meter = text("div", "", "limits-meter");
    meter.setAttribute("aria-hidden", "true");
    const fill = document.createElement("span");
    // Only the visual geometry is clamped; the text above shows the value.
    fill.style.width = Math.min(100, Math.max(0, w.remaining_percent)) + "%";
    meter.append(fill);
    box.append(meter);
    let reset = "Reset time Unknown";
    if (w.reset_at) {
      const at = Date.parse(w.reset_at);
      if (Number.isNaN(at)) reset = "Reset time Unknown";
      else if (at <= Date.now()) reset = "Reset " + w.reset_at + " has passed · remaining Unknown until a fresh reading";
      else reset = "Resets " + w.reset_at + " · in " + span((at - Date.now()) / 1000);
    }
    box.append(text("p", reset));
    const age = typeof w.age_seconds === "number" ? "observed " + span(w.age_seconds) + " before check" : "observation age Unknown";
    box.append(text("p", "Source " + source + " · " + age + " · " + w.status));
    return box;
  }

  function renderLimits() {
    const view = lastLimits;
    const policy = section(view, "policy");
    const manual = section(view, "manual");
    const codex = section(view, "codex");
    const authentication = section(view, "authentication");
    const agents = lastData && Array.isArray(lastData.agents) ? lastData.agents : [];
    const statusLine = document.getElementById("limits-status");
    if (!statusLine) return;
    setText(statusLine, view
      ? "Checked " + ((manual && manual.checked_at) || (codex && codex.checked_at) || "at an unknown time") + " · cached local reads"
      : "Allowance overview unavailable. Everything below is Unknown.");

    const lead = document.getElementById("limits-lead");
    lead.replaceChildren();
    if (policy) {
      lead.append(text("strong", "Registered lead: " + (policy.lead_agent || "none") + (policy.lead_group ? " (group " + policy.lead_group + ")" : "")));
      lead.append(document.createTextNode(" · mode " + policy.mode + " · tier " + policy.tier + " · up to "
        + policy.workflow_limit_per_group + " workflow" + (policy.workflow_limit_per_group === 1 ? "" : "s")
        + " per shared budget, including the lead. A registered lead is a reservation, not an attached live conversation; your external lead CLI session is not captured here."));
    } else {
      lead.append(text("strong", "Registered lead, mode and tier: Unknown"));
      lead.append(document.createTextNode(" · the installed policy read is unavailable or unsupported."));
    }

    const accounts = policy ? policy.accounts : {};
    const groupOf = (name) => Object.prototype.hasOwnProperty.call(accounts, name) ? accounts[name] : name;
    const names = new Set(agents.map((a) => a.name).filter((n) => typeof n === "string"));
    if (policy) {
      Object.keys(accounts).forEach((n) => names.add(n));
      if (policy.lead_agent) names.add(policy.lead_agent);
    }
    const active = (group) => {
      if (!policy) return "Native active workflows Unknown";
      const native = policy.active_native_workflows[group] || 0;
      const withLead = native + (policy.lead_group === group ? 1 : 0);
      return "Native active workflows " + native + (policy.lead_group === group ? " + registered lead" : "")
        + " = " + withLead + " of " + policy.workflow_limit_per_group;
    };

    // Members per budget group: a group with exactly one member is that
    // agent's own budget and is shown inside its card; only budgets shared
    // by several agents (or with readings but no agent) get their own card.
    const membersOf = (group) => Array.from(names).filter((n) => policy && groupOf(n) === group).sort();
    const windowsFor = (group) => {
      const parts = [];
      const provider = codex && codex.groups[group];
      if (provider) {
        if (provider.state !== "ok")
          parts.push(text("p", "Automatic Codex: Unknown (" + (provider.reason || "unknown").replaceAll("_", " ") + ")"));
        for (const [bucket, entry] of Object.entries(provider.buckets || {}))
          for (const slot of ["primary", "secondary"])
            if (entry.windows[slot]) parts.push(limitsWindow(bucket, entry.windows[slot]));
        if (provider.last_good)
          for (const [bucket, entry] of Object.entries(provider.last_good.buckets || {}))
            for (const slot of ["primary", "secondary"])
              if (entry.windows[slot]) parts.push(limitsWindow(bucket + " (historical)", entry.windows[slot]));
      }
      const recorded = manual && manual.groups[group];
      if (recorded) for (const [label, w] of Object.entries(recorded.windows)) parts.push(limitsWindow(label, w));
      const current = parts.filter((p) => p.classList && p.classList.contains("limits-window") && !p.textContent.includes("(historical)")).length;
      if (!current) parts.push(text("p", "No current allowance reading · remaining Unknown"));
      return parts;
    };
    const fact = (dl, name, value) => {
      const row = document.createElement("div");
      row.append(text("dt", name), text("dd", value));
      dl.append(row);
    };

    const routes = document.getElementById("limits-routes");
    routes.replaceChildren();
    for (const name of Array.from(names).sort()) {
      const agent = agents.find((a) => a.name === name);
      const card = text("div", "", "limits-card");
      card.dataset.route = name;
      const head = text("h4", "");
      head.append(agentBadge(name));
      card.append(head);
      const tags = text("div", "", "limits-tags");
      if (policy && policy.lead_agent === name) tags.append(text("span", "Registered lead (reservation)", "chip"));
      tags.append(text("span", agent ? (agent.bench && agent.bench.off ? "Benched OFF" : "ON") : "ON/OFF Unknown", "chip" + (agent && agent.bench && agent.bench.off ? " warn" : "")));
      card.append(tags);
      const facts = document.createElement("dl");
      facts.className = "limits-facts";
      const group = policy ? groupOf(name) : null;
      const shared = group ? membersOf(group).filter((m) => m !== name) : [];
      fact(facts, "Budget", group === null ? "Unknown" : group + (shared.length ? ", shared with " + shared.join(", ") : ", its own"));
      // "0 of 1"; the sum is spelled out only when the lead counts too.
      const running = () => {
        const native = policy.active_native_workflows[group] || 0;
        return policy.lead_group === group
          ? native + " + registered lead = " + (native + 1) + " of " + policy.workflow_limit_per_group
          : native + " of " + policy.workflow_limit_per_group;
      };
      fact(facts, "Running", policy ? running() : "Unknown");
      const binary = agent && agent.binary ? agent.binary.present : null;
      fact(facts, "Tool", binary === true ? "installed" : binary === false ? "missing" : "Unknown");
      const auth = /^claude(?:-|$)/.test(name) && authentication && authentication.agents
        ? authentication.agents.claude : null;
      const signIn = auth && auth.authentication === "signed_in" ? "Signed in"
        : auth && auth.authentication === "signed_out" ? "Signed out" : "Unknown";
      fact(facts, "Sign-in", signIn + (auth ? " · " + auth.status + " native observation"
        + (Number.isFinite(auth.age_seconds) ? " · " + span(auth.age_seconds) + " ago" : "") : ""));
      card.append(facts);
      if (group !== null && !shared.length) {
        const allowance = text("div", "", "limits-allowance");
        allowance.dataset.group = group;
        allowance.append(text("p", "Allowance", "limits-allowance-title"), ...windowsFor(group));
        card.append(allowance);
      } else if (group !== null) {
        card.append(text("p", "Allowance: see the shared budget " + group + " below.", "small"));
      }
      routes.append(card);
    }
    if (!names.size) routes.append(text("p", "No configured routes observed. Routes and their limits are Unknown.", "small"));

    const groups = new Set();
    for (const name of names) if (policy) groups.add(groupOf(name));
    if (policy && policy.lead_group) groups.add(policy.lead_group);
    if (manual) Object.keys(manual.groups).forEach((g) => groups.add(g));
    if (codex) Object.keys(codex.groups).forEach((g) => groups.add(g));
    const list = document.getElementById("limits-groups");
    list.replaceChildren();
    let sharedCards = 0;
    for (const group of Array.from(groups).sort()) {
      const members = membersOf(group);
      if (policy && members.length === 1) continue;   // shown inside that agent's card
      const card = text("div", "", "limits-card");
      card.dataset.group = group;
      card.append(text("h4", "Shared budget " + group));
      card.append(text("p", members.length ? "Shared by " + members.join(", ") : "No configured route maps to this group"));
      card.append(text("p", active(group)));
      card.append(...windowsFor(group));
      list.append(card);
      sharedCards++;
    }
    document.querySelector(".limits-subtitle").hidden = !sharedCards && !!policy;
    if (!groups.size) list.append(text("p", "No shared budget groups or readings observed. Allowance is Unknown.", "small"));
    if (!manual || !codex)
      list.append(text("p", (!manual && !codex ? "Manual and automatic Codex readings are" : !manual ? "Manual readings are" : "Automatic Codex readings are")
        + " unavailable from the installed CLI and stay Unknown.", "small limits-unsupported"));
    balanceCardGrids();
  }

  // Card grids keep balanced rows: as many columns as fit (at most four),
  // then spread evenly, so 6 cards are 2 rows of 3 and 7 are 2 rows of 4.
  function balanceGrid(grid) {
    const cards = grid.querySelectorAll(":scope > .limits-card").length;
    if (!cards) return;
    const gap = 6, minCard = 250, maxCols = 4;
    const fit = Math.max(1, Math.min(maxCols, Math.floor((grid.clientWidth + gap) / (minCard + gap))));
    const cols = String(Math.ceil(cards / Math.ceil(cards / fit)));
    if (grid.style.getPropertyValue("--cols") !== cols) grid.style.setProperty("--cols", cols);
  }
  function balanceCardGrids() {
    for (const id of ["limits-routes", "limits-groups"]) {
      const grid = document.getElementById(id);
      if (grid) balanceGrid(grid);
    }
  }
  {
    const routes = document.getElementById("limits-routes");
    if (routes) new ResizeObserver(balanceCardGrids).observe(routes);
  }

  async function refreshLimits() {
    if (limitsBusy) return;
    limitsBusy = true;
    try {
      const response = await fetch("/api/limits", { cache: "no-store" });
      lastLimits = response.ok ? await response.json() : null;
    } catch (_) {
      lastLimits = null;
    } finally {
      limitsBusy = false;
    }
    renderLimits();
  }

  // The loading screen (the dot U) stays only until the first observation
  // has finished, whatever its result; the person is let in right away,
  // even if the animation is still running.
  let booted = false;
  function markReady() {
    if (booted) return;
    booted = true;
    document.documentElement.classList.add("is-ready");
  }
  // A slow first read never holds anyone on the loading screen: after 2.5 s
  // the page opens and its own status line says it is still loading.
  setTimeout(markReady, 2500);

  async function refresh() {
    if (busy) return;
    busy = true;
    document.getElementById("tasks").setAttribute("aria-busy", "true");
    try {
      const response = await fetch("/api/activity", { cache: "no-store" });
      if (!response.ok) throw new Error("observer unavailable");
      render(await response.json());
    } catch (_) {
      lastData = null;
      // Remove old states so a failed observation cannot look current.
      clearMapAfterFailure();
      document.getElementById("tasks").replaceChildren();
      taskListSignature = "";
      document.getElementById("limits").replaceChildren();
      document.getElementById("events").textContent = "";
      document.getElementById("events-raw").textContent = "";
      setDrawerCount("limits-count", "");
      setDrawerCount("events-count", "");
      status.className = "error";
      status.textContent =
        "Local activity is unavailable. No current state is claimed.";
    } finally {
      busy = false;
      document.getElementById("tasks").setAttribute("aria-busy", "false");
      markReady();
    }
    // Allowance metadata never blocks the activity render above.
    renderLimits();
    refreshLimits();
  }
  document.getElementById("refresh").addEventListener("click", refresh);
  // Worker option logos depend on the identity tables initialized above.
  // Seed restored choices before the first request, after those tables exist.
  syncWorkerOptions([]);
  syncCategoryOptions([]);
  refresh();
  setInterval(refresh, 2000);
})();
