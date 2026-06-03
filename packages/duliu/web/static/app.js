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

const VIEWS = [
  "view-home",
  "view-contest",
  "view-pipeline",
  "view-editor",
  "view-agent",
  "view-monitor",
  "view-settings",
];

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
    const tab = parts[2] || "pipeline";
    return { page: "problem", problemId: parts[1], tab };
  }
  return { page: "home" };
}

function navigate(path) {
  const p = path.startsWith("#") ? path.slice(1) : path;
  location.hash = p.startsWith("/") ? p : `/${p}`;
}

function showView(viewId) {
  for (const id of VIEWS) {
    document.getElementById(id).classList.toggle("hidden", id !== viewId);
  }
  const shell = document.getElementById("app-shell");
  const isEditor = viewId === "view-editor";
  const isSettings = viewId === "view-settings";
  shell.classList.toggle("sidebar-collapsed", isEditor || viewId === "view-agent");
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
    parts.push(` / <a href="#/problem/${route.problemId}/pipeline">${currentProblem.title}</a>`);
    const tabNames = { pipeline: "流水线", editor: "编辑器", agent: "Agent", monitor: "监控" };
    parts.push(` / ${tabNames[route.tab] || route.tab}`);
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
    a.classList.toggle("active", tab === route.tab);
    a.href = `#/problem/${route.problemId}/${tab}`;
    a.onclick = (e) => {
      e.preventDefault();
      navigate(`/problem/${route.problemId}/${tab}`);
    };
  });
}

async function onRoute() {
  const route = parseRoute();
  updateBreadcrumb(route);
  updateProblemSubnav(route);
  stopPollers();

  if (route.page === "settings") {
    showView("view-settings");
    await loadSettings();
    return;
  }

  if (route.page === "home") {
    showView("view-home");
    await loadTree();
    renderHomeRecent();
    return;
  }

  if (route.page === "contest") {
    showView("view-contest");
    await loadTree();
    await openContest(route.contestId);
    return;
  }

  if (route.page === "problem") {
    await loadTree();
    await openProblem(route.problemId);
    const tab = route.tab || "pipeline";
    if (tab === "pipeline") {
      showView("view-pipeline");
      await refreshPipeline();
      stagePollTimer = setInterval(refreshPipeline, 5000);
    } else if (tab === "editor") {
      showView("view-editor");
      await ensureMonaco();
      await loadArtifactKinds();
      layoutMonaco();
    } else if (tab === "agent") {
      showView("view-agent");
      await refreshAgentContext();
      await refreshStageTimeline("agent-stage-timeline");
      stagePollTimer = setInterval(() => refreshStageTimeline("agent-stage-timeline"), 5000);
    } else if (tab === "monitor") {
      showView("view-monitor");
      await loadEvents();
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
    li.onclick = () => navigate(`/contest/${c.id}`);
    csUl.appendChild(li);
  }
  const ul = document.getElementById("tree-problems");
  ul.innerHTML = "";
  for (const p of treeCache.problems) {
    const li = document.createElement("li");
    li.textContent = p.title;
    li.dataset.id = p.id;
    li.classList.toggle("active", p.id === currentProblemId);
    li.onclick = () => navigate(`/problem/${p.id}/pipeline`);
    ul.appendChild(li);
  }
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
    d.onclick = () => navigate(`/problem/${p.id}/agent`);
    box.appendChild(d);
  }
}

