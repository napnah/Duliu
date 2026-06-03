const API = "";
let currentProblemId = null;
let currentContestSetId = null;
let currentSlotLabel = "A";
let currentSpec = { samples: [] };
let currentProblem = null;
let sessionId = null;
let editor = null;
let pollTimer = null;
let eventSource = null;
let monitorSocket = null;
let stagePollTimer = null;
let monacoReady = false;
let treeCache = null;
let routeSeq = 0;

const VIEWS = [
  "view-home",
  "view-contest",
  "view-workspace",
  "view-monitor",
  "view-settings",
];

const WORKSPACE_TABS = new Set(["workspace", "work", "pipeline", "editor", "agent"]);

let mdCache = { statement: "", editorial: "" };
let activeWsPane = "code";
/** Editor.md — https://editor.md.ipandao.com */
const EDITORMD_LIB = "https://cdn.jsdelivr.net/npm/editor.md@1.5.0/lib/";
const editorMd = { statement: null, editorial: null };

const STAGE_LABELS = {
  IMPORT: "爬取导入",
  SPEC: "题意规格",
  STATEMENT: "题面",
  SOLUTION: "标程",
  GENERATOR: "数据生成",
  STRESS: "对拍",
  ADVERSARIAL_REVIEW: "对抗审查",
  PACKAGE: "题包",
  EDITORIAL: "题解",
  DONE: "完成",
};

/** 各阶段工作区快捷操作（替代原 import 大面板） */
const STAGE_UI_ACTIONS = {
  IMPORT: [
    { action: "import_check", label: "运行 import_check" },
    { action: "fetch_std", label: "拉取 CF 标程" },
    { action: "open_source", label: "打开原题" },
    { action: "import_confirm", label: "提交确认", primary: true },
    { action: "chat", label: "调度 IMPORT", message: "dispatch IMPORT" },
    { action: "approve", label: "通过 IMPORT" },
  ],
  SPEC: [
    { action: "pane", label: "查看题面", pane: "statement" },
    { action: "chat", label: "调度 SPEC", message: "dispatch SPEC" },
    { action: "approve", label: "通过 SPEC" },
  ],
  STATEMENT: [
    { action: "pane", label: "编辑题面", pane: "statement" },
    { action: "chat", label: "调度 STATEMENT", message: "dispatch STATEMENT" },
    { action: "approve", label: "通过 STATEMENT" },
  ],
  SOLUTION: [
    { action: "pane", label: "编辑标程", pane: "code", artifact: "std" },
    { action: "load_sample", label: "加载样例" },
    { action: "run", label: "运行 (F9)" },
    { action: "chat", label: "调度 SOLUTION", message: "dispatch SOLUTION" },
    { action: "approve", label: "通过 SOLUTION" },
  ],
  GENERATOR: [
    { action: "chat", label: "调度 GENERATOR", message: "dispatch GENERATOR" },
    { action: "approve", label: "通过 GENERATOR" },
  ],
  STRESS: [
    { action: "stress_quick", label: "快速对拍" },
    { action: "counterexamples", label: "反例列表" },
    { action: "chat", label: "调度 STRESS", message: "dispatch STRESS" },
    { action: "approve", label: "通过 STRESS" },
  ],
  ADVERSARIAL_REVIEW: [
    { action: "chat", label: "调度审查", message: "dispatch ADVERSARIAL_REVIEW" },
    { action: "approve", label: "通过审查" },
  ],
  PACKAGE: [
    { action: "polygon_zip", label: "Polygon zip" },
    { action: "package_sync", label: "题包同步" },
    { action: "chat", label: "调度 PACKAGE", message: "dispatch PACKAGE" },
    { action: "approve", label: "通过 PACKAGE" },
  ],
  EDITORIAL: [
    { action: "pane", label: "查看题解", pane: "editorial" },
    { action: "chat", label: "调度 EDITORIAL", message: "dispatch EDITORIAL" },
    { action: "approve", label: "通过 EDITORIAL" },
  ],
  DONE: [
    { action: "pane", label: "题面", pane: "statement" },
    { action: "pane", label: "题解", pane: "editorial" },
  ],
  _default: [
    { action: "chat", label: "调度当前阶段", message: "dispatch" },
    { action: "approve", label: "通过当前阶段" },
    { action: "chat", label: "查看状态", message: "状态" },
  ],
};

/* ── API ── */
async function api(path, opts = {}) {
  const r = await fetch(API + path, {
    headers: { "Content-Type": "application/json", ...opts.headers },
    ...opts,
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || r.statusText);
  }
  if (r.status === 204) return null;
  return r.json();
}

/* ── Router ── */
function parseRoute() {
  const hash = (location.hash || "#/home").replace(/^#/, "");
  const parts = hash.split("/").filter(Boolean);
  if (parts[0] === "home" || parts.length === 0) return { page: "home" };
  if (parts[0] === "settings") return { page: "settings" };
  if (parts[0] === "contest" && parts[1]) return { page: "contest", contestId: parts[1] };
  if (parts[0] === "problem" && parts[1]) {
    let tab = parts[2] || "workspace";
    if (WORKSPACE_TABS.has(tab) && tab !== "monitor") tab = "workspace";
    return { page: "problem", problemId: parts[1], tab };
  }
  return { page: "home" };
}

function navigate(path) {
  const p = path.startsWith("#") ? path.slice(1) : path;
  const next = p.startsWith("/") ? p : `/${p}`;
  const cur = (location.hash || "").replace(/^#/, "");
  if (cur === next) {
    onRoute();
    return;
  }
  location.hash = next;
}

function problemViewId(tab) {
  if (tab === "monitor") return "view-monitor";
  return "view-workspace";
}

function isWorkspaceRoute(route) {
  return route.page === "problem" && route.tab !== "monitor";
}

function showView(viewId) {
  for (const id of VIEWS) {
    document.getElementById(id).classList.toggle("hidden", id !== viewId);
  }
  const shell = document.getElementById("app-shell");
  const isWorkspace = viewId === "view-workspace";
  const isSettings = viewId === "view-settings";
  shell.classList.toggle("sidebar-collapsed", isWorkspace);
  shell.classList.toggle("workspace-mode", isWorkspace);
  document.getElementById("sidebar").classList.toggle("hidden", isSettings);
}

function updateBreadcrumb(route) {
  const el = document.getElementById("breadcrumb");
  const parts = ['<a href="#/home" data-nav>工作区</a>'];
  if (route.page === "contest" && treeCache) {
    const c = treeCache.contest_sets.find((x) => x.id === route.contestId);
    parts.push(` / <a href="#/contest/${route.contestId}">${c?.name || "套题"}</a>`);
  }
  if (route.page === "problem" && currentProblem) {
    if (currentContestSetId) {
      const c = treeCache?.contest_sets.find((x) => x.id === currentContestSetId);
      if (c) parts.push(` / <a href="#/contest/${currentContestSetId}">${c.name}</a>`);
    }
    parts.push(` / <a href="#/problem/${route.problemId}/workspace">${currentProblem.title}</a>`);
    const tabNames = { workspace: "工作区", monitor: "监控" };
    parts.push(` / ${tabNames[route.tab] || "工作区"}`);
  }
  if (route.page === "settings") parts.push(" / 设置");
  el.innerHTML = parts.join("");
  el.querySelectorAll("[data-nav]").forEach((a) => {
    a.onclick = (e) => {
      e.preventDefault();
      navigate(a.getAttribute("href").replace("#", ""));
    };
  });
}

function updateProblemSubnav(route) {
  const nav = document.getElementById("problem-subnav");
  const show = route.page === "problem" && route.problemId;
  nav.hidden = !show;
  if (!show) return;
  nav.querySelectorAll("[data-problem-tab]").forEach((a) => {
    const tab = a.dataset.problemTab;
    const active =
      tab === "workspace"
        ? isWorkspaceRoute(route)
        : tab === route.tab;
    a.classList.toggle("active", active);
    a.href = `#/problem/${route.problemId}/${tab}`;
    a.onclick = (e) => {
      e.preventDefault();
      navigate(`/problem/${route.problemId}/${tab}`);
    };
  });
}

async function onRoute() {
  const seq = ++routeSeq;
  const route = parseRoute();
  updateBreadcrumb(route);
  updateProblemSubnav(route);
  stopPollers();

  if (route.page === "settings") {
    showView("view-settings");
    currentProblemId = null;
    currentContestSetId = null;
    await loadSettings();
    return;
  }

  if (route.page === "home") {
    showView("view-home");
    currentProblemId = null;
    currentContestSetId = null;
    await loadTree();
    if (seq !== routeSeq) return;
    renderHomeRecent();
    return;
  }

  if (route.page === "contest") {
    showView("view-contest");
    currentContestSetId = route.contestId;
    currentProblemId = null;
    sessionId = null;
    await loadTree();
    if (seq !== routeSeq) return;
    await openContest(route.contestId);
    return;
  }

  if (route.page === "problem") {
    const tab = route.tab || "workspace";
    showView(problemViewId(tab));
    currentProblemId = route.problemId;
    currentContestSetId = null;
    await loadTree();
    if (seq !== routeSeq) return;
    await openProblem(route.problemId);
    if (seq !== routeSeq) return;

    if (isWorkspaceRoute(route)) {
      await refreshPipeline();
      if (seq !== routeSeq) return;
      await refreshRunnerEnv();
      if (seq !== routeSeq) return;
      await ensureMonaco();
      if (seq !== routeSeq) return;
      await loadArtifactKinds();
      if (seq !== routeSeq) return;
      layoutMonaco();
      if (seq !== routeSeq) return;
      await refreshAgentContext();
      if (seq !== routeSeq) return;
      stagePollTimer = setInterval(refreshPipeline, 5000);
    } else if (tab === "monitor") {
      await loadEvents();
      if (seq !== routeSeq) return;
      startEventStream();
    }
  }
}

function stopPollers() {
  if (pollTimer) clearInterval(pollTimer);
  if (stagePollTimer) clearInterval(stagePollTimer);
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }
  if (monitorSocket) {
    monitorSocket.close();
    monitorSocket = null;
  }
  pollTimer = null;
  stagePollTimer = null;
  const sseEl = document.getElementById("monitor-sse-status");
  if (sseEl) sseEl.textContent = "实时通道未连接";
}

function appendMonitorEvent(e, ul) {
  const li = document.createElement("li");
  li.textContent = `${e.created_at?.slice(0, 19) || ""} [${e.source || ""}] ${e.type || ""}: ${e.message || ""}`;
  ul.appendChild(li);
}

function onMonitorPayload(data) {
  if (data.type === "connected") return;
  const ul = document.getElementById("event-list");
  if (!ul) return;
  const rid = document.getElementById("filter-run-id")?.value?.trim();
  if (rid && data.run_id && data.run_id !== rid) return;
  appendMonitorEvent(data, ul);
  while (ul.children.length > 200) ul.removeChild(ul.firstChild);
}

function startSseMonitor() {
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }
  let url = "/api/monitor/events/stream?";
  if (currentProblemId) url += `problem_id=${currentProblemId}&`;
  if (currentContestSetId) url += `contest_set_id=${currentContestSetId}&`;
  const statusEl = document.getElementById("monitor-sse-status");
  eventSource = new EventSource(API + url);
  eventSource.onopen = () => {
    if (statusEl) statusEl.textContent = "SSE 已连接";
  };
  eventSource.onmessage = (ev) => {
    try {
      onMonitorPayload(JSON.parse(ev.data));
    } catch (_) {
      /* ignore */
    }
  };
  eventSource.onerror = () => {
    if (statusEl) statusEl.textContent = "SSE 断开，3s 后轮询…";
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
    if (!pollTimer) pollTimer = setInterval(loadEvents, 3000);
  };
}

