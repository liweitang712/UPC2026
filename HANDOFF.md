# B 题交接与接手步骤

论文写作入口及 WP1、WP2、WP3 的逐项提示词见 [PAPER_WRITING.md](PAPER_WRITING.md)。

**当前阶段：规范已整理，待三位队员认领。** 旧版有可跑的点球代码、数值和英文稿。新方案的模型阶梯、盲测与制图还需按 `spec/` 执行，旧版数值仅用于回归对照。

## 给三位队员

各自克隆本仓库，使用自己的 GitHub 与 Codex 账号，在仓库目录打开 Codex。根据分工复制下面一条提示词。由队员 3 管理 `main` 和发布结果，三人约定后合并各自分支。

| 工作包 | 建议分支 | 负责范围与交付 |
|---|---|---|
| **WP1 · Physics** [#1](https://github.com/liweitang712/UPC2026/issues/1) | `team/physics` | `physics/` 的 B0–B2/M1–M3 前向接口、事件定位、解析及步长检查。为 F1 提供轨迹和基线数据，为 WP2 提供接口 |
| **WP2 · Inference** [#2](https://github.com/liweitang712/UPC2026/issues/2) | `team/inference` | `inference/` 的观测模型、后验与敏感性。给 WP3 交 `predictions.csv`，并交 F2–F4 所需结果与图稿 |
| **WP3 · Validation & release** [#3](https://github.com/liweitang712/UPC2026/issues/3) | `team/validation-paper` | `validation/` 的封存真值、盲测和评分，`figures/` 的 F5–F6，`paper/` 的英文稿。维护冻结发布并由 WP1 或 WP2 独立复核 |

### 可直接粘贴到 Codex

**WP1**

> 读 AGENTS.md、HANDOFF.md、spec/case.json、spec/schema.md、spec/models.csv 和 spec/physics.md。认领 WP1，基于 main 开 team/physics。只负责前向模型、基线、事件定位、收敛测试和 F1 的数据。先给 WP2 交可复用的函数签名与样例，再提交实现、复现命令和测试结果。共用口径有变更先交主代理裁决。

**WP2**

> 读 AGENTS.md、HANDOFF.md、spec/schema.md、spec/inference.md 和 spec/figures-and-paper.md。认领 WP2，基于 main 开 team/inference。先用冻结题例设计似然和输出格式，待 WP1 接口可用后做反演、情景重拟合和 F2–F4。盲测只使用 cases.csv。交接时附预测数据、模型及场景版本、诊断和运行命令。

**WP3**

> 读 AGENTS.md、HANDOFF.md、spec/validation.md 和 spec/figures-and-paper.md。认领 WP3，基于 main 开 team/validation-paper。先冻结验证协议与盲测输入，真值保管到预测冻结后再评分。整合模型、反演与图表，发布统一 run_id；写英文稿并让另一名队员从冻结提交独立复算。

## 跨电脑交接

仓库里的提交与 PR 是交接记录。每次推送后，在对应工作包的 Issue 或 PR 更新以下字段。接手方拉取指定提交，再让本机 Codex 阅读有关规范及文件。

| 字段 | 填法 |
|---|---|
| 工作包、状态、接手者 | 例如 WP1，接口可用，交 WP2 |
| 分支、commit、run_id | 以实际 Git commit 为准。有正式输出时再写 run_id |
| 数据与文件 | 列路径和输入版本 |
| 复现与验收 | 命令、通过的测试、仍有的问题 |
| 需要裁决的变更 | 例如事件枚举、噪声假设、盲测设计 |

**顺序。** 三人先确认接口和坐标。WP1 与 WP3 可并行完成前向测试、验证预登记，WP2 可先用共同样例搭建推断接口。随后 WP1 交接口，WP2 交预测，WP3 解封评分并发布统一结果。写作和正式出图读取同一个 `release.json`。各队员保存用于论文的 AI 原样提示词和完整输出。

**未决事项。** 三个工作包仍待认领。尚未选择 M1–M3 主模型，尚未冻结盲测配置、情景权重或正式结果。发起接口变更时先在工作包 Issue 或 PR 说明受影响的下游产物。
