# Web 工件编辑、语法高亮与一键对拍（与「沙箱」的关系）

> 决策：**D-13**（Web 编辑器）、**D-14**（标程一键对拍）、**D-16**（按输入一键运行）

## 1. 先分清两件事

| 概念 | 做什么 | 在哪里 |
|------|--------|--------|
| **Web 工件编辑** | 改题面、标程、gen、checker 等 **文本内容** | 浏览器 → API → Postgres `artifacts` |
| **沙箱（Runner）** | **编译、运行** 标程/暴力/对拍（不可信代码） | Linux Docker + Isolate，**与编辑 UI 无关** |

**结论**：可以在 Web 端修改任意已登记的工件文档；**高亮由前端编辑器库完成**；保存后点「对拍」才进入沙箱执行，不会在浏览器里 `exec` 用户代码。

---

## 2. Web 端编辑任意工件（D-13）

### 2.1 范围

单题 `problem_id` 下，所有 `artifacts.kind` 均在 Web **工件面板** 打开，例如：

| kind / 路径习惯 | 语言模式 |
|-----------------|----------|
| `statement` | Markdown |
| `std` / `brute` | C++ / Python / Java（按扩展名或 spec） |
| `gen` | Python / C++ |
| `validator` / `checker` / `interactor` | C++ |
| `spec` / `idea` | YAML |
| `editorial` | Markdown |

### 2.2 语法高亮（调用现有库）