function startWebSocketMonitor() {
  if (monitorSocket) {
    monitorSocket.close();
    monitorSocket = null;
  }
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  let q = "/api/monitor/events/ws?";
  if (currentProblemId) q += `problem_id=${currentProblemId}&`;
  if (currentContestSetId) q += `contest_set_id=${currentContestSetId}&`;
  const statusEl = document.getElementById("monitor-sse-status");
  monitorSocket = new WebSocket(`${proto}//${location.host}${q}`);
  monitorSocket.onopen = () => {
    if (statusEl) statusEl.textContent = "WebSocket 已连接";
  };
  monitorSocket.onmessage = (ev) => {
    try {
      onMonitorPayload(JSON.parse(ev.data));
    } catch (_) {
      /* ignore */
    }
  };
  const fallback = () => {
    if (monitorSocket) {
      monitorSocket.close();
      monitorSocket = null;
    }
    startSseMonitor();
  };
  monitorSocket.onerror = fallback;
  monitorSocket.onclose = (e) => {
    if (e.code !== 1000 && !eventSource) fallback();
  };
}

function startEventStream() {
  if (typeof WebSocket !== "undefined") startWebSocketMonitor();
  else startSseMonitor();
}

window.addEventListener("hashchange", onRoute);

/* ── Monaco ── */
async function ensureMonaco() {
  if (monacoReady) return;
  await new Promise((resolve) => {
    require.config({
      paths: { vs: "https://cdn.jsdelivr.net/npm/monaco-editor@0.52.0/min/vs" },
    });
    require(["vs/editor/editor.main"], () => {
      editor = monaco.editor.create(document.getElementById("monaco-editor"), {
        value: "",
        language: "cpp",
        theme: "vs",
        automaticLayout: true,
        fontSize: 14,
        minimap: { enabled: true },
        scrollBeyondLastLine: false,
      });
      monacoReady = true;
      new ResizeObserver(() => editor?.layout()).observe(
        document.getElementById("monaco-editor")
      );
      resolve();
    });
  });
}

function layoutMonaco() {
  if (!editor) return;
  requestAnimationFrame(() => editor.layout());
  window.addEventListener("resize", () => editor?.layout(), { once: true });
}

function langForKind(kind) {
  if (kind === "std" || kind === "brute") {
    return document.getElementById("artifact-language")?.value || "cpp";
  }
  if (kind === "checker") return "python";
  if (kind === "statement" || kind === "editorial") return "markdown";
  if (kind === "spec" || kind === "idea") return "yaml";
  return "plaintext";
}

/* ── Tree ── */
async function loadTree() {
  treeCache = await api("/api/tree");
  document.getElementById("tree-workspace").textContent = treeCache.workspace.name;
  const csUl = document.getElementById("tree-contests");
  csUl.innerHTML = "";
  for (const c of treeCache.contest_sets) {
    const li = document.createElement("li");
    li.textContent = `${c.name} · ${c.contest_style}`;
    li.dataset.id = c.id;
    li.classList.toggle("active", c.id === currentContestSetId);
    li.onclick = (e) => {
      e.preventDefault();
      navigate(`/contest/${c.id}`);
    };
    csUl.appendChild(li);
  }
  const ul = document.getElementById("tree-problems");
  ul.innerHTML = "";
  for (const p of treeCache.problems) {
    const li = document.createElement("li");
    li.textContent = p.title;
    li.dataset.id = p.id;
    li.classList.toggle("active", p.id === currentProblemId);
    li.onclick = (e) => {
      e.preventDefault();
      navigate(`/problem/${p.id}/workspace`);
    };
    ul.appendChild(li);
  }
  markTreeActive();
}

function renderHomeRecent() {
  const box = document.getElementById("home-recent");
  box.innerHTML = "";
  if (!treeCache) return;
  for (const c of treeCache.contest_sets.slice(0, 4)) {
    const d = document.createElement("div");
    d.className = "home-card";
    d.innerHTML = `<strong>套题</strong><br>${c.name}<br><span class="muted">${c.contest_style} · ${c.slot_count} 槽</span>`;
    d.onclick = () => navigate(`/contest/${c.id}`);
    box.appendChild(d);
  }
  for (const p of treeCache.problems.slice(0, 6)) {
    const d = document.createElement("div");
    d.className = "home-card";
    d.innerHTML = `<strong>单题</strong><br>${p.title}<br><span class="muted">${p.current_stage}</span>`;
    d.onclick = () => navigate(`/problem/${p.id}/workspace`);
    box.appendChild(d);
  }
}

/* ── Contest ── */
function markTreeActive() {
  document.querySelectorAll("#tree-contests li").forEach((li) => {
    li.classList.toggle("active", li.dataset.id === currentContestSetId);
  });
  document.querySelectorAll("#tree-problems li").forEach((li) => {
    li.classList.toggle("active", li.dataset.id === currentProblemId);
  });
}

