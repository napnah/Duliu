const API = "";
let currentProblemId = null;
let currentSpec = { samples: [] };
let sessionId = null;
let editor = null;
let pollTimer = null;

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

function langForKind(kind) {
  if (kind === "std" || kind === "brute") return document.getElementById("artifact-language")?.value || "cpp";
  if (kind === "checker") return "python";
  if (kind === "statement" || kind === "editorial") return "markdown";
  if (kind === "spec" || kind === "idea") return "yaml";
  return "plaintext";
}

async function initMonaco() {
  return new Promise((resolve) => {
    require.config({
      paths: { vs: "https://cdn.jsdelivr.net/npm/monaco-editor@0.52.0/min/vs" },
    });
    require(["vs/editor/editor.main"], () => {
      editor = monaco.editor.create(document.getElementById("monaco-editor"), {
        value: "",
        language: "cpp",
        theme: "vs-dark",
        automaticLayout: true,
        fontSize: 14,
      });
      resolve();
    });
  });
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

async function loadTree() {
  const tree = await api("/api/tree");
  document.getElementById("tree-workspace").textContent = `工作区: ${tree.workspace.name}`;
  const csUl = document.getElementById("tree-contests");
  csUl.innerHTML = "";
  for (const c of tree.contest_sets) {
    const li = document.createElement("li");
    li.textContent = `${c.name} (${c.contest_style}, ${c.slot_count}槽)`;
    csUl.appendChild(li);
  }
  const ul = document.getElementById("tree-problems");
  ul.innerHTML = "";
  for (const p of tree.problems) {
    const li = document.createElement("li");
    li.textContent = `${p.title} [${p.contest_style}]`;
    li.dataset.id = p.id;
    li.onclick = () => selectProblem(p.id);
    if (p.id === currentProblemId) li.classList.add("active");
    ul.appendChild(li);
  }
}

async function selectProblem(id) {
  currentProblemId = id;
  sessionId = null;
  document.querySelectorAll("#tree-problems li").forEach((el) => {
    el.classList.toggle("active", el.dataset.id === id);
  });
  const p = await api(`/api/problems/${id}`);
  currentSpec = p.spec_json || { samples: [] };
  document.getElementById("problem-meta").classList.remove("hidden");
  document.getElementById("editor-section").classList.remove("hidden");
  document.getElementById("run-section").classList.remove("hidden");
  document.getElementById("problem-title").textContent = p.title;
  document.getElementById("problem-stage").textContent = p.current_stage;
  document.getElementById("problem-style").textContent = `${p.contest_style} / ${p.problem_type}`;
  document.getElementById("btn-interactive").style.display =
    p.problem_type === "INTERACTIVE" || p.problem_type === "COMMUNICATION" ? "inline-block" : "none";
  document.getElementById("problem-control").textContent = p.control_mode;
  document.getElementById("use-checker").checked = p.problem_type === "SUBMIT_ANSWER";
  await loadStages();
  await loadArtifactKinds();
  await loadEvents();
  await ensureSession();
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(loadEvents, 3000);
}

async function loadStages() {
  const stages = await api(`/api/problems/${currentProblemId}/stages`);
  const bar = document.getElementById("stages-bar");
  bar.innerHTML = "";
  const p = await api(`/api/problems/${currentProblemId}`);
  for (const s of stages) {
    const span = document.createElement("span");
    span.textContent = `${s.stage_id}: ${s.status}`;
    if (s.stage_id === p.current_stage) span.classList.add("current");
    if (s.status === "APPROVED") span.classList.add("approved");
    bar.appendChild(span);
  }
}

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
    const k = sel.value;
    if (k === "std" || k === "brute") document.getElementById("run-program").value = k;
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
  await loadEvents();
  alert("已保存");
};

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
  if (r.checker) text += "\n[checker]\n" + JSON.stringify(r.checker, null, 2);
  document.getElementById("run-output").textContent = text;
  const el = document.getElementById("run-verdict");
  const v = r.verdict || done.status;
  el.textContent = `Verdict: ${v}${r.match === false ? " (mismatch)" : ""}${r.match === true ? " (match)" : ""}`;
  el.className = "verdict " + (v === "OK" || v === "AC" ? "ok" : "fail");
}

document.getElementById("btn-run").onclick = async () => {
  const program = document.getElementById("run-program").value;
  const input = document.getElementById("run-input").value;
  const expected = document.getElementById("run-expected").value;
  const useDraft = document.getElementById("use-draft").checked;
  const useChecker = document.getElementById("use-checker").checked;
  const language = document.getElementById("artifact-language").value;
  const body = { program, input, use_editor_draft: useDraft, language, use_checker: useChecker };
  if (useDraft) body.draft = { language, source: editor.getValue() };
  if (expected) body.expected_out = expected;
  document.getElementById("run-verdict").textContent = "运行中…";
  const job = await api(`/api/problems/${currentProblemId}/run`, {
    method: "POST",
    body: JSON.stringify(body),
  });
  showRunResult(await pollJob(job.id));
  await loadEvents();
};

document.getElementById("btn-compile").onclick = async () => {
  const program = document.getElementById("run-program").value;
  const useDraft = document.getElementById("use-draft").checked;
  const language = document.getElementById("artifact-language").value;
  const body = { program, use_editor_draft: useDraft, language };
  if (useDraft) body.draft = { language, source: editor.getValue() };
  const job = await api(`/api/problems/${currentProblemId}/compile`, {
    method: "POST",
    body: JSON.stringify(body),
  });
  showRunResult(await pollJob(job.id));
};

