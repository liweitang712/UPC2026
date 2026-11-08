# WP2 · 两帧反演

基线为 `e24d633`，工作分支为 `team/inference`。冻结题例使用
`spec/case.json` v1，模型编号和交换字段沿用 `spec/models.csv` 与
`spec/schema.md`。WP1 起始接口版本为 `e25b682`。

## 观测似然

按 `x1,y1,z1,x2,y2,z2` 堆叠观测，冻结向量为
`(1.50,0.45,0.44,2.96,0.86,0.74)` m，时刻为 0.05 和 0.10 s。
以 `solve` 返回的两帧球心构造残差。拟合时检查两个
`observation_valid` 标记，传播时用完整预测时域并保留首事件。

| 拟议场景 ID | 似然 |
|---|---|
| `gaussian-10mm` | 独立坐标误差，标准差 0.010 m。相关版本对协方差作 Cholesky 分解，用三角求解白化残差并保留归一化项。 |
| `rounding-10mm` | 每一维的模型坐标须落在观测值 ±0.005 m 的左闭右开区间。 |
| `gaussian-10mm-rounded-10mm` | 独立高斯误差后作厘米舍入。逐坐标计算标准正态区间概率，累加其对数。正尾改用生存函数，避免两个接近 1 的 CDF 相减。 |

场景 ID 待与 WP3 的发布清单对齐。B1/B2 共用潜在观测抽样，舍入场景先在观测单元内均匀抽样，再按场景加入高斯噪声。B2 有序节点失败须保留对应权重。M1–M3 对各场景分别拟合，变更球型、风或横向力配置时重新拟合相同两帧。

## 输出

预测 CSV 表头如下。

```csv
case_id,model_id,scenario_id,draw_id,weight,event,t_s,y_m,z_m,clearance_goal,reason
```

每组权重含失败且合计为 1。非平面事件的 y、z 和净空字段留空，
B2 的时间留空。完全失败写入一条权重为 1 的失败记录。事件概率以总权重为分母，失败权重给出概率上界与下界之差。过门位置和时间摘要分别按到达平面和入门条件计算，支持不足时记录原因。

盲测预测输入仅为 WP3 发出的 `cases.csv`，物理常量和预注册场景来自版本化配置。交接记录模型与场景版本、输入哈希、种子、数值容差、抽样次数、有效样本量、最大权重和失败原因，并给出预测命令和图表命令。

## 接入验收

公开题例的首轮基线使用独立 10 mm 高斯误差。B0 使用平坦速度参考先验，
B1/B2 使用平坦潜在坐标参考先验，并共用每次抽样的两帧坐标。
在可导入 WP1 `e25b682` 的 Python 3.10+ 环境中，从仓库根目录运行

```sh
python -B -m inference.baseline inference/public-baseline --draws 10000 --seed 2026
```

如果 WP1 尚未合入当前分支，可将该提交的 `physics/` 和 `spec/case.json`
一起导出到独立目录，再将该目录加入 `PYTHONPATH`。
`public-baseline/` 下的预测和诊断仅对应公开题例的基线验收。

用同一 WP1 版本运行两组舍入情景。当前舍入预测覆盖 B1/B2 的平坦潜在坐标参考后验。

```sh
python -B -m inference.baseline inference/public-rounding-10mm --scenario rounding-10mm --draws 10000 --seed 2026
python -B -m inference.baseline inference/public-gaussian-10mm-rounded-10mm --scenario gaussian-10mm-rounded-10mm --draws 10000 --seed 2026
```

## M2 高斯参考复现

首轮存档使用 WP1 `e25b682`。按 `spec/inference.md` 的旧版 M2 先验抽样气动系数，
逐组用两帧残差定位初速度提议中心。重要性权重使用完整两帧高斯似然，
并校正初速度提议密度。以独立种子和两倍预算复跑。

```sh
python -B -m inference.m2 inference/public-m2 --draws 10000 --seed 2026 --wp1-revision e25b682
python -B -m inference.m2 inference/public-m2-repeat --draws 20000 --seed 2027 --wp1-revision e25b682
```

两次运行均输出逐抽样预测和诊断。预测概率以全体已分配权重为分母，
到达时间中位数以过门平面为条件。

## WP1 交付版和公开题例图表

