# Problem B figures and paper specification

Status: planned. The entries below specify what to generate from future locked runs. They report no new numerical results.

Use [`case.json`](case.json) for the supplied observations, [`schema.md`](schema.md) for field names and units, and [`validation.md`](validation.md) for the scoring, split, and selection rules. Use F1–F6 and T1–T3 as stable asset IDs.

## Figure register

| ID | Data owner | Required content and units | Evidence and limits |
|---|---|---|---|
| F1 | `b_physics`, `b_inference` | Observation and extrapolation panels $y(x)$ and $z(x)$, with axes in metres. Mark release and both observed centers, baseline traces, the selected model's trajectory fan, the 0.10 s cutoff, and the plane at $x=11$ m. Shade the observed span. | Use case data and traces for the same kick. Log the selection rule and seed for representative draws. Stop each curve at its first terminal event. Keep physical model contrasts separate from coordinate parameterization comparisons. |
| F2 | `b_inference` | Goal front view with equal scales on `Y (m)` and `Z (m)`. Show the full goal, solid frame, dashed radius-clearance boundary, density conditional on plane arrival, joint 95% region, baseline points and mode conditional on entry if available. Label the color scale `Conditional density (m⁻²)` or `Probability per grid cell (%)` as applicable. | Use locked draws and summary. List the probabilities of crossing outside the frame and of no crossing beside the plot, with numerical failure reported separately. Report off-panel probability mass using the original denominator. Label the distinct conditions for the density and mode. |
| F3 | `b_inference` | Show dimensionless singular values of the whitened, parameter-scaled observation Jacobian and a pair of early-compatible, later-divergent trajectories. Use metres for displacement or crossing difference and identify each terminal event. | Record the assumed noise, parameter scaling, physical bounds, and shared observed frames. If no admissible pair is found, show the achieved spread or a prediction profile and give the search limits. |
| F4 | `b_physics`, `b_inference` | Show entry probabilities across measurement-error scenarios and crossing intervals across ball type, wind and transverse-force scenarios. Label the coordinate-error scale in mm, probabilities in %, and position intervals in m. An optional $C_D(Re)$ inset uses dimensionless axes and marks the predicted Reynolds range and each experiment's range. | Read T2 scenario data and specify which scenarios were refitted. Show structural scenario ranges separately when model weights lack an external basis. Plot an empirical curve only when its source and digitization can be checked. |
| F5 | `b_validation` | Show reliability for arrival and entry probabilities, with forecast and observed rates in %, identity diagonals, bin counts and uncertainty bars. Show counts or rates of numerical failures and point abstentions by model and scenario. | Use locked blind cases and label matched, single-factor mismatch, and combined mismatch separately. Record the bin rule and denominators. Suppress estimates below the locked bin support threshold and report their counts. |
| F6 | `b_validation` | Show observed joint coverage at nominal 50%, 80%, and 95%, with both axes in %. Pair with model comparisons using crossing error or energy score in m. | State the truth-plane subset for each statistic and give the model availability and overlap denominators. Use paired differences and uncertainty intervals from the locked blind evaluation. |

`b_figures` owns F1–F6 and `figures_manifest.csv`. Supply a vector PDF, preview PNG, reproducible plotting script or command, and English caption for each figure. Keep F1, F2, F4, and F5 in the main text. Place F3 and F6 in the main text when they support a principal claim and in the appendix otherwise. Use consistent goal geometry, colors, and model labels. Label the lateral direction `positive y side` when the viewpoint might reverse left and right. Distinguish observations, predictions, and withheld truth in the legends. Inspect equations, units, captions, and axis labels at their final PDF size. Every caption identifies the relevant population, conditioning event, and evidence type.

## Table register

| ID | Data owner | Required columns and checks |
|---|---|---|
| T1 | `b_physics`, `b_inference` | Assumption, variable or model ID, value or range, units, scope, and source. Include priors, measurement scenarios, event geometry, and physical constants. Identify time/distance variants of the same physics and label dimensionless coefficients. Cite primary evidence for measured inputs and identify modeling choices. |
| T2 | `b_inference` | Supplied-kick model and scenario IDs, change from baseline, and probabilities of plane arrival, center in goal, and radius clearance. Give conditional mode if supported, joint and marginal uncertainty with conditioning, and arrival time in seconds. Use metres for crossing locations and interval endpoints. Mark unavailable values when effective support is insufficient. |
| T3 | `b_validation` | Split, stratum, model ID, full sample size, physical outcome counts, valid forecasts, technical failures, and point abstentions. Include all-case failure-penalized Brier loss, ordinary Brier score and its denominator, conditional crossing score and its denominator, and paired uncertainty. Include coverage and availability or link to the F5–F6 evidence. |

