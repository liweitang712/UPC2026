# UPC 2026 · Problem B

本仓库供三位参赛队员及各自的 Codex 协作。任务是从两帧早期观测预测点球穿过球门平面的位置和不确定性。题给坐标、版本化数据规范、盲测流程、制图和成稿要求均在 `spec/`。新队员先读 [交接入口](HANDOFF.md)。

**论文写作请从 [共享 LaTeX 入口与三人分工](PAPER_WRITING.md) 开始。**

当前论文采用 **M2** 预测入门位置与不确定性，M1 和 B0 用于对照。题例、位置优先的合成留出评估、图表和复现入口见 [upc2026-location-v2](releases/upc2026-location-v2/README.md)。

| 文件 | 用途 |
|---|---|
| [spec/plan.zh-CN.md](spec/plan.zh-CN.md) | 中文总体方案、文献、22 个任务、F1–F6 图单 |
| [spec/case.json](spec/case.json)、[spec/schema.md](spec/schema.md) | 官方题例、坐标、事件、字段、分母及发布契约 |
| [spec/models.csv](spec/models.csv)、[spec/physics.md](spec/physics.md) | 模型编号、前向物理与积分 |
| [spec/inference.md](spec/inference.md) | 两帧反演、抽样与预测 |
| [spec/validation.md](spec/validation.md) | 预注册、盲测和评分 |
| [spec/figures-and-paper.md](spec/figures-and-paper.md) | 制图、英文写作与复核 |
| [reference/](reference/) | 旧版 B 题稿、代码、图与历史输出 |

新实现以 `case.json`、`schema.md` 和 `models.csv` 的机器口径为准。中文任务书解释整体设计。历史结果供复现和比较。保留旧稿的正负方向文字、噪声情景和筛选条件作为历史记录，正式稿采用本仓库的新定义。

[2026 题面](https://university-physics-competition.com/2026-competition) · [竞赛规则](https://university-physics-competition.com/contest-rules)