让 Python 可导入 WP1 交付版 `02b67b2a8e1e7fda974385c98b76f66b33dbfaa0`
的 `physics` 包。绘图使用 NumPy 2.5.4 和 Matplotlib 3.11.2。
在仓库根目录运行 `./inference/run_public.ps1`。默认每个情景 4000 次，
种子 2026。纯舍入使用 16000 次，M2 参考复跑使用 8000 次及种子 2027。
输出位于 `inference/wp2-public/`，包含逐抽样预测、T2、
F3 轨迹与 Jacobian、F2–F4 的 PDF/PNG 和英文图注。图表属于公开题例草稿，
待 WP3 冻结正式发布后按同一 run ID 重出。

M3 锚定速度为 30 m/s，超出曲线范围时使用 WP1 的拒绝策略。两条曲线
分别重新估计锚点和初速度。两组先验敏感性是拖曳先验中心 0.35 和横向系数
先验标准差 0.12，其余各自沿用 M2 参考配置。条件统计使用 ESS 50 的草稿门槛。
众数使用目标区域内的 0.02 m 网格，比较 0.05 m 和 0.10 m 两种高斯核带宽。
草稿把 ESS 低于总尝试数 10% 或最大权重高于 1% 标为采样警告。
纯舍入通过 16000 次提议得到 249 个非零权重，有效样本量约 142，
适合作为探索性敏感性结果。

## WP3 预测接口

当前批量入口使用有界批次，支持 Python 3.10+；本次复核在 Python
3.14 上运行。输出含每组尝试数、有限权重、支持域与先验拒绝、
似然重试及传播失败权重。M3 严格曲线在观测窗内的域外参数是
零支持提议，传播中离开曲线仍记为未解析预测。其他似然数值失败
以半步重试一次，仍未解析时整组失败，因为其后验权重未知。
有限支持未采到也会显式失败。详见 [复核记录](REVIEW-V2.md)。

```sh
python -B -m inference.forecast cases.csv scenarios.json output --draws 4000 --seed 2026
```

情景注册表按 `scenario_id` 索引，例如
`{"gaussian-10mm":{"sigma_m":0.01,"curve":"goff2026_trionda_b"}}`。
可选设置包括 `rounding_width_m`、`wind_m_s`、`drag_mean`、
`transverse_sigma`。注册表必须与 WP3 的冻结协议一致。正式运行前应
核对采样预算及条件 ESS 门槛。气动模型的纯舍入
通过单元指示似然拒绝不相容的抽样，低支持场景需要单独核对 ESS。
输出附两份输入的 SHA-256。预测入口仅从
`cases.csv` 读取题例观测，固定物理常量来自版本化公共题例。

以下命令属于历史 WP3 v1，须在 `98d6970` 的独立检出目录运行，并使用
冻结 WP1 版本；当前入口不得覆盖 `selection-v1` 或盲测发布产物。
WP3 v1 选择集使用 `selection-scenarios.json`，固定为 10 mm 独立高斯误差、
零风和 Trionda B 曲线。并行运行使用 Python 3.14。选择集输入取自 WP3 冻结
提交 `c5f3e5ef2073b2cce25a09ba0e82ded242dca2b7` 的
`validation/frozen/v1/selection/cases.csv`，SHA-256 为
`898df22b8365b03d9194191bc20bc89c575eddb612b7f4b53f6eae08afa00d16`。

```sh
python -B -m inference.forecast cases.csv inference/selection-scenarios.json inference/selection-v1 --draws 1024 --seed 2026 --workers 12
```

发布包将逐抽样 CSV 无损压缩。评分前用
`python -m gzip -d inference/selection-v1/predictions.csv.gz` 恢复 CSV，
再将其与 `forecast.json` 一同交给 WP3。

- 用冻结两帧解析计算 B0 等方差高斯拟合，比较 WP1 的 B0 输出。独立核对 B1 点估计。
- 检查舍入小噪声极限、窄尾区间和相关高斯白化等价性。
- 检查门外、未到达、退化点云和数值失败的预测记录与分母。
- F2 使用条件过门密度及联合区域，F3 使用白化缩放 Jacobian 及早期相容轨迹，F4 使用逐情景重拟合结果。正式数据统一引用 WP3 冻结的 run ID。