/* ── Contest ── */
async function openContest(id) {
  currentContestSetId = id;
  currentProblemId = null;
  sessionId = null;
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

async function renderLanggraphHistory(listId, metaId, data) {
  const ul = document.getElementById(listId);
  const meta = document.getElementById(metaId);
  if (!ul) return;
  ul.innerHTML = "";
  if (!data?.enabled) {
    if (meta) meta.textContent = "LangGraph 未启用";
    ul.innerHTML = "<li>—</li>";
    return;
  }
  if (meta) meta.textContent = `thread: ${data.thread_id || "—"}`;
  const hist = data.history || [];
  if (!hist.length) {
    ul.innerHTML = "<li>暂无 checkpoint</li>";
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

async function refreshContestLanggraphHistory(contestSetId) {
  try {
    const data = await api(`/api/contest-sets/${contestSetId}/langgraph/history`);
    await renderLanggraphHistory("contest-lg-history", "contest-lg-meta", data);
  } catch {
    await renderLanggraphHistory("contest-lg-history", "contest-lg-meta", { enabled: false });
  }
}

async function refreshPipelineLanggraphHistory() {
  if (!currentProblemId) return;
  try {
    const data = await api(`/api/problems/${currentProblemId}/langgraph/history`);
    await renderLanggraphHistory("pipeline-lg-history", "pipeline-lg-meta", data);
  } catch {
    await renderLanggraphHistory("pipeline-lg-history", "pipeline-lg-meta", { enabled: false });
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
      if (s.problem_id) navigate(`/problem/${s.problem_id}/pipeline`);
    };
    tbody.appendChild(tr);
  }
}

/* ── Problem ── */
async function openProblem(id) {
  currentProblemId = id;
  sessionId = null;
  currentProblem = await api(`/api/problems/${id}`);
  currentSpec = currentProblem.spec_json || { samples: [] };
  currentContestSetId = currentProblem.contest_set_id || null;
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
  const impPanel = document.getElementById("import-panel");
  if (p.originality === "NON_ORIGINAL") {
    impPanel.classList.remove("hidden");
    const imp = graph.import || {};
    document.getElementById("import-url").textContent = imp.problem_url || "（无 URL）";
    const chk = imp.agent_checklist;
    const chkHint = chk?.steps?.length ? ` · 清单 ${chk.steps.length} 项` : "";
    document.getElementById("import-status-line").textContent =
      `导入: ${imp.status || "-"} · import_check: ${imp.import_check_ok ? "通过" : "未通过"} · 提交确认: ${imp.submission_confirmed ? "是" : "否"}${chkHint}`;
    const link = document.getElementById("import-open-url");
    if (imp.problem_url) link.href = imp.problem_url;
    document.getElementById("import-confirm-box").checked = !!imp.submission_confirmed;
  } else {
    impPanel.classList.add("hidden");
  }
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
  renderAgentChips(p.current_stage);
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

function renderAgentChips(stage) {
  const box = document.getElementById("agent-chips");
  box.innerHTML = "";
  const cmds = [
    `dispatch ${stage}`,
    `approve ${stage}`,
    "状态",
    "对拍",
    "最近事件",
    "dispatch PACKAGE",
  ];
  if (currentContestSetId) cmds.push("套题状态", "套题评估");
  for (const c of cmds) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = c;
    b.onclick = () => {
      document.getElementById("chat-input").value = c;
      document.getElementById("btn-chat-send").click();
    };
    box.appendChild(b);
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

function showRunResult(done) {
  const r = done.result_json || {};
  let text = (r.stdout || "") + (r.stderr ? "\n[stderr]\n" + r.stderr : "");
  if (r.compile_log) text += "\n[compile]\n" + r.compile_log;
  if (r.std) text += "\n[std]\n" + JSON.stringify(r.std, null, 2);
  if (r.brute) text += "\n[brute]\n" + JSON.stringify(r.brute, null, 2);
  document.getElementById("run-output").textContent = text;
  const el = document.getElementById("run-verdict");
  const v = r.verdict || done.status;
  el.textContent = v;
  el.className = "verdict " + (v === "OK" || v === "AC" ? "ok" : "fail");
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

function appendChat(role, text, toolsUsed) {
  const log = document.getElementById("chat-log");
  const div = document.createElement("div");
  div.className = `chat-msg ${role}`;
  div.textContent = text;
  log.appendChild(div);
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
    log.appendChild(chips);
  }
  log.scrollTop = log.scrollHeight;
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
  navigate(`/problem/${p.id}/pipeline`);
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
  navigate(`/problem/${p.id}/pipeline`);
};

document.getElementById("btn-goto-editor").onclick = () => {
  if (currentProblemId) navigate(`/problem/${currentProblemId}/editor`);
};
document.getElementById("btn-goto-agent").onclick = () => {
  if (currentProblemId) navigate(`/problem/${currentProblemId}/agent`);
};

document.getElementById("btn-import-check").onclick = async () => {
  if (!currentProblemId) return;
  const job = await api(`/api/problems/${currentProblemId}/import/check`, { method: "POST" });
  document.getElementById("run-verdict")?.textContent && (document.getElementById("run-verdict").textContent = "import_check…");
  const done = await pollJob(job.id);
  alert(done.result_json?.ok ? `import_check 通过 ${done.result_json.rounds} 轮` : `失败: ${done.result_json?.reason}`);
  await refreshPipeline();
};

document.getElementById("btn-import-confirm").onclick = async () => {
  if (!currentProblemId) return;
  if (!document.getElementById("import-confirm-box").checked) {
    alert("请勾选确认");
    return;
  }
  await api(`/api/problems/${currentProblemId}/import/confirm-submission`, {
    method: "POST",
    body: JSON.stringify({
      submission_url: document.getElementById("import-submission-url").value || null,
    }),
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
  navigate(`/problem/${currentProblemId}/pipeline`);
};

document.getElementById("btn-dispatch").onclick = async () => {
  const p = await api(`/api/problems/${currentProblemId}`);
  const out = await api(`/api/problems/${currentProblemId}/dispatch`, {
    method: "POST",
    body: JSON.stringify({ stage_id: p.current_stage, reason: "web" }),
  });
  alert(out.dispatch.report?.summary || out.dispatch.hint || "已调度");
  navigate(`/problem/${currentProblemId}/pipeline`);
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
  const text = document.getElementById("chat-input").value.trim();
  if (!text || (!currentProblemId && !currentContestSetId)) return;
  await ensureSession();
  appendChat("user", text);
  document.getElementById("chat-input").value = "";
  const body = { message: text };
  if (currentProblemId) body.problem_id = currentProblemId;
  if (currentContestSetId) body.contest_set_id = currentContestSetId;
  const res = await api(`/api/sessions/${sessionId}/chat`, {
    method: "POST",
    body: JSON.stringify(body),
  });
  appendChat("assistant", res.assistant.content, res.tools_used);
  await refreshStageTimeline("agent-stage-timeline");
  await refreshAgentToolsPanel();
  if (parseRoute().tab === "monitor") await loadEvents();
};

document.getElementById("btn-agent-clear").onclick = () => {
  document.getElementById("chat-log").innerHTML = "";
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
  navigate(`/problem/${out.problem.id}/pipeline`);
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
  if (e.key === "F9" && parseRoute().tab === "editor") {
    e.preventDefault();
    document.getElementById("btn-run").click();
  }
});

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