## Evidence handoff and QA

`b_integrator` owns the final `release.json` and `summary.json`. `b_validation` locks the case list and truth and writes `metrics.csv` after receiving frozen predictions. `b_physics` and `b_inference` produce traces, draws, and diagnostics. `b_paper` owns prose, layout, table assembly, and `claims.csv`. `b_review` independently reruns a nominal case and a mismatch or failure case, checks the evidence joins, and reports any blocked claims to `b_integrator`.

Use `figures_manifest.csv` and `claims.csv` as evidence indexes. Each row identifies the asset or claim ID, run ID and version, source artifact and exact summary keys or validation row filters, statistic, population, conditioning event, display units, and owner. Add figure range and clipped mass when relevant. For an externally sourced statement record the reference, relevant page or section, and what it supports. For an analytic result record the equation or derivation ID and its check. Use relative artifact paths and stable IDs. Store probabilities on a 0–1 scale and convert to percentages only for display.

Before typesetting, regenerate derived display values from their source data and verify the following items.

- The abstract and conclusion use the selected model and identical scenario IDs, values, units, conditioning, and rounding. Exclude the supplied kick from aggregate validation.
- In T3 and F5–F6 the full-sample, truth-crossing, valid-prediction, and overlap denominators match their stated populations. Ground-first and physical non-crossings remain in event probabilities. Report technical failures separately.
- In F2, F4, and T2 the geometry and probabilities share thresholds, region level, and weights. Verify $P(\text{radius clearance})\le P(\text{center in goal})\le P(\text{plane crossing})$. Conditional locations stay unavailable where the support criterion fails. When numerical failures leave probabilities unresolved, display the prespecified bounds.
- Solver convergence and time/distance equivalence use the configuration named in the text. Claims about calibration and comparative performance cite the blind split, with its stress strata and uncertainty.
- Label an external trajectory as an observed comparison only after verifying the data and usable event. Keep observed, synthetic matched, synthetic stressed, and analytic evidence distinct. Report measured latency on a stated runtime if claiming that the method can operate within the time available to the goalkeeper.

## Paper order and contest format

Prepare an anonymous English Problem B paper. Put the registered team number at the top of each page. The first page contains only the team number, `B`, the title, and a summary of at most 300 words. The team supplies the team number. Omit authors, institution, and identifying details from the paper and PDF metadata. Follow the official submission format for the team's selected problem. [UPC contest rules](https://uphysicsc.com/contestrules.html)

1. **Problem and output.** State the coordinate system, observation times, forward plane crossing, and airborne scope. Separate unconditional outcome probabilities from the crossing location conditional on entry.
2. **Physics and inference.** Explain the candidate models, where drag cancels under a distance parameterization, observation error and timing, parameter constraints, and propagation to the first event. Include enough detail to reproduce the calculations without relying on the code appendix.
3. **Validation and model choice.** Describe the independent truth generator, locked splits, comparator ladder, numerical fixtures, scoring populations, failure policy, and selection rule. Interpret the blind results and weak-identification tests once the evidence is available.
4. **Supplied kick and limitations.** Present the selected point statistic, joint and marginal uncertainty with conditioning, event probabilities, arrival time, and sensitivity to measurement and model assumptions. Explain limitations from unobserved spin, wind, tracking accuracy, and bounce or frame contact as relevant.
5. **References and AI report.** Cite the supplied problem, rules, primary physics and validation sources, and software or algorithms used. End with **Report on the Use of AI**. Identify each system and its role and include the exact queries and complete corresponding outputs for AI-assisted writing. State any AI-assisted computational-model development and the actual systems used. Verify the retained interaction record is complete before submission. The team must understand, verify, explain, and defend the implementation. [UPC contest rules, section 5](https://uphysicsc.com/contestrules.html)

Populate result fields only from verified evidence. Regenerate affected figures, tables, and prose together if a run changes.