async function openContest(id) {
  currentContestSetId = id;
  currentProblemId = null;
  sessionId = null;
  markTreeActive();
  const d = await api(`/api/contest-sets/${id}`);
  document.getElementById("contest-title").textContent = d.name;
  document.getElementById("contest-status").textContent = d.status;
  document.getElementById("contest-meta").textContent =
    `${d.contest_style} · ${d.slot_count} 槽`;
  renderDifficultyChart(d);
  renderSlotTable(d);
  const ev = d.set_eval_json || {};
  document.getElementById("set-eval-summary").textContent = ev.summary
    ? `${ev.summary}`
    : "尚未运行套题评估";
  await refreshContestLanggraphHistory(id);
}

async function renderLanggraphHistory(listId, metaId, data, health) {
  const ul = document.getElementById(listId);
  const meta = document.getElementById(metaId);
  if (!ul) return;
  ul.innerHTML = "";
  const serverOn = health?.langgraph ?? data?.enabled;
  if (!data?.enabled && !serverOn) {
    if (meta) {
      meta.textContent =
        "LangGraph 未启用 — 设置环境变量 DULIU_USE_LANGGRAPH=true 并重启服务";
    }
    ul.innerHTML = "<li>—</li>";
    return;
  }
  if (!data?.enabled && serverOn) {
    if (meta) meta.textContent = data?.error || "LangGraph 已开启，但无法加载历史（检查 langgraph 依赖与 checkpoint）";
    ul.innerHTML = "<li>—</li>";
    return;
  }
  const cp = health?.langgraph_checkpoint || "";
  if (meta) {
    meta.textContent = `thread: ${data.thread_id || "—"}${cp ? ` · checkpointer: ${cp}` : ""}`;
  }
  const hist = data.history || [];
  if (!hist.length) {
    ul.innerHTML = "<li>暂无 checkpoint（调度 dispatch 后生成）</li>";
    return;
  }
  for (const h of hist) {
    const li = document.createElement("li");
    const cid = (h.checkpoint_id || "?").slice(0, 8);
    const extra =
      h.stage_id != null
        ? `stage=${h.stage_id}`
        : `slots=${h.slot_count ?? 0} finalized=${h.finalized ?? false}`;
    li.textContent = `${cid}… ${extra}`;
    ul.appendChild(li);
  }
}

async function fetchHealth() {
  try {
    return await api("/api/health");
  } catch {
    return {};
  }
}

async function refreshContestLanggraphHistory(contestSetId) {
  const health = await fetchHealth();
  try {
    const data = await api(`/api/contest-sets/${contestSetId}/langgraph/history`);
    await renderLanggraphHistory("contest-lg-history", "contest-lg-meta", data, health);
  } catch (e) {
    await renderLanggraphHistory(
      "contest-lg-history",
      "contest-lg-meta",
      { enabled: !!health.langgraph, history: [], error: e.message },
      health
    );
  }
}

async function refreshPipelineLanggraphHistory() {
  if (!currentProblemId) return;
  const health = await fetchHealth();
  try {
    const data = await api(`/api/problems/${currentProblemId}/langgraph/history`);
    await renderLanggraphHistory("pipeline-lg-history", "pipeline-lg-meta", data, health);
  } catch (e) {
    await renderLanggraphHistory(
      "pipeline-lg-history",
      "pipeline-lg-meta",
      { enabled: !!health.langgraph, history: [], error: e.message },
      health
    );
  }
}

function renderDifficultyChart(detail) {
  const box = document.getElementById("difficulty-chart");
  box.innerHTML = "";
  const ev = detail.set_eval_json || {};
  const chart = ev.chart || {};
  const labels = chart.labels?.length ? chart.labels : detail.slots.map((s) => s.slot_label);
  const ratings =
    chart.ratings?.length >= 1
      ? chart.ratings
      : detail.slots.map((s) => s.problem?.spec_json?.difficulty?.rating).filter((x) => x != null);
  if (!ratings.length) {
    box.textContent = "暂无难度数据";
    return;
  }
  const maxR = Math.max(...ratings, 1);
  labels.forEach((lab, i) => {
    const r = ratings[i];
    if (r == null) return;
    const wrap = document.createElement("div");
    wrap.className = "bar-wrap";
    const bar = document.createElement("div");
    bar.className = "bar";
    bar.style.height = `${Math.round((r / maxR) * 90)}px`;
    wrap.appendChild(bar);
    wrap.appendChild(document.createTextNode(`${lab} · ${r}`));
    box.appendChild(wrap);
  });
}

function renderSlotTable(detail) {
  const tbody = document.querySelector("#slot-table tbody");
  tbody.innerHTML = "";
  for (const s of detail.slots) {
    const tr = document.createElement("tr");
    const title = s.problem?.title || "（空）";
    const stage = s.problem?.current_stage || "—";
    const rating = s.problem?.spec_json?.difficulty?.rating ?? "—";
    tr.innerHTML = `<td>${s.slot_label}</td><td>${title}</td><td>${stage}</td><td>${rating}</td><td><span class="muted">打开 →</span></td>`;
    tr.onclick = () => {
      currentSlotLabel = s.slot_label;
      if (s.problem_id) navigate(`/problem/${s.problem_id}/workspace`);
    };
    tbody.appendChild(tr);
  }
}

/* ── Problem ── */
async function openProblem(id) {
  if (currentProblemId !== id) {
    sessionId = null;
  }
  currentProblemId = id;
  currentProblem = await api(`/api/problems/${id}`);
  currentSpec = currentProblem.spec_json || { samples: [] };
  currentContestSetId = currentProblem.contest_set_id || null;
  markTreeActive();
}

async function refreshPipeline() {
  if (!currentProblemId) return;
  const p = await api(`/api/problems/${currentProblemId}`);
  currentProblem = p;
  const graph = await api(`/api/problems/${currentProblemId}/pipeline-graph`);
  document.getElementById("pipeline-title").textContent = p.title;
  document.getElementById("pipeline-stage").textContent = p.current_stage;
  document.getElementById("pipeline-style").textContent =
    `${p.contest_style} / ${p.problem_type} / ${p.originality}`;
  document.getElementById("pipeline-control").textContent = p.control_mode;
  window.__importMeta = graph.import || {};
  renderStageActions(p);
  const polyLine = document.getElementById("polygon-upload-line");
  if (polyLine) {
    try {
      const st = await api(`/api/problems/${currentProblemId}/polygon/upload-status`);
      const u = st.upload || {};
      let hint = u.zip_path ? ` · Polygon zip: ${u.ok ? "就绪" : "缺工件"}` : "";
      try {
        const apiSt = await api(`/api/problems/${currentProblemId}/polygon/api/status`);
        if (apiSt.linked_polygon_problem_id) {
          hint += ` · API#${apiSt.linked_polygon_problem_id}`;
        } else if (apiSt.api_configured) {
          hint += " · API 已配置未关联";
        }
      } catch {
        /* ignore */
      }
      polyLine.textContent = hint;
    } catch {
      polyLine.textContent = "";
    }
  }
  renderGraphTimeline("stage-timeline", graph);
  await refreshPipelineLanggraphHistory();
}

function renderStageActions(p) {
  const bar = document.getElementById("stage-actions-bar");
  if (!bar) return;
  const stage = p.current_stage;
  let actions = STAGE_UI_ACTIONS[stage] || STAGE_UI_ACTIONS._default;
  if (stage !== "IMPORT" && p.originality === "NON_ORIGINAL" && !window.__importMeta?.import_check_ok) {
    actions = [
      { action: "import_check", label: "运行 import_check" },
      { action: "fetch_std", label: "拉取 CF 标程" },
      ...actions.slice(0, 4),
    ];
  }
  bar.classList.remove("hidden");
  bar.innerHTML = "";
  const label = document.createElement("span");
  label.className = "stage-actions-label";
  label.textContent = `${STAGE_LABELS[stage] || stage} · 操作`;
  const inner = document.createElement("div");
  inner.className = "stage-actions-inner";
  bar.appendChild(label);
  bar.appendChild(inner);
  for (const a of actions) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = a.primary ? "btn-stage-primary" : "btn-stage btn-secondary btn-sm";
    btn.textContent = a.label;
    btn.onclick = () => runStageUiAction(a);
    inner.appendChild(btn);
  }
}