document.getElementById("btn-compare").onclick = async () => {
  const input = document.getElementById("run-input").value;
  document.getElementById("run-verdict").textContent = "对比运行中…";
  const job = await api(`/api/problems/${currentProblemId}/run/compare`, {
    method: "POST",
    body: JSON.stringify({ input }),
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
  alert(r.ok ? `对拍通过 ${r.rounds} 轮` : `对拍失败: ${r.reason}`);
  await loadEvents();
};

document.getElementById("btn-load-sample").onclick = () => {
  const s = currentSpec.samples && currentSpec.samples[0];
  if (s) {
    document.getElementById("run-input").value = s.input || "";
    if (s.output) document.getElementById("run-expected").value = s.output;
  }
};

document.getElementById("btn-approve").onclick = async () => {
  const p = await api(`/api/problems/${currentProblemId}`);
  const note = document.getElementById("gate-note").value;
  await api(`/api/problems/${currentProblemId}/stages/${p.current_stage}/approve`, {
    method: "POST",
    body: JSON.stringify({ note }),
  });
  await selectProblem(currentProblemId);
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
  document.getElementById("run-verdict").textContent = "交互运行中…";
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
  alert(out.dispatch.report?.summary || JSON.stringify(out.dispatch));
  await selectProblem(currentProblemId);
};

document.getElementById("btn-dispatch").onclick = async () => {
  const p = await api(`/api/problems/${currentProblemId}`);
  const out = await api(`/api/problems/${currentProblemId}/dispatch`, {
    method: "POST",
    body: JSON.stringify({ stage_id: p.current_stage, reason: "web" }),
  });
  alert(out.dispatch.report?.summary || out.dispatch.hint || "已调度");
  await selectProblem(currentProblemId);
};

document.getElementById("btn-refresh").onclick = () => loadTree();

document.getElementById("btn-new-problem").onclick = async () => {
  const title = prompt("题目标题", "New Problem");
  if (!title) return;
  const style = prompt("contest_style: ICPC 或 OI", "ICPC") || "ICPC";
  await api("/api/problems", {
    method: "POST",
    body: JSON.stringify({ title, contest_style: style }),
  });
  await loadTree();
};

document.getElementById("btn-new-contest-icpc").onclick = async () => {
  const name = prompt("套题名称", "New ICPC Set");
  if (!name) return;
  await api("/api/contest-sets", { method: "POST", body: JSON.stringify({ name, contest_style: "ICPC" }) });
  await loadTree();
};

document.getElementById("btn-new-contest-oi").onclick = async () => {
  const name = prompt("套题名称", "New OI Set");
  if (!name) return;
  await api("/api/contest-sets", { method: "POST", body: JSON.stringify({ name, contest_style: "OI" }) });
  await loadTree();
};

document.getElementById("btn-settings").onclick = async () => {
  const s = await api("/api/workspace/secrets");
  document.getElementById("secret-status").textContent = s.openai_configured
    ? `已配置: ${s.openai_masked}`
    : "未配置 OpenAI Key（仍可使用规则 Session）";
  document.getElementById("dlg-settings").showModal();
};

document.getElementById("btn-close-settings").onclick = () => document.getElementById("dlg-settings").close();

document.getElementById("btn-save-secrets").onclick = async () => {
  const key = document.getElementById("openai-key").value;
  await api("/api/workspace/secrets", {
    method: "PUT",
    body: JSON.stringify({ openai_api_key: key || null }),
  });
  document.getElementById("dlg-settings").close();
};

function appendChat(role, text) {
  const log = document.getElementById("chat-log");
  const div = document.createElement("div");
  div.className = `chat-msg ${role}`;
  div.textContent = (role === "user" ? "你: " : "Agent: ") + text;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}

document.getElementById("btn-chat-send").onclick = async () => {
  const text = document.getElementById("chat-input").value.trim();
  if (!text || !currentProblemId) return;
  await ensureSession();
  appendChat("user", text);
  document.getElementById("chat-input").value = "";
  const res = await api(`/api/sessions/${sessionId}/chat`, {
    method: "POST",
    body: JSON.stringify({ message: text, problem_id: currentProblemId }),
  });
  appendChat("assistant", res.assistant.content);
  await loadEvents();
  await loadStages();
};

async function loadEvents() {
  if (!currentProblemId) return;
  let url = `/api/monitor/events?problem_id=${currentProblemId}&limit=50`;
  const rid = document.getElementById("filter-run-id").value.trim();
  if (rid) url += `&run_id=${rid}`;
  const events = await api(url);
  const ul = document.getElementById("event-list");
  ul.innerHTML = "";
  for (const e of events) {
    const li = document.createElement("li");
    const run = e.run_id ? ` run:${String(e.run_id).slice(0, 8)}` : "";
    li.textContent = `[${e.source}]${run} ${e.type}: ${e.message}`;
    ul.appendChild(li);
  }
}

document.getElementById("filter-run-id").addEventListener("change", loadEvents);

(async () => {
  await initMonaco();
  await loadTree();
  const tree = await api("/api/tree");
  if (tree.problems.length) await selectProblem(tree.problems[0].id);
})();
