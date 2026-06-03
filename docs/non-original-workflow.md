# 非原创题（NON_ORIGINAL）工作流：网络标程、严格对拍、原题提交

> 决策：**D-15** · 仅个人学习；系统 **强制** 关联原题并督促用户在原平台提交。

## 1. 目标

| 需求 | Duliu 做法 |
|------|------------|
| 使用网络上已有 **标程** 作为起点 | IMPORT 阶段爬取或用户粘贴；存 `artifacts.std` + 来源元数据 |
| 依然 **严格对拍** | std vs brute，字节比较或 checker；在 Runner 沙箱执行 |
| 对拍程序 **简单、易实现** | 非原创默认 **简化 stress 配置** + 必须有 brute |
| **强烈要求用户在原题提交** | 原题链接常驻 UI；IMPORT/Gate 强制确认「已在原题平台提交」 |

---

## 2. IMPORT 阶段数据

`import.json` / `problems` 扩展字段：

```yaml
originality: NON_ORIGINAL
source:
  platform: codeforces | atcoder | luogu | other
  problem_url: "https://..."      # 必填
  problem_id: "CF1234A"           # 平台题号
  contest_url: optional
std_provenance:
  kind: crawler | user_paste | official_editorial_code
  url: optional                   # 标程来源页
  license_note: "user_provided"   # 学习用途自述
submission_requirement:
  required: true
  user_confirmed: false           # 用户勾选后 true
  submission_url: optional        # 用户填写的提交链接
  handle: optional
```

---

## 3. 网络标程的获取

| 方式 | 说明 |
|------|------|
| **爬虫 + 用户 Token** | 在 Web 设置配置 Cookie/Token 后，尝试拉取 **用户账号** 的 AC 提交（遵守 ToS，仅学习） |
| **用户粘贴** | Web 编辑器粘贴标程，手动填写 `std_provenance` |
| **题解代码** | 仅作参考草稿，**不能**替代对拍；须标注明来源 |

**不承诺**一定能自动拿到标程；拿不到时 IMPORT Gate 要求用户 **手动粘贴 std** 或放弃导入。

---

## 4. 严格对拍（简化但不变严）

### 4.1 非原创默认策略（简单）

| 组件 | 要求 |
|------|------|
| **std** | 来自网络或用户；版本入库 |
| **brute** | **必填**（可 Agent 生成「极简暴力」：Python、仅覆盖小数据约束） |
| **gen** | 优先 **手写样例** + `gen.py` 小范围随机（如 n≤2000 轮）；避免复杂构造 |
| **validator** | 推荐有；无则 IMPORT 时从题面约束生成最小 validator |

### 4.2 对拍模式

| 模式 | 轮数 | 用途 |
|------|------|------|
| `import_check` | 500~2000 | IMPORT 后自动跑，验证「网络标程 vs 暴力」 |
| `quick` | 1e3 | Web「一键对拍」 |
| `full` | 1e5 | S5 正式验收 |

判定规则与全局一致：**严格比 out** 或 **SPJ**；WA 必须归档。

### 4.3 若网络标程错误

- `import_check` 失败 → 状态 `IMPORT_FAILED`，Monitor 给反例。  
- 用户修正 std 或 brute / 约束后重跑；**不得**在未对拍通过时标记 IMPORT 通过。

---

## 5. 原题提交（强制人机约束）

### 5.1 UI

- 单题页顶部 **原题卡片**：平台图标、`problem_url`、[在原题网站打开]（新标签）。  
- **提交确认**（IMPORT 或进入 S3 之前必须完成）：

```
☐ 我已在原题平台（Codeforces/AtCoder/…）提交或核对过该题
   提交链接（选填）：[________________]
   用户名（选填）：[________________]
[确认并继续]
```

### 5.2 规则

| 规则 | 说明 |
|------|------|
| `submission_requirement.required = true` | 非原创题默认开启，配置不可关（workspace 级） |
| 未确认 | **禁止** `approve IMPORT`、禁止 `dispatch` 到 SOLUTION 之后阶段 |
| 仅本地 AC | **不算** 完成；必须勾选原题提交声明（诚信声明 + 学习规范） |
| 记录审计 | `user_confirmed_at`、`submission_url` 写入 DB，供日后自查 |

### 5.3 与「使用网络标程」的关系

- 网络标程 = Duliu 内验题起点；**原题提交** = 用户到 **官方题库** 做题/交题，避免只在本系统「抄答案」而不做原题。

---

## 6. 阶段路径（非原创）

```
IMPORT（爬题面 + 尝试标程 + import_check 对拍）
  → Gate：对拍通过 + 原题提交确认
STATEMENT（可仅校对格式）
  → SOLUTION（若无 brute 则生成极简 brute）
  → GENERATOR（简化 gen）
  → STRESS（full）
  → ADVERSARIAL → …
```

---

## 7. 合规提示（Web 展示）

IMPORT 页固定文案：

- 仅用于 **个人学习**；不得用于公开比赛或商用转载。  
- 标程/题面版权归原平台与作者所有。  
- 请先在 **原题链接** 提交后再在 Duliu 内改编/验题。

---

## 8. 里程碑

| 里程碑 | 交付 |
|--------|------|
| M5 | 爬虫 IMPORT + import_check + 原题提交 Gate |
| M1 可先做 | 用户粘贴 std + 原题 URL + 手动确认 + quick stress（不依赖爬虫） |