async function runStageUiAction(a) {
  if (!currentProblemId) return;
  if (a.pane) {
    if (a.artifact) {
      const sel = document.getElementById("artifact-kind");
      if (sel) sel.value = a.artifact;
      await loadArtifactContent(a.artifact);
    }
    setWorkspacePane(a.pane === "code" ? "code" : a.pane);
    return;
  }
  if (a.action === "import_check") {
    document.getElementById("btn-import-check")?.click();
    return;
  }
  if (a.action === "fetch_std") {
    document.getElementById("btn-fetch-ac-std")?.click();
    return;
  }
  if (a.action === "import_confirm") {
    document.getElementById("btn-import-confirm")?.click();
    return;
  }
  if (a.action === "open_source") {
    const url = window.__importMeta?.problem_url;
    if (url) window.open(url, "_blank", "noopener");
    else alert("无原题 URL");
    return;
  }
  if (a.action === "approve") {
    document.getElementById("btn-approve")?.click();
    return;
  }
  if (a.action === "load_sample") {
    document.getElementById("btn-load-sample")?.click();
    return;
  }
  if (a.action === "run") {
    document.getElementById("btn-run")?.click();
    return;
  }
  if (a.action === "stress_quick") {
    document.getElementById("btn-stress-quick")?.click();
    return;
  }
  if (a.action === "counterexamples") {
    document.getElementById("btn-counterexamples")?.click();
    return;
  }
  if (a.action === "polygon_zip") {
    document.getElementById("btn-polygon-zip")?.click();
    return;
  }
  if (a.action === "package_sync") {
    document.getElementById("btn-package-sync")?.click();
    return;
  }
  if (a.action === "chat" && a.message) {
    let msg = a.message;
    if (msg === "dispatch") {
      const st = currentProblem?.current_stage;
      msg = `dispatch ${st}`;
    }
    await sendAgentMessage(msg);
    return;
  }
}

function renderGraphTimeline(containerId, graph) {
  const ul = document.getElementById(containerId);
  if (!ul) return;
  ul.innerHTML = "";
  const cur = graph.current_stage;
  const curIdx = graph.nodes.findIndex((n) => n.stage_id === cur);
  graph.nodes.forEach((n, i) => {
    const li = document.createElement("li");
    let cls = "future";
    if (n.status === "APPROVED") cls = "done";
    else if (n.is_current) cls = n.status === "AWAITING_HUMAN" ? "waiting" : "current";
    else if (curIdx >= 0 && i < curIdx) cls = "done";
    li.className = cls;
    li.innerHTML = `
      <span class="stage-node">${i + 1}</span>
      <div class="stage-label">${n.stage_id}</div>
      <div class="stage-status">${STAGE_LABELS[n.stage_id] || n.stage_id} — ${n.status}</div>`;
    ul.appendChild(li);
  });
}

function stageTimelineClass(stage, currentStage, status) {
  if (status === "APPROVED" || stage === "DONE") return "done";
  if (stage === currentStage) {
    if (status === "AWAITING_HUMAN" || status === "RUNNING") return "waiting";
    return "current";
  }
  const order = window.__stageOrder || [];
  const ci = order.indexOf(currentStage);
  const si = order.indexOf(stage);
  if (ci >= 0 && si > ci) return "future";
  if (si < ci) return "done";
  return "future";
}

async function refreshStageTimeline(containerId) {
  if (!currentProblemId) return;
  const stages = await api(`/api/problems/${currentProblemId}/stages`);
  const p = await api(`/api/problems/${currentProblemId}`);
  window.__stageOrder = stages.map((s) => s.stage_id);
  const ul = document.getElementById(containerId);
  if (!ul) return;
  ul.innerHTML = "";
  const curIdx = stages.findIndex((s) => s.stage_id === p.current_stage);
  stages.forEach((s, i) => {
    const li = document.createElement("li");
    li.className = stageTimelineClass(s.stage_id, p.current_stage, s.status);
    const label = STAGE_LABELS[s.stage_id] || s.stage_id;
    let hint = s.status;
    if (i > curIdx && s.status === "PENDING") hint = "未开始";
    if (s.stage_id === p.current_stage) hint = `进行中 · ${s.status}`;
    li.innerHTML = `
      <span class="stage-node">${i + 1}</span>
      <div class="stage-label">${s.stage_id}</div>
      <div class="stage-status">${label} — ${hint}</div>`;
    ul.appendChild(li);
  });
}

async function refreshAgentContext() {
  if (!currentProblemId) {
    document.getElementById("agent-context").textContent = "请从侧栏选择题目";
    await refreshAgentToolsPanel();
    return;
  }
  const p = currentProblem || (await api(`/api/problems/${currentProblemId}`));
  document.getElementById("agent-context").textContent =
    `${p.title} · 当前阶段 ${p.current_stage} · ${p.contest_style}`;
  await refreshAgentToolsPanel();
}

async function refreshAgentToolsPanel() {
  const listEl = document.getElementById("agent-tool-list");
  const histEl = document.getElementById("agent-tool-history");
  if (!listEl || !histEl) return;
  try {
    const meta = await api("/api/session/tools");
    listEl.innerHTML = "";
    const tools = meta.tools || [];
    if (!meta.enabled) {
      listEl.innerHTML = "<li>Tool Calling 未启用</li>";
    } else if (!tools.length) {
      listEl.innerHTML = "<li>无注册工具</li>";
    } else {
      for (const name of tools) {
        const li = document.createElement("li");
        li.textContent = name;
        listEl.appendChild(li);
      }
    }
    histEl.innerHTML = "";
    if (!sessionId) {
      histEl.innerHTML = "<li class='muted'>发送消息后显示调用记录</li>";
      return;
    }
    const msgs = await api(`/api/sessions/${sessionId}/messages`);
    const calls = [];
    for (const m of msgs) {
      const tj = m.tool_calls_json;
      const used = (tj && tj.tools) || [];
      for (const u of used) {
        calls.push({ tool: u.tool || "?", at: m.created_at });
      }
    }
    const recent = calls.slice(-12).reverse();
    if (!recent.length) {
      histEl.innerHTML = "<li class='muted'>本会话尚无工具调用</li>";
      return;
    }
    for (const c of recent) {
      const li = document.createElement("li");
      li.innerHTML = `<strong>${c.tool}</strong>`;
      histEl.appendChild(li);
    }
  } catch (e) {
    listEl.innerHTML = `<li>${e.message}</li>`;
  }
}

/* ── Artifacts & run ── */
async function loadArtifactKinds() {
  const data = await api(`/api/problems/${currentProblemId}/artifacts`);
  const sel = document.getElementById("artifact-kind");
  const kinds = data.items.map((i) => i.kind);
  const preferred = ["statement", "std", "brute", "checker", "interactor", "protocol", "gen", "editorial"];
  const ordered = [...new Set([...preferred.filter((k) => kinds.includes(k)), ...kinds])];
  sel.innerHTML = "";
  for (const k of ordered.length ? ordered : ["std", "brute", "statement"]) {
    const o = document.createElement("option");
    o.value = k;
    o.textContent = k;
    sel.appendChild(o);
  }
  const codeKinds = ["std", "brute", "checker", "interactor", "gen", "protocol"];
  const pick = codeKinds.find((k) => ordered.includes(k)) || ordered[0] || "std";
  sel.value = pick;
  await loadArtifactContent(sel.value);
  sel.onchange = () => {
    loadArtifactContent(sel.value);
    if (sel.value === "std" || sel.value === "brute") {
      document.getElementById("run-program").value = sel.value;
    }
  };
}

async function loadArtifactContent(kind) {
  const langSel = document.getElementById("artifact-language");
  try {
    const art = await api(`/api/problems/${currentProblemId}/artifacts/${kind}`);
    if (art.language) langSel.value = art.language;
    monaco.editor.setModelLanguage(editor.getModel(), langForKind(kind));
    editor.setValue(art.content_text);
  } catch {
    monaco.editor.setModelLanguage(editor.getModel(), langForKind(kind));
    editor.setValue("");
  }
}

