# Problem B figures and paper specification

Status: planned. The entries below specify what to generate from future locked runs. They report no new numerical results.

Use [`case.json`](case.json) for the supplied observations, [`schema.md`](schema.md) for field names and units, and [`validation.md`](validation.md) for the frozen scoring, split, and selection rules. Use F1–F6 and T1–T3 as stable asset IDs even if their presentation order changes.

## Figure register

| ID | Owner | Required content and units | Evidence and limits |
|---|---|---|---|
| F1 | Model owner | Coordinate geometry and observation window. Mark the ball center at release, the two observed centers, and the plane `x = 11 m`. Label axes `x (m)`, `y (m)` and `z (m)` as shown. Mark the actual frame times in seconds and distinguish the fitted interval from the prediction interval. | Render the observations and frame dimensions directly from the case. Any connecting line must be identified as schematic or as a model trajectory. |
| F2 | Model owner | Plot (y(x)) and (z(x)) in metres for the supplied kick, with the observations, held-out prediction span, and common model IDs. Use an inset or linked panel for the first 3 m if needed. Mark arrival times in seconds if shown. | Use trajectory outputs for the same kick and configuration. Separate a comparison of physical models from a comparison of time and distance parameterizations. End each curve at its first terminal event. |
| F3 | Identifiability owner | Show early observation agreement and later separation for an admissible pair or parameter profile. Label trajectory coordinates in metres and observation misfit in standardized, dimensionless units. Show model bounds and which geometry the trajectories cross. | Link to the weak-identification search or profile, its physical bounds, the assumed noise, and the crossing events. If the pair search finds no admissible example, show the tested range or profile with that outcome. |
| F4 | Inference owner | Plot the supplied kick's goal-plane distribution with equal scales on `Y (m)` and `Z (m)`, the frame and radius-clearance proxy. Label the joint region, its conditioning event and level, and the estimated mode conditional on entry if support is sufficient. State the unconditional entry probability in the caption or an annotation. | Use draws and summary from the selected locked run. Keep misses in an unconditional event count. Use the same weights and region method as the reported intervals. Use the same conditioning for the figure label, legend, and caption. |
| F5 | Evaluation owner | Show nominal versus observed joint coverage in percent with uncertainty bars, split by prespecified matched and stress strata. Add interval width or region area in m or m² in a separate panel if useful. A goal reliability panel may use predicted and observed probability on 0–1 axes. | Compute from locked blind cases. Print denominators and distinguish unweighted challenge results from results using prespecified scenario weights. Suppress reliability bins with inadequate support and show their counts in T2. |
| F6 | Inference owner | Show how predictions for the supplied kick vary across measurement-noise, prior, and physics scenarios. Use coordinate noise in cm or m, event probability in % or 0–1, and position intervals in m. Label scenario baselines and error models explicitly. | Read scenario summaries from the same evidence set as T3. Keep changes in noise, prior, and structural model distinguishable. Where structural scenario probabilities are unspecified, display scenario ranges and do not average them into a confidence interval. |

Use consistent goal geometry, colors and model labels. Distinguish observations, predictions, and withheld truth in legends. Use editable vector graphics for lines and axes where practical. Verify equations, units, captions and axis tick labels at their final size in the PDF. Every caption must identify the population, conditioning, and evidence type needed to read the panel.

## Table register

| ID | Owner | Required columns and checks |
|---|---|---|
| T1 | Model and inference owners | Candidate model ID and purpose, state/parameter counts, physical terms, parameter assumptions or priors, measurement model, and event treatment. Identify time/distance variants of the same model and give units or mark dimensionless coefficients. Cite primary evidence next to assumptions informed by measurements and label modeling choices. |
| T2 | Evaluation owner | Split, stratum, model ID, full sample size, physical outcome counts, valid forecasts, technical failures, and point abstentions. Include all-case failure-penalized Brier loss, ordinary Brier score and its valid-forecast denominator, conditional crossing score and its denominator, and the paired uncertainty summary. Include region coverage and availability or link to the underlying F5 evidence. |
| T3 | Inference owner | Supplied-kick scenario ID, change from baseline, (P(\text{plane})), (P(\text{center in goal})), and (P(\text{radius clearance})). Report conditional mode if supported, joint and marginal uncertainty summaries with conditioning, and arrival time in seconds. Use metres for crossing locations and interval endpoints. Report explicit unavailable values where an event has too few effective draws. |

