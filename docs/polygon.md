# Polygon 是什么？与 Duliu 的关系

## 1. Polygon 是什么

**[Polygon](https://polygon.codeforces.com)** 是 Codeforces 官方的 **出题与验题平台**（需 CF 账号）。出题人在 Polygon 上完成一整套「从题面到测试数据到验题」的流程，通过后可将题目 **挂到比赛 (Contest)** 或 **题库 (Problemset)**。

Duliu 的 **PACKAGE** 阶段目标是生成 **Polygon 可导入/可对照的题包结构**，减少手工搭目录。

## 2. Polygon 上的一道题（逻辑组织）

在 Polygon 网站里，一道题是一个 **Problem** 工程，典型包含：

| 部分 | 内容 |
|------|------|
| **Statements** | 题面（多语言）、输入输出格式、样例、注记 |
| **General Info** | 时限、内存、输入输出文件名、难度标签等 |
| **Solutions** | 标程、错误解、其他参考解（用于验题） |
| **Files / Scripts** | `gen.py`、validator、checker、interactor、对拍脚本等 |
| **Tests** | 手工样例 + 生成测试的 **批次 (testset)** |
| **Validation** | 在 Polygon 上跑 **完整验题**：标程过所有点、错解按预期失败、压力生成等 |

Polygon 内部用 **脚本流水线** 管理数据（常见 `run.gen` / `run.sh` 一类），与 **testlib** 生态紧密结合。

## 3. 题包（Package）目录形态（导出/本地）

出题人常把题目 **打包 (Package)** 成目录或 zip，结构大致为：

```
problem_package/
  problem.xml              # 元数据（时限、文件名、版本等）
  statements/
    chinese.html / english.html
  solutions/
    standard.cpp
    wrong.cpp ...
  scripts/
    gen.cpp / gen.py
    validator.cpp
    checker.cpp            # 若 SPJ
    interactor.cpp         # 若交互
  tests/                   # 或按 batch 分子目录
    1.in  1.out
    ...
```

不同导出工具细节略有差异，但核心是：**题面 + 标程 + 脚本 + 测试点 + XML 元数据**。

## 4. Duliu 要做什么、不做什么

| Duliu | Polygon |
|-------|---------|
| 在 DB 存题面、代码、数据 | 网站上的 Problem 工程 |
| Runner 在 Linux Docker 里对拍 | Polygon 云端验题 |
| 生成 **Polygon 兼容 package** | 官方上传/验题入口 |

**默认（当前决策）**：Duliu **生成本地 package**，由人 **手动上传** Polygon 验题；**不做**强依赖网页自动上传（无稳定官方 API）。

## 5. 与题型的对应

| Duliu 题型 | Polygon 侧 |
|------------|------------|
| TRADITIONAL | 标准 tests + 可选 checker |
| SUBMIT_ANSWER | checker / SPJ 必需 |
| INTERACTIVE | interactor + 交互协议 |
| COMMUNICATION | 多选手 + interactor（Polygon 对通信题有专门流程） |

## 6. 延伸阅读

- Polygon 帮助与社区教程（CF 博客、testlib 文档）
- Duliu `packages/duliu/polygon/` 实现期：DB 工件 → 渲染 `problem.xml` + 落盘 tests
