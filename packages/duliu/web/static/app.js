const API = "";
const LS_CFG = "duliu.localConfig";

let currentProblemId = null;
let currentContestSetId = null;
let currentSlotLabel = "A";
let currentSpec = { samples: [] };
let currentProblem = null;
let sessionId = null;
let editor = null;
let pollTimer = null;
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
      pollTimer = setInterval(loadEvents, 3000);
    }
  }
}

function stopPollers() {
  if (pollTimer) clearInterval(pollTimer);
  if (stagePollTimer) clearInterval(stagePollTimer);
  pollTimer = null;
  stagePollTimer = null;
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
  document.getElementById("pipeline-title").textContent = p.title;
  document.getElementById("pipeline-stage").textContent = p.current_stage;
  document.getElementById("pipeline-style").textContent = `${p.contest_style} / ${p.problem_type}`;
  document.getElementById("pipeline-control").textContent = p.control_mode;
  await refreshStageTimeline("stage-timeline");
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
    return;
  }
  const p = currentProblem || (await api(`/api/problems/${currentProblemId}`));
  document.getElementById("agent-context").textContent =
    `${p.title} · 当前阶段 ${p.current_stage} · ${p.contest_style}`;
  renderAgentChips(p.current_stage);
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

async function pollJob(jobId) {
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
  for (const e of events) {
    const li = document.createElement("li");
    const run = e.run_id ? ` · ${String(e.run_id).slice(0, 8)}` : "";
    li.textContent = `${e.created_at?.slice(0, 19) || ""} [${e.source}]${run} ${e.type}: ${e.message}`;
    ul.appendChild(li);
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

function appendChat(role, text) {
  const log = document.getElementById("chat-log");
  const div = document.createElement("div");
  div.className = `chat-msg ${role}`;
  div.textContent = role === "user" ? text : text;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}

/* ── Settings ── */
async function loadSettings() {
  const s = await api("/api/workspace/secrets");
  document.getElementById("secret-status").textContent = s.openai_configured
    ? `OpenAI 已配置：${s.openai_masked}`
    : "OpenAI 未配置（仍可使用规则 Agent）";
  const cfg = JSON.parse(localStorage.getItem(LS_CFG) || "{}");
  document.getElementById("cfg-cf-token").value = cfg.cfToken || "";
  document.getElementById("cfg-polygon-cookie").value = cfg.polygonCookie || "";
  document.getElementById("cfg-crawl-sites").value = (cfg.crawlSites || []).join("\n");
}

function saveLocalConfig() {
  const cfg = {
    cfToken: document.getElementById("cfg-cf-token").value,
    polygonCookie: document.getElementById("cfg-polygon-cookie").value,
    crawlSites: document.getElementById("cfg-crawl-sites").value
      .split("\n")
      .map((x) => x.trim())
      .filter(Boolean),
  };
  localStorage.setItem(LS_CFG, JSON.stringify(cfg));
  alert("本地配置已保存");
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

document.getElementById("btn-polygon-zip").onclick = () => {
  window.open(`/api/problems/${currentProblemId}/polygon/export`, "_blank");
};

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
  appendChat("assistant", res.assistant.content);
  await refreshStageTimeline("agent-stage-timeline");
  if (parseRoute().tab === "monitor") await loadEvents();
};

document.getElementById("btn-agent-clear").onclick = () => {
  document.getElementById("chat-log").innerHTML = "";
  sessionId = null;
};

document.getElementById("btn-save-secrets").onclick = async () => {
  await api("/api/workspace/secrets", {
    method: "PUT",
    body: JSON.stringify({ openai_api_key: document.getElementById("openai-key").value || null }),
  });
  await loadSettings();
  alert("已保存");
};

document.getElementById("btn-save-local-config").onclick = saveLocalConfig;

document.getElementById("filter-run-id")?.addEventListener("change", loadEvents);

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