**已锁定**：前端使用 **[Monaco Editor](https://github.com/microsoft/monaco-editor)**（与 VS Code 同源）。

| 能力 | 实现 |
|------|------|
| 高亮 | 内置 `cpp` / `python` / `java` / `markdown` / `yaml` |
| 多文件 | 左侧工件树切换，`uri` 区分未保存草稿 |
| 保存 | `PUT /api/problems/{id}/artifacts/{kind}` → 新版本 + `sha256` |
| 未保存提示 | 切换文件 / 对拍前拦截 |

可选备选：CodeMirror 6（更轻）；**默认 Monaco**，便于后续与 VS Code 扩展体验一致。

### 2.3 与 `control_mode`

| 模式 | 编辑 |
|------|------|
| `HUMAN` | 用户改，Agent 不自动覆盖当前草稿 |
| `AGENT` | Agent 可写新版本；Web 提示「Agent 可能更新，请刷新」 |
| `HYBRID` | 用户改后保存即锁定该 kind 直至 dispatch |

---

## 3. 标程（如 `std.cpp`）改完一键对拍（D-14）

### 3.1 交互

在 `std` 编辑器工具栏：

```
[保存]  [编译检查]  [一键对拍 ▼]
                          ├─ 快速对拍（1e3 轮，默认）
                          └─ 完整对拍（1e5 轮，进 S5 正式流程）
```

### 3.2 后端流程

```
用户点击「一键对拍」
  → 若未保存：先保存 artifacts.std 当前草稿
  → POST /api/problems/{id}/stress/run
        body: { mode: "quick"|"full", std_version, brute_version, gen_version }
  → JobFacade.enqueue_stress（Worker + Runner 沙箱）
  → events + Monitor 实时进度
  → 完成：stress 摘要（AC/WA/TLE）、反例下载链接
```

**不绕过严格判定**：仍为 std vs brute，**字节比较**或 **checker/SPJ**（与 §13.3 一致）。

### 3.3 前置条件（API 校验）

| 条件 | 说明 |
|------|------|
| 存在 `brute` | 无暴力则禁止对拍（非原创见 non-original 文档，可放宽为「极简暴力」但仍必须有） |
| 存在 `gen` 或预生成 `tests` | quick 模式可用「仅样例 + 小随机」 |
| Linux Runner 健康 | Worker 就绪 |

正式阶段 **S5 Gate** 仍以「完整对拍 + 人工 approve」为准；一键对拍用于 **编辑迭代**，不等价跳过 Gate。

---

## 4. 按输入一键运行（D-16）

在浏览器中输入（或选择）**测试输入**，点击 **运行**，由 **Runner 沙箱** 执行当前程序并 **把结果返回到 Web**（类似本地「自定义测试」/ Codeforces Custom Test）。

### 4.1 UI（工件编辑器下方「运行」面板）

```
运行程序: [标程 std ▼] [暴力 brute]     时限/内存: 来自 spec（只读）
输入 Input ─────────────────────────────  [从样例加载 ▼]
│ （Monaco 或 textarea，纯文本 stdin）      │
└────────────────────────────────────────
[运行]  [清空]     编译: ○ 待运行 / ● 成功 / ● 失败

输出 Output
│ stdout（只读 Monaco，可复制）              │
│ stderr                                   │
└────────────────────────────────────────
状态: AC | WA | TLE | RTE | CE    用时: 42ms   内存: 3.2MB   退出码: 0
```

- 打开 `std.cpp` 时默认选中 **标程**；打开 `brute.*` 时默认 **暴力**。
- **从样例加载**：下拉选择已保存的 `tests/*.in` 或题面样例输入。
- 若编辑器有未保存修改：运行前提示 **「先保存」** 或勾选 **「用当前草稿运行一次」**（见 4.3）。

### 4.2 后端流程

```
用户点击 [运行]
  → POST /api/problems/{id}/run
  → JobFacade.enqueue_run_single（Worker → Runner 沙箱）
       · 编译（若二进制不存在或源码版本变化）
       · 写入 input.txt，isolate 跑单进程，网络 OFF
       · 采集 stdout / stderr / 退出码 / 用时 / 内存
  → job 完成：结果 JSON 写入 job.result + event runner.run_single.done
  → Web：轮询 GET /api/jobs/{id} 或 WebSocket 推送，填充 Output 面板
```

**与对拍区别**：只跑 **一个程序 + 一份输入**，不跑 brute 对照；用于调试标程/暴力本身。

### 4.3 请求体（API）

```json
{
  "program": "std",
  "artifact_version": 12,
  "input": "3\n1 2 3\n",
  "use_editor_draft": false,
  "draft": null
}
```

| 字段 | 说明 |
|------|------|
| `program` | `std` \| `brute`（M3+ 可扩展 `checker` 测多解样例） |
| `artifact_version` | 指定已保存版本；省略则用 latest |
| `input` | stdin 原文，最大 **1MB**（可配置） |
| `use_editor_draft` | `true` 时用 `draft` 临时编译运行，**不**写入 artifacts 表 |
| `draft` | `{ "language": "cpp", "source": "..." }` |

### 4.4 响应体（返回到浏览器）

```json
{
  "job_id": "uuid",
  "status": "done",
  "result": {
    "verdict": "OK",
    "exit_code": 0,
    "time_ms": 42,
    "memory_kb": 3276,
    "stdout": "6\n",
    "stderr": "",
    "compile_log": "",
    "truncated": false
  }
}
```

| verdict | 含义 |
|---------|------|
| `OK` | 正常结束且在时限内 |
| `CE` | 编译错误，`compile_log` 有内容 |
| `RTE` | 运行错误 / 非零退出 |
| `TLE` | 超时 |
| `OLE` | 输出超过上限（如 10MB） |

输出过大时 `truncated: true`，完整日志走 `GET /api/jobs/{id}/logs`。

### 4.5 沙箱约束（与全局一致）

| 项 | 规则 |
|----|------|
| 执行位置 | 仅 Linux Docker + Isolate |
| 网络 | 关闭 |
| 时限/内存 | `problems.spec` 中该题限制 |
| 并发 | 单题同时 `run_single` Job 上限（如 2），防刷 |
| 代码来源 | 必须是本题 `problem_id` 下 std/brute，禁止任意路径 |

### 4.6 可选增强（M2+）

- **对比模式**：同一 input 同时跑 std + brute，返回两份输出并排（仍非 full stress）。
- **期望输出**：用户填 `expected_out`，Runner 做 **字节比较** 显示 WA/AC（不替代正式 checker）。

### 4.7 前置条件

- 程序源码可编译（或 Python/Java 可解释执行）。
- Runner 服务健康。
- **不要求** 已有 gen / 对拍通过（单点运行独立）。

---

## 5. 沙箱在本需求中的角色（不变）

- 编辑：零沙箱，纯 HTTP + DB。  
- 对拍/编译：**必须**进 Runner 容器 + Isolate。  
- Web 永远收不到「在浏览器里跑 cpp」的能力。

---

## 6. API 摘要（实现期）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/problems/{id}/artifacts` | 列表 + 最新版本元数据 |
| GET | `/api/problems/{id}/artifacts/{kind}` | 拉取内容 |
| PUT | `/api/problems/{id}/artifacts/{kind}` | 保存新版本 |
| POST | `/api/problems/{id}/compile` | 仅编译（`program`: std/brute） |
| POST | `/api/problems/{id}/run` | **按输入一键运行（D-16）** |
| POST | `/api/problems/{id}/stress/run` | 一键对拍 |
| GET | `/api/jobs/{job_id}` | 任务状态 + **run/stress 结果 JSON** |
| GET | `/api/jobs/{job_id}/logs` | 完整 stdout/stderr/编译日志 |

---

## 7. 里程碑

| 里程碑 | 交付 |
|--------|------|
| M1 | Monaco 编辑 + **运行面板（stdin → 沙箱 → 返回输出）** + quick stress |
| M2 | 草稿运行、`std+brute` 对比运行、期望输出 AC/WA |
| M3 | checker/interactor 相关运行模式 + SPJ 对拍 |
