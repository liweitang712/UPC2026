# Data and event contract

Use [case.json](case.json) for the official shot and shared numerical defaults. Use [models.csv](models.csv) for model IDs. The origin is the penalty mark. The frame is right-handed with +x toward the goal, +y to the kicker's left while facing the goal, and +z up. Plot labels should say “positive y side” if the viewing direction is ambiguous. Positions are in metres, times in seconds from the kick, and probabilities in [0, 1]. Decimal rounding is applied only at publication.

## First event

Find the first positive-direction crossing of the goal plane or the first downward return to the ground contact height z = R, whichever comes first. Initial contact at t = 0 is ignored for a trajectory taking off upward. Immediate downward penetration is ground contact at t = 0. A numerical tie within the configured tolerance goes to the ground event. The configured horizon bounds the method's claim. Strict center-in-rectangle inequalities exclude equality with a post, ground line, or crossbar. A stricter clearance proxy applies one ball radius of inset to both sides and the top, with z > R. This proxy is separate from an official whole-ball scoring decision.

| Event | Meaning |
|---|---|
| `PLANE_GOAL` | First plane crossing before ground, center strictly inside the goal rectangle |
| `PLANE_WIDE` | First plane crossing before ground, center outside the goal rectangle or on its boundary |
| `GROUND_FIRST` | Ground contact before or within the event tie tolerance of the first plane crossing |
| `NO_REACH` | The configured observation horizon ended without either event or the method can establish that no forward crossing is possible |
| `NUMERICAL_FAILURE` | The model or inference could not produce a usable classification |

Keep the event and reason separate. B2 uses the configured spatial tie tolerance because it provides no arrival time. Track a numerical failure separately from a physical non-crossing. For boundary tests use the numerical event tolerance to resolve ordering. The goal bounds stay fixed.

## Exchange files

All CSVs use a header, comma separation, UTF-8, and blank fields for unavailable values. IDs use stable strings. Boolean fields are 0 or 1, with a blank when the quantity is unavailable.

| File | Key | Required fields after key |
|---|---|---|
| `cases.csv` | `case_id` | `split,stratum,scenario_id,t1_s,x1_m,y1_m,z1_m,t2_s,x2_m,y2_m,z2_m` |
| `truth.csv` | `case_id` | `event,t_s,y_m,z_m,clearance_goal,reason` |
| `predictions.csv` | `case_id,model_id,scenario_id,draw_id` | `weight,event,t_s,y_m,z_m,clearance_goal,reason` |
| `metrics.csv` | `run_id,split,stratum,model_id,scenario_id,metric` | `value,unit,n_total,n_eligible,n_scored,n_failed,interval_lo,interval_hi` |

`cases.csv` can describe the measurement-error protocol without exposing latent truth parameters. Hold the blind truth file separately until prediction freezes. For each case/model/scenario, prediction weights must sum to one including failed draws. A full method failure is a single failure row of weight one. For ground and no-reach events, leave `y_m,z_m,clearance_goal` blank. `t_s` records the event time where available and can be blank for no-reach, failure or B2. With plane events `clearance_goal=1` implies `PLANE_GOAL`.

## Summary and release

The integrator publishes one `release.json` per `run_id` with the code commit, input file hashes, case/schema versions, model/scenario configurations, numeric tolerances, independent generation/noise/inference seeds, and relative paths of data and metrics. A `summary.json` references that run ID and records a result per case/model/scenario. Required keys include:

- `p_reach`, `p_goal`, `p_clearance_goal`, `p_ground_first`, `p_no_reach`, `p_failure`. All use total weight as denominator. If there are failures, event probabilities computed with total weight are lower bounds. The corresponding upper bounds add the failed weight. If there is no interpretable prediction, use null for conditional quantities.
- `p_goal_given_reach` among resolved plane crossings only, or null if that mass is zero.
- `plane_intervals` and `goal_intervals`, with explicit condition, levels, quantile endpoints for t/y/z, contributing weight and count. Report the condition and construction of any joint region.
- `entry_mode_yz_m` conditional on `PLANE_GOAL`, with estimator, bandwidth/grid where applicable, contributing weight/count and numerical stability. Keep this separate from coordinate medians.
- `diagnostics` for effective sample size, repeated runs, numerical failures and other quality flags.

Do not reinterpret failed draws as misses when comparing models. If there are no numerical failures and plane mass is positive, (P(G)=P(C)P(G\mid C)). All resolved event categories plus failure mass must sum to one. Check (P(\mathrm{clearance})\leq P(G)\leq P(C)). Case estimates, figures, and manuscript claims must point to the same release and use its denominators.
