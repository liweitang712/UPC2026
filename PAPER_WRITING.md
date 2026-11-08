# UPC 2026 B 题｜论文写作入口

**[打开 SJTU LaTeX 共享项目](https://latex.sjtu.edu.cn/project/6aefd43ba226e7cf9f8fcd94)**。主文档为 `main.tex`。登录后先读项目根目录的 `AGENTS.md`，再认领下面的章节。共享项目保存唯一的论文正文。GitHub 保存代码、复现命令、结果发布、证据索引和交接记录。

| 工作包 | LaTeX 正文 | 图表交付 |
|---|---|---|
| [WP1 · 物理模型 #1](https://github.com/liweitang712/UPC2026/issues/1) | `sections/01-problem.tex`、`sections/02-wp1-physics.tex` | T1 的物理假设与来源，F1 的基线轨迹。与 WP2 核对 F1 的预测叠加及 F4 的气动依据 |
| [WP2 · 反演预测 #2](https://github.com/liweitang712/UPC2026/issues/2) | `sections/03-wp2-inference.tex`、`sections/05-wp2-case.tex` | 向 WP1 提供 T1 的观测与先验条目。负责 T2 题例结果、F1 的预测叠加和 F2–F4 |
| [WP3 · 验证 #3](https://github.com/liweitang712/UPC2026/issues/3) | `sections/04-wp3-validation.tex` | T3 验证结果，F5–F6，盲测分母、失败计数与模型选型依据 |
| 三人共同 | WP1、WP2、WP3 分别交物理、反演、验证局限的一段草稿，以及摘要素材和本人的 AI 使用记录 | 轮值整合者统一编辑 `sections/06-discussion.tex`，并维护 `main.tex`、`sections/00-summary.tex`、`sections/07-ai-report.tex` 与共享参考文献。另两人复核 |

## 给各工作包 Codex 的提示词

### WP1 · 题意与前向模型

> 打开共享 SJTU LaTeX 项目并读取 `AGENTS.md`。写英文 `sections/01-problem.tex` 和 `sections/02-wp1-physics.tex`，核对题给坐标、两帧时刻、过线与触地判据、B0–B2、M1–M3、阻力曲线来源和数值验收。补齐 T1 的物理量、单位和来源。给 F1 提供可复现的基线轨迹和英文图注，与 WP2 核对预测叠加。交一段物理局限和一句摘要素材给整合者。在 Issue #1 留下文件、证据版本、复现命令和待确认项。

### WP2 · 反演与题例

> 打开共享 SJTU LaTeX 项目并读取 `AGENTS.md`。写英文 `sections/03-wp2-inference.tex` 和 `sections/05-wp2-case.tex`，说明似然、先验、反演、可辨识性、抽样与失败处理。把 T1 的观测和先验条目交给 WP1 填表。用冻结结果填写 T2 与 F2–F4，并给 WP1 提供 F1 的预测轨迹。区分过线概率、入门概率、条件入门众数和条件预测区间，注明条件与分母。交一段反演局限和一句摘要素材给整合者。在 Issue #2 记录 `run_id`、图表来源和复现命令。

### WP3 · 盲测与模型比较

> 打开共享 SJTU LaTeX 项目并读取 `AGENTS.md`。写英文 `sections/04-wp3-validation.tex`，说明盲测拆分、真值生成、评分与选型规则。WP2 锁定预测后再解封真值。用冻结指标填写 T3、F5–F6，区分匹配、单项错配和组合错配，报告真值过线数、可评分数和数值失败。交一段验证局限和一句摘要素材给整合者。在 Issue #3 记录 `run_id`、指标来源、分母和选型依据。

## 合稿与复核

1. 各人只写自己认领的章节。写入数字前核对同一个冻结 `run_id`，在 LaTeX 源码注释中记录数据文件、模型或情景 ID、条件与分母。结果尚待冻结的段落先保留占位。
2. 图用 `figures/F1.pdf` 至 `figures/F6.pdf` 的固定文件名。把生成命令、数据来源和版本记入 GitHub 的 `figures_manifest.csv`。用 `claims.csv` 对齐正文、图表和摘要中的数值。
3. 如果 Codex 无法操作在线项目，在对应 Issue 或 PR 交付可粘贴的英文 LaTeX 片段，注明目标文件和插入位置，由章节负责人并入共享稿。处理后在 Issue 留下交接记录。
4. 整合者汇总摘要、结论与 AI 披露，再编译核对匿名封面、队号、图表、引用和版面。三人各自保存 AI 使用记录与要求提交的原样提示词和输出。[图表和论文规范](https://github.com/liweitang712/UPC2026/blob/main/spec/figures-and-paper.md) · [竞赛规则](https://university-physics-competition.com/contest-rules)