async function pollJobWs(jobId) {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(`${proto}//${location.host}/api/jobs/${jobId}/ws`);
    const timer = setTimeout(() => {
      ws.close();
      reject(new Error("job ws timeout"));
    }, 120000);
    ws.onmessage = (ev) => {
      try {
        const d = JSON.parse(ev.data);
        if (d.type === "done" || d.status === "done" || d.status === "failed") {
          clearTimeout(timer);
          ws.close();
          resolve({
            id: jobId,
            status: d.status,
            kind: d.kind,
            result_json: d.result_json,
            log_text: d.log_text,
          });
        }
      } catch (e) {
        clearTimeout(timer);
        reject(e);
      }
    };
    ws.onerror = () => {
      clearTimeout(timer);
      reject(new Error("job ws error"));
    };
  });
}

async function pollJob(jobId) {
  if (typeof WebSocket !== "undefined") {
    try {
      return await pollJobWs(jobId);
    } catch (_) {
      /* fallback REST */
    }
  }
  for (let i = 0; i < 120; i++) {
    const job = await api(`/api/jobs/${jobId}`);
    if (job.status === "done" || job.status === "failed") return job;
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error("job timeout");
}

function jobResultMessage(done) {
  const r = done.result_json || {};
  if (r.error) return String(r.error);
  if (r.reason) return String(r.reason);
  if (r.verdict) return String(r.verdict);
  if (done.log_text) return String(done.log_text).slice(0, 800);
  return done.status || "unknown";
}

function showRunResult(done) {
  const r = done.result_json || {};
  const stdout = r.stdout || "";
  let detail = "";
  if (r.stderr) detail += "[stderr]\n" + r.stderr + "\n";
  if (r.compile_log) detail += "[compile]\n" + r.compile_log + "\n";
  if (r.std) detail += "[std]\n" + JSON.stringify(r.std, null, 2) + "\n";
  if (r.brute) detail += "[brute]\n" + JSON.stringify(r.brute, null, 2) + "\n";
  if (done.status === "failed" && r.error) detail = (detail ? detail + "\n" : "") + r.error;

  const stdoutEl = document.getElementById("run-stdout");
  const outEl = document.getElementById("run-output");
  if (stdoutEl) stdoutEl.textContent = stdout || (detail ? "" : "（无输出）");
  if (outEl) {
    outEl.textContent =
      detail.trim() || (stdout ? "" : jobResultMessage(done)) || "（无附加信息）";
  }

  const el = document.getElementById("run-verdict");
  const v = r.verdict || (done.status === "failed" ? jobResultMessage(done) : done.status);
  el.textContent = v;
  const ok = v === "OK" || v === "AC" || (r.ok === true && done.status === "done");
  el.className = "verdict " + (ok ? "ok" : "fail");
}

async function refreshRunnerEnv() {
  const el = document.getElementById("runner-env-hint");
  if (!el) return;
  try {
    const st = await api("/api/runner/sandbox-status");
    const gppOk =
      st.gpp_available === true || (st.gpp_available === undefined && !!st.gpp_path);
    const pyOk =
      st.python3_available === true ||
      (st.python3_available === undefined && !!st.python_path);
    const gpp = gppOk
      ? `g++ 就绪${st.gpp_path ? ` (${st.gpp_path})` : ""}`
      : "g++ 未安装 — 在容器执行: apt-get update && apt-get install -y g++ python3，或重建镜像";
    const py = pyOk ? "python 就绪" : "python 未安装";
    const javac = st.javac_available ? " · javac 就绪" : "";
    el.textContent = `Runner: ${st.mode} · ${gpp} · ${py}${javac}`;
  } catch (e) {
    el.textContent = `Runner 状态未知: ${e.message}`;
  }
}

function renderMarkdown(el, text) {
  if (!el) return;
  const src = text || "";
  if (typeof marked !== "undefined") {
    marked.setOptions({ gfm: true, breaks: true });
    el.innerHTML = marked.parse(src);
  } else {
    el.textContent = src;
  }
  if (typeof renderMathInElement !== "undefined") {
    renderMathInElement(el, {
      delimiters: [
        { left: "$$", right: "$$", display: true },
        { left: "$", right: "$", display: false },
        { left: "\\(", right: "\\)", display: false },
        { left: "\\[", right: "\\]", display: true },
      ],
      throwOnError: false,
    });
  }
}

function setWorkspacePane(name) {
  activeWsPane = name;
  document.querySelectorAll("[data-ws-pane]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.wsPane === name);
  });
  document.querySelectorAll(".workspace-pane-stack > .ws-pane").forEach((pane) => {
    const id = pane.id.replace("ws-pane-", "");
    pane.classList.toggle("active", id === name);
  });
  if (name === "code") {
    const sel = document.getElementById("artifact-kind");
    if (sel && (sel.value === "statement" || sel.value === "editorial")) {
      sel.value = orderedIncludesStd(sel) ? "std" : "brute";
      void loadArtifactContent(sel.value);
    }
    requestAnimationFrame(() => layoutMonaco());
  } else if (editor) {
    /* 切走代码页时触发 layout，避免 Monaco 残留绘制 */
    requestAnimationFrame(() => editor.layout());
  }
  if (name === "statement") void loadMarkdownPane("statement");
  if (name === "editorial") void loadMarkdownPane("editorial");
}

function orderedIncludesStd(sel) {
  return Array.from(sel.options).some((o) => o.value === "std");
}

function editorMdContainerId(kind) {
  return kind === "statement" ? "editormd-statement" : "editormd-editorial";
}

function getEditorMdContent(kind) {
  const ed = editorMd[kind];
  if (ed && typeof ed.getMarkdown === "function") {
    return ed.getMarkdown() || "";
  }
  return mdCache[kind] || "";
}

function resizeEditorMd(kind) {
  const ed = editorMd[kind];
  if (ed && typeof ed.resize === "function") {
    requestAnimationFrame(() => ed.resize());
  }
}

function ensureEditorMd(kind, initialText) {
  return new Promise((resolve) => {
    if (typeof editormd === "undefined") {
      resolve(null);
      return;
    }
    const id = editorMdContainerId(kind);
    const text = initialText ?? mdCache[kind] ?? "";
    if (editorMd[kind]) {
      editorMd[kind].setMarkdown(text);
      resizeEditorMd(kind);
      resolve(editorMd[kind]);
      return;
    }
    const src = document.getElementById(`${id}-src`);
    if (src) src.value = text;
    const host = document.getElementById(id)?.closest(".editormd-host");
    const stack = document.querySelector(".workspace-pane-stack");
    const h = Math.max(
      320,
      (host?.clientHeight || 0) || (stack?.clientHeight || 0) - 48 || 400
    );
    editorMd[kind] = editormd(id, {
      width: "100%",
      height: h,
      path: EDITORMD_LIB,
      markdown: text,
      tex: true,
      texPreview: true,
      watch: true,
      syncScrolling: "single",
      autoHeight: false,
      placeholder:
        kind === "statement" ? "题面 Markdown（支持 LaTeX）…" : "题解 Markdown（支持 LaTeX）…",
      onload: function () {
        this.resize();
        resolve(this);
      },
    });
  });
}

async function loadMarkdownPane(kind) {
  if (!currentProblemId) return;
  try {
    const art = await api(`/api/problems/${currentProblemId}/artifacts/${kind}`);
    mdCache[kind] = art.content_text || "";
  } catch {
    mdCache[kind] =
      kind === "statement"
        ? "# 题面\n\n（运行 STATEMENT 阶段或导入原题后点「刷新」）\n"
        : "# 题解\n\n（运行 EDITORIAL 阶段后点「刷新」）\n";
  }
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  await ensureEditorMd(kind, mdCache[kind]);
  setTimeout(() => resizeEditorMd(kind), 200);
}

async function saveMarkdownPane(kind) {
  if (!currentProblemId) return;
  mdCache[kind] = getEditorMdContent(kind);
  await api(`/api/problems/${currentProblemId}/artifacts/${kind}`, {
    method: "PUT",
    body: JSON.stringify({
      content_text: mdCache[kind],
      language: "markdown",
      author: "human",
    }),
  });
}