## Evidence handoff and QA

The coordinator owns the run manifest and final consistency review. The validation owner locks the case list and truth before model outputs are opened. The model and inference owners produce traces, draws and fit diagnostics. The evaluation owner joins observations, truth and predictions on the schema keys and publishes the summary consumed by the figure and paper owners. The paper owner controls prose and layout.

Keep one lightweight evidence index. Each row should identify a figure, table, or consequential manuscript claim, its run ID and version, its input artifact and exact keys or filters, the statistic and conditioning event, the display units, and the owner. For an externally sourced statement use a reference, relevant page or section, and what it supports. For an analytic result use an equation or derivation ID and its check. Attach the input and output versions to figure captions in the evidence index. Use relative artifact paths and stable IDs.

Before typesetting, regenerate derived display values from their source data and verify the following items.

- The abstract and conclusion use the selected model and identical scenario IDs, values, units, conditioning and rounding. The supplied kick is excluded from aggregate validation.
- In T2 and F5 the full sample, truth-crossing, valid-prediction, and overlap denominators match their stated populations. Ground-first and physical non-crossings remain in event probabilities. A technical failure does not masquerade as a physical miss.
- In F4 and T3 the goals and probabilities share thresholds, region level and weights. Verify (P(\text{radius clearance})\leq P(\text{center in goal})\leq P(\text{plane crossing})). Conditional locations stay unavailable where the support criterion fails.
- Solver convergence, time/distance equivalence and numerical checks refer to the relevant configuration. Claims about calibration and relative performance cite the blind split, with the stress strata and uncertainty displayed.
- The external trajectory is labeled an observed comparison only after the data and usable event are verified. Keep observed, synthetic matched, synthetic stressed, and analytic evidence distinct. Report latency as measured on a stated runtime if claiming a method can operate within the time available to the goalkeeper.

## Paper order and contest format

Prepare an anonymous English Problem B paper. Put the registered team number at the top of each page. The first page contains only the team number, `B`, the title, and a summary of at most 300 words. The team supplies the team number. Do not include authors, institution, or identifying details in the paper or PDF metadata. Use the official contest format and submit only the team's selected problem. [UPC contest rules](https://uphysicsc.com/contestrules.html)

1. **Problem and output.** State the coordinate system, observation times, forward plane crossing, and airborne scope. Separate unconditional outcome probabilities from the crossing location conditional on entry.
2. **Physics and inference.** Explain the candidate models, where drag cancels under a distance parameterization, observation error and timing, parameter constraints, and propagation to the first event. Include enough detail to reproduce the calculations without relying on the code appendix.
3. **Validation and model choice.** Describe the independent truth generator, locked splits, comparator ladder, numerical fixtures, scoring populations, failure policy and selection rule. Interpret the blind results and weak-identification tests only after they are available.
4. **Supplied kick and limitations.** Present the selected point statistic, joint and marginal uncertainty with conditioning, event probabilities, arrival time and measurement/model sensitivity. Explain limits from unobserved spin, wind, tracking accuracy, and bounce or frame contact as relevant.
5. **References and AI report.** Cite the supplied problem, rules, primary physics and validation sources, and software or algorithms used. End with **Report on the Use of AI**. Identify each system and its role and include the exact queries and complete corresponding outputs as required for AI-assisted writing. State any AI-assisted computational-model development and the actual systems used. Use the retained interaction record for the appendix and verify that it is complete before submission. The team must understand, verify, explain and defend the implementation. [UPC contest rules, section 5](https://uphysicsc.com/contestrules.html)

The specification uses placeholders for results that depend on future runs. Replace placeholders only from verified evidence, and update affected figures, tables and prose together if a run changes.