async function loadEvents() {
  if (!currentProblemId && !currentContestSetId) return;
  let url = "/api/monitor/events?limit=80";
  if (currentProblemId) url += `&problem_id=${currentProblemId}`;
  if (currentContestSetId) url += `&contest_set_id=${currentContestSetId}`;
  const rid = document.getElementById("filter-run-id")?.value?.trim();
  if (rid) url += `&run_id=${rid}`;
  const events = await api(url);
  const ul = document.getElementById("event-list");
  if (!ul) return;
  ul.innerHTML = "";
  const groups = new Map();
  for (const e of events) {
    const key = e.run_id || "_none";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(e);
  }
  for (const [runKey, items] of groups) {
    if (runKey !== "_none") {
      const h = document.createElement("li");
      h.className = "event-group-head";
      h.textContent = `run ${String(runKey).slice(0, 8)}… (${items.length})`;
      ul.appendChild(h);
    }
    for (const e of items) {
      const li = document.createElement("li");
      li.textContent = `${e.created_at?.slice(0, 19) || ""} [${e.source}] ${e.type}: ${e.message}`;
      ul.appendChild(li);
    }
  }
}

async function ensureSession() {
  if (sessionId) return sessionId;
  const s = await api("/api/sessions", {
    method: "POST",
    body: JSON.stringify({ title: "Web Session", problem_id: currentProblemId }),
  });
  sessionId = s.id;
  return sessionId;
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function formatChatHtml(text) {
  const raw = escapeHtml(text || "");
  if (typeof marked !== "undefined") {
    marked.setOptions({ gfm: true, breaks: true });
    return marked.parse(raw);
  }
  return raw.replace(/\n/g, "<br>");
}

function appendChat(role, text, toolsUsed) {
  const log = document.getElementById("chat-log");
  const wrap = document.createElement("div");
  wrap.className = `chat-msg-wrap ${role}`;
  const bubble = document.createElement("div");
  bubble.className = `chat-bubble chat-msg ${role}`;
  if (role === "assistant") {
    bubble.innerHTML = formatChatHtml(text);
  } else {
    bubble.textContent = text;
  }
  wrap.appendChild(bubble);
  log.appendChild(wrap);
  if (role === "assistant" && toolsUsed && toolsUsed.length) {
    const chips = document.createElement("div");
    chips.className = "chat-tools";
    for (const t of toolsUsed) {
      const span = document.createElement("span");
      span.className = "chat-tool-chip";
      const name = t.tool || "tool";
      span.textContent = t.args ? `${name}(${JSON.stringify(t.args).slice(0, 40)})` : name;
      span.title = t.result ? String(t.result).slice(0, 200) : "";
      chips.appendChild(span);
    }
    wrap.appendChild(chips);
  }
  log.scrollTop = log.scrollHeight;
}

function showChatSuggestions(actions) {
  const box = document.getElementById("chat-suggestions");
  if (!box) return;
  if (!actions?.length) {
    box.classList.add("hidden");
    box.innerHTML = "";
    return;
  }
  box.classList.remove("hidden");
  box.innerHTML =
    '<div class="chat-suggestions-label">建议下一步</div><div class="chat-suggestion-row"></div>';
  const row = box.querySelector(".chat-suggestion-row");
  for (const a of actions) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "chat-suggestion-btn";
    btn.textContent = a.label;
    btn.onclick = () => applySuggestedAction(a);
    row.appendChild(btn);
  }
}

async function applySuggestedAction(a) {
  const kind = a.kind || "chat";
  if (kind === "pane") {
    setWorkspacePane(a.message === "code" ? "code" : a.message);
    return;
  }
  if (kind === "link" && a.message) {
    window.open(a.message, "_blank", "noopener");
    return;
  }
  if (kind === "action") {
    await runStageUiAction({ action: a.message, label: a.label });
    return;
  }
  await sendAgentMessage(a.message || a.label);
}

async function sendAgentMessage(text) {
  const msg = (text || "").trim();
  if (!msg || (!currentProblemId && !currentContestSetId)) return;
  await ensureSession();
  appendChat("user", msg);
  document.getElementById("chat-input").value = "";
  showChatSuggestions([]);
  const body = { message: msg };
  if (currentProblemId) body.problem_id = currentProblemId;
  if (currentContestSetId) body.contest_set_id = currentContestSetId;
  const res = await api(`/api/sessions/${sessionId}/chat`, {
    method: "POST",
    body: JSON.stringify(body),
  });
  appendChat("assistant", res.assistant.content, res.tools_used);
  showChatSuggestions(res.suggested_actions || []);
  await refreshPipeline();
  await refreshAgentToolsPanel();
  if (parseRoute().tab === "monitor") await loadEvents();
}

/* ── Settings ── */
async function loadSettings() {
  const llm = await api("/api/workspace/llm-config");
  const active = llm.active_provider || "openai";
  document.getElementById("llm-active-provider").value = active;
  const lines = [];
  for (const [id, p] of Object.entries(llm.providers || {})) {
    lines.push(`${p.label}: ${p.configured ? p.api_key_masked : "未配置"} · ${p.model}`);
  }
  document.getElementById("llm-status").textContent = llm.any_configured
    ? `当前 ${llm.providers[active]?.label || active} · ${lines.join(" | ")}`
    : "未配置 LLM（仍可使用规则 Agent）";
  const defaults = {
    openai: "gpt-4o-mini",
    deepseek: "deepseek-chat",
    qwen: "qwen-plus",
    glm: "glm-4-flash",
  };
  for (const id of ["openai", "deepseek", "qwen", "glm"]) {
    const keyEl = document.getElementById(`llm-${id}-key`);
    const modelEl = document.getElementById(`llm-${id}-model`);
    if (keyEl) keyEl.value = "";
    if (modelEl) {
      const p = llm.providers?.[id];
      modelEl.placeholder = p?.model || p?.default_model || defaults[id];
      modelEl.value = "";
    }
  }
  const cfg = await api("/api/workspace/crawler-config");
  document.getElementById("crawler-status").textContent =
    `白名单: ${cfg.whitelist_hosts.join(", ")} · CF=${cfg.cf_cookie_configured ? cfg.cf_cookie_masked : "未配置"} · Polygon API=${cfg.polygon_api_configured ? cfg.polygon_api_key_masked : "未配置"}`;
  document.getElementById("cfg-cf-token").value = "";
  document.getElementById("cfg-luogu-cookie").value = "";
  document.getElementById("cfg-polygon-cookie").value = "";
  const pk = document.getElementById("cfg-polygon-api-key");
  const ps = document.getElementById("cfg-polygon-api-secret");
  if (pk) pk.value = "";
  if (ps) ps.value = "";
  document.getElementById("cfg-crawl-sites").value = (cfg.crawl_sites || []).join("\n");
}

async function saveCrawlerConfig() {
  const body = {
    crawl_sites: document
      .getElementById("cfg-crawl-sites")
      .value.split("\n")
      .map((x) => x.trim())
      .filter(Boolean),
  };
  const cf = document.getElementById("cfg-cf-token").value;
  const lg = document.getElementById("cfg-luogu-cookie").value;
  const poly = document.getElementById("cfg-polygon-cookie").value;
  if (cf) body.cf_cookie = cf;
  if (lg) body.luogu_cookie = lg;
  if (poly) body.polygon_cookie = poly;
  const pkey = document.getElementById("cfg-polygon-api-key")?.value;
  const psec = document.getElementById("cfg-polygon-api-secret")?.value;
  if (pkey) body.polygon_api_key = pkey;
  if (psec) body.polygon_api_secret = psec;
  await api("/api/workspace/crawler-config", { method: "PUT", body: JSON.stringify(body) });
  await loadSettings();
  alert("爬虫配置已保存到服务端");
}

/* ── Event bindings ── */
document.getElementById("btn-sidebar-toggle").onclick = () => {
  document.getElementById("app-shell").classList.toggle("sidebar-collapsed");
  layoutMonaco();
};

document.getElementById("btn-refresh").onclick = () => loadTree().then(onRoute);

document.getElementById("btn-new-problem").onclick = async () => {
  const title = prompt("题目标题", "New Problem");
  if (!title) return;
  const style = prompt("ICPC 或 OI", "ICPC") || "ICPC";
  const p = await api("/api/problems", {
    method: "POST",
    body: JSON.stringify({ title, contest_style: style }),
  });
  await loadTree();
  navigate(`/problem/${p.id}/workspace`);
};

document.getElementById("btn-new-contest-icpc").onclick = async () => {
  const name = prompt("套题名称", "New ICPC Set");
  if (!name) return;
  const cs = await api("/api/contest-sets", {
    method: "POST",
    body: JSON.stringify({ name, contest_style: "ICPC" }),
  });
  await loadTree();
  navigate(`/contest/${cs.id}`);
};

document.getElementById("btn-new-contest-oi").onclick = async () => {
  const name = prompt("套题名称", "New OI Set");
  if (!name) return;
  const cs = await api("/api/contest-sets", {
    method: "POST",
    body: JSON.stringify({ name, contest_style: "OI" }),
  });
  await loadTree();
  navigate(`/contest/${cs.id}`);
};

document.getElementById("btn-set-eval").onclick = async () => {
  if (!currentContestSetId) return;
  const report = await api(`/api/contest-sets/${currentContestSetId}/evaluate`, { method: "POST" });
  alert(report.summary);
  navigate(`/contest/${currentContestSetId}`);
};

document.getElementById("btn-set-approve").onclick = async () => {
  if (!currentContestSetId) return;
  const note = prompt("备注（可选）", "") || null;
  await api(`/api/contest-sets/${currentContestSetId}/approve-eval`, {
    method: "POST",
    body: JSON.stringify({ note }),
  });
  navigate(`/contest/${currentContestSetId}`);
};

document.getElementById("btn-slot-create").onclick = async () => {
  if (!currentContestSetId) return;
  const title = prompt(`槽位 ${currentSlotLabel} 标题`, "New Problem");
  if (!title) return;
  const rating = parseInt(prompt("Rating（可选）", "1500") || "", 10);
  const p = await api(
    `/api/contest-sets/${currentContestSetId}/slots/${currentSlotLabel}/create-problem`,
    {
      method: "POST",
      body: JSON.stringify({
        title,
        problem_type: "TRADITIONAL",
        rating: Number.isFinite(rating) ? rating : null,
      }),
    }
  );
  await loadTree();
  navigate(`/problem/${p.id}/workspace`);
};

document.getElementById("btn-import-check").onclick = async () => {
  if (!currentProblemId) return;
  const job = await api(`/api/problems/${currentProblemId}/import/check`, { method: "POST" });
  const verdictEl = document.getElementById("run-verdict");
  if (verdictEl) verdictEl.textContent = "import_check…";
  const done = await pollJob(job.id);
  const r = done.result_json || {};
  const msg = r.ok
    ? `import_check 通过 ${r.rounds ?? "?"} 轮`
    : `失败: ${jobResultMessage(done)}`;
  if (verdictEl) {
    verdictEl.textContent = r.ok ? "OK" : jobResultMessage(done);
    verdictEl.className = "verdict " + (r.ok ? "ok" : "fail");
  }
  const outEl = document.getElementById("run-output");
  if (outEl) outEl.textContent = JSON.stringify(r, null, 2);
  alert(msg);
  await refreshPipeline();
};

document.getElementById("btn-import-confirm").onclick = async () => {
  if (!currentProblemId) return;
  if (!confirm("确认已在原题平台提交或核对过该题？")) return;
  const submission_url = prompt("提交链接（选填）", "") || null;
  await api(`/api/problems/${currentProblemId}/import/confirm-submission`, {
    method: "POST",
    body: JSON.stringify({ submission_url }),
  });
  await refreshPipeline();
};

document.getElementById("btn-save").onclick = async () => {
  const kind = document.getElementById("artifact-kind").value;
  const language = document.getElementById("artifact-language").value;
  await api(`/api/problems/${currentProblemId}/artifacts/${kind}`, {
    method: "PUT",
    body: JSON.stringify({
      content_text: editor.getValue(),
      language: kind === "statement" ? null : language,
      author: "human",
    }),
  });
};

document.getElementById("btn-run").onclick = async () => {
  const program = document.getElementById("run-program").value;
  const body = {
    program,
    input: document.getElementById("run-input").value,
    use_editor_draft: document.getElementById("use-draft").checked,
    language: document.getElementById("artifact-language").value,
    use_checker: document.getElementById("use-checker").checked,
  };
  if (document.getElementById("use-draft").checked) {
    body.draft = { language: body.language, source: editor.getValue() };
  }
  const exp = document.getElementById("run-expected").value;
  if (exp) body.expected_out = exp;
  document.getElementById("run-verdict").textContent = "运行中…";
  const job = await api(`/api/problems/${currentProblemId}/run`, {
    method: "POST",
    body: JSON.stringify(body),
  });
  showRunResult(await pollJob(job.id));
};

document.getElementById("btn-compile").onclick = async () => {
  const body = {
    program: document.getElementById("run-program").value,
    use_editor_draft: document.getElementById("use-draft").checked,
    language: document.getElementById("artifact-language").value,
  };
  if (body.use_editor_draft) {
    body.draft = { language: body.language, source: editor.getValue() };
  }
  const job = await api(`/api/problems/${currentProblemId}/compile`, {
    method: "POST",
    body: JSON.stringify(body),
  });
  showRunResult(await pollJob(job.id));
};

document.getElementById("btn-compare").onclick = async () => {
  document.getElementById("run-verdict").textContent = "对比中…";
  const job = await api(`/api/problems/${currentProblemId}/run/compare`, {
    method: "POST",
    body: JSON.stringify({ input: document.getElementById("run-input").value }),
  });
  showRunResult(await pollJob(job.id));
};

document.getElementById("btn-stress-quick").onclick = async () => {
  const job = await api(`/api/problems/${currentProblemId}/stress/run`, {
    method: "POST",
    body: JSON.stringify({ mode: "quick" }),
  });
  const done = await pollJob(job.id);
  const r = done.result_json || {};
  alert(r.ok ? `对拍通过 ${r.rounds} 轮` : `失败: ${r.reason}`);
};

document.getElementById("btn-load-sample").onclick = () => {
  const s = currentSpec.samples?.[0];
  if (s) {
    document.getElementById("run-input").value = s.input || "";
    if (s.output) document.getElementById("run-expected").value = s.output;
  }
};

document.getElementById("btn-approve").onclick = async () => {
  const p = await api(`/api/problems/${currentProblemId}`);
  await api(`/api/problems/${currentProblemId}/stages/${p.current_stage}/approve`, {
    method: "POST",
    body: JSON.stringify({ note: document.getElementById("gate-note").value }),
  });
  navigate(`/problem/${currentProblemId}/workspace`);
};

document.getElementById("btn-dispatch").onclick = async () => {
  const p = await api(`/api/problems/${currentProblemId}`);
  const out = await api(`/api/problems/${currentProblemId}/dispatch`, {
    method: "POST",
    body: JSON.stringify({ stage_id: p.current_stage, reason: "web" }),
  });
  alert(out.dispatch.report?.summary || out.dispatch.hint || "已调度");
  navigate(`/problem/${currentProblemId}/workspace`);
};

document.getElementById("btn-interactive").onclick = async () => {
  const useDraft = document.getElementById("use-draft").checked;
  const body = { use_editor_draft: useDraft };
  if (useDraft) {
    body.draft_std = {
      language: document.getElementById("artifact-language").value,
      source: editor.getValue(),
    };
  }
  const job = await api(`/api/problems/${currentProblemId}/run/interactive`, {
    method: "POST",
    body: JSON.stringify(body),
  });
  showRunResult(await pollJob(job.id));
};

document.getElementById("btn-restore-artifact").onclick = async () => {
  if (!currentProblemId) return;
  const kind = document.getElementById("artifact-kind").value;
  const versions = await api(`/api/problems/${currentProblemId}/artifacts/${kind}/versions`);
  if (!versions.length) {
    alert("无历史版本");
    return;
  }
  const list = versions.map((v) => `v${v.version} (${v.author})`).join("\n");
  const ver = parseInt(prompt(`选择要恢复的版本号:\n${list}`, String(versions[0].version)), 10);
  if (!Number.isFinite(ver)) return;
  await api(`/api/problems/${currentProblemId}/artifacts/${kind}/restore`, {
    method: "POST",
    body: JSON.stringify({ version: ver }),
  });
  await loadArtifactContent(kind);
  alert(`已恢复为基于 v${ver} 的新版本`);
};

document.getElementById("btn-polygon-zip").onclick = () => {
  window.open(`/api/problems/${currentProblemId}/polygon/export`, "_blank");
};

document.getElementById("btn-polygon-attempt")?.addEventListener("click", async () => {
  if (!currentProblemId) return;
  const out = await api(`/api/problems/${currentProblemId}/polygon/attempt-upload`, {
    method: "POST",
  });
  const a = out.attempt || {};
  alert(a.instructions || JSON.stringify(a, null, 2));
  await refreshPipeline();
});

document.getElementById("btn-polygon-auto")?.addEventListener("click", async () => {
  if (!currentProblemId) return;
  const out = await api(`/api/problems/${currentProblemId}/polygon/auto-upload`, {
    method: "POST",
  });
  const f = out.form_upload || {};
  alert(f.instructions || JSON.stringify(f, null, 2));
  await refreshPipeline();
});

document.getElementById("btn-polygon-api-sync")?.addEventListener("click", async () => {
  if (!currentProblemId) return;
  const out = await api(`/api/problems/${currentProblemId}/polygon/api/sync`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  alert(
    out.ok
      ? `已同步 Polygon #${out.polygon_problem_id}，packages=${out.package_count ?? "?"}`
      : JSON.stringify(out, null, 2)
  );
  await refreshPipeline();
});

document.getElementById("btn-polygon-api-download")?.addEventListener("click", async () => {
  if (!currentProblemId) return;
  const out = await api(`/api/problems/${currentProblemId}/polygon/api/download-package`, {
    method: "POST",
    body: JSON.stringify({ package_type: "standard" }),
  });
  alert(out.ok ? `已下载: ${out.path}` : JSON.stringify(out, null, 2));
  await refreshPipeline();
});

document.getElementById("btn-package-sync")?.addEventListener("click", async () => {
  if (!currentProblemId) return;
  const out = await api(`/api/problems/${currentProblemId}/package/sync-polygon`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  alert(out.ok ? `同步完成: ${out.download?.path || out.local?.zip_path}` : JSON.stringify(out, null, 2));
  await refreshPipeline();
});

document.getElementById("btn-stress-interpret")?.addEventListener("click", async () => {
  if (!currentProblemId) return;
  const out = await api(`/api/problems/${currentProblemId}/stress/interpret`, { method: "POST" });
  const i = out.interpretation || {};
  alert(i.summary || JSON.stringify(i, null, 2));
});

document.getElementById("btn-polygon-import")?.addEventListener("click", async () => {
  if (!currentProblemId) return;
  const out = await api(`/api/problems/${currentProblemId}/polygon/import-package`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  alert(
    out.ok
      ? `已导入 ${out.imported_count} 项，新增样例 ${out.samples_added}`
      : JSON.stringify(out, null, 2)
  );
  await refreshPipeline();
});

document.getElementById("btn-counterexamples")?.addEventListener("click", async () => {
  if (!currentProblemId) return;
  const out = await api(`/api/problems/${currentProblemId}/counterexamples`);
  const items = out.items || [];
  if (!items.length) {
    alert("暂无归档反例");
    return;
  }
  const lines = items.slice(-5).map(
    (x, i) =>
      `#${i + 1} round=${x.round} ${x.reason}\n${(x.input || "").slice(0, 80)}`
  );
  alert(lines.join("\n\n"));
});

document.getElementById("btn-polygon-api-build")?.addEventListener("click", async () => {
  if (!currentProblemId) return;
  const out = await api(`/api/problems/${currentProblemId}/polygon/api/build-package`, {
    method: "POST",
    body: JSON.stringify({ full: false, verify: true, commit_first: true }),
  });
  alert(out.ok ? `buildPackage OK · Polygon #${out.polygon_problem_id}` : JSON.stringify(out, null, 2));
  await refreshPipeline();
});

document.getElementById("btn-polygon-prepare")?.addEventListener("click", async () => {
  if (!currentProblemId) return;
  const out = await api(`/api/problems/${currentProblemId}/polygon/prepare-upload`, {
    method: "POST",
  });
  const u = out.upload || {};
  alert(
    `${u.instructions || "已准备"}\n\n路径: ${u.zip_path || "-"}\n打开: ${u.polygon_url || "https://polygon.codeforces.com/"}`
  );
  await refreshPipeline();
});

document.getElementById("btn-dispatch-package").onclick = async () => {
  const out = await api(`/api/problems/${currentProblemId}/dispatch`, {
    method: "POST",
    body: JSON.stringify({ stage_id: "PACKAGE", reason: "web" }),
  });
  alert(out.dispatch.report?.summary || "已调度");
};

document.getElementById("btn-chat-send").onclick = async () => {
  await sendAgentMessage(document.getElementById("chat-input").value);
};

document.getElementById("btn-agent-clear").onclick = () => {
  document.getElementById("chat-log").innerHTML = "";
  showChatSuggestions([]);
  sessionId = null;
  refreshAgentToolsPanel();
};

document.getElementById("btn-save-llm-config").onclick = async () => {
  const body = {
    active_provider: document.getElementById("llm-active-provider").value,
  };
  for (const id of ["openai", "deepseek", "qwen", "glm"]) {
    const key = document.getElementById(`llm-${id}-key`)?.value?.trim();
    const model = document.getElementById(`llm-${id}-model`)?.value?.trim();
    if (key) body[`${id}_api_key`] = key;
    if (model) body[`${id}_model`] = model;
  }
  await api("/api/workspace/llm-config", { method: "PUT", body: JSON.stringify(body) });
  await loadSettings();
  alert("LLM 配置已保存");
};

document.getElementById("btn-save-crawler-config").onclick = saveCrawlerConfig;

document.getElementById("btn-crawl-import").onclick = async () => {
  const url = prompt("题目 URL（Codeforces / AtCoder / 洛谷）");
  if (!url) return;
  const title = prompt("标题（可选）", "") || null;
  const out = await api("/api/crawl/import", {
    method: "POST",
    body: JSON.stringify({ url, title }),
  });
  alert(`已排队导入 job=${out.job.id}`);
  await loadTree();
  navigate(`/problem/${out.problem.id}/workspace`);
};

document.getElementById("btn-export-events").onclick = () => {
  let u = "/api/monitor/events/export?limit=500";
  if (currentProblemId) u += `&problem_id=${currentProblemId}`;
  if (currentContestSetId) u += `&contest_set_id=${currentContestSetId}`;
  window.open(u, "_blank");
};

document.getElementById("filter-run-id")?.addEventListener("change", () => {
  loadEvents();
  if (parseRoute().tab === "monitor") startEventStream();
});

document.getElementById("btn-fetch-ac-std")?.addEventListener("click", async () => {
  if (!currentProblemId) return;
  const handle = prompt("Codeforces handle（可选，用于筛选 AC）", "") || null;
  try {
    const out = await api(`/api/problems/${currentProblemId}/import/fetch-std`, {
      method: "POST",
      body: JSON.stringify(handle ? { handle } : {}),
    });
    alert(`已拉取标程 v${out.fetch.version} · submission ${out.fetch.submission_id}`);
    await refreshPipeline();
  } catch (e) {
    alert(e.message || String(e));
  }
});

document.addEventListener("keydown", (e) => {
  if (e.key === "F9" && isWorkspaceRoute(parseRoute()) && activeWsPane === "code") {
    e.preventDefault();
    document.getElementById("btn-run").click();
  }
});

document.querySelectorAll("[data-ws-pane]").forEach((btn) => {
  btn.addEventListener("click", () => setWorkspacePane(btn.dataset.wsPane));
});

document.getElementById("btn-reload-statement")?.addEventListener("click", () =>
  loadMarkdownPane("statement")
);
document.getElementById("btn-reload-editorial")?.addEventListener("click", () =>
  loadMarkdownPane("editorial")
);
document.getElementById("btn-save-statement")?.addEventListener("click", async () => {
  try {
    await saveMarkdownPane("statement");
    alert("题面已保存");
  } catch (e) {
    alert(e.message || String(e));
  }
});
document.getElementById("btn-save-editorial")?.addEventListener("click", async () => {
  try {
    await saveMarkdownPane("editorial");
    alert("题解已保存");
  } catch (e) {
    alert(e.message || String(e));
  }
});

const chatInputEl = document.getElementById("chat-input");
if (chatInputEl) {
  chatInputEl.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" || e.shiftKey || e.isComposing) return;
    e.preventDefault();
    document.getElementById("btn-chat-send")?.click();
  });
}

document.querySelectorAll("[data-nav]").forEach((a) => {
  a.addEventListener("click", (e) => {
    e.preventDefault();
    navigate(a.getAttribute("href").replace("#", ""));
  });
});

(async () => {
  if (!location.hash) location.hash = "#/home";
  await onRoute();
})();
