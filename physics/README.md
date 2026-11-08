# WP1 forward solver

This package needs Python 3.10+ and uses the standard library. Run from the repository root. It follows the [shared event contract](../spec/schema.md) and [WP1 specification](../spec/physics.md).

## Interface for WP2 and WP3

```python
from dataclasses import replace

from physics import SolverConfig, load_case, solve

case = load_case()
baseline = solve("B1", case, include_trace=True)
print(baseline.observations, baseline.observation_valid, baseline.event)

parameters = {"v0": (30.3, 9.2, 6.9), "cd": 0.31, "cy": -0.13, "cz": 0.02}
full = solve("M2", case, parameters)
early = solve("M2", case, parameters, SolverConfig(horizon_s=case.times[-1]))

# Reuse the physical configuration with the next case's two early observations.
new_case = replace(case, observations=((1.52, 0.40, 0.43), (3.00, 0.78, 0.72)))
print(solve("B1", new_case).event)
```

`solve(model_id, case, parameters=None, config=None, *, include_trace=False)` returns a `ForwardResult` with the two modeled centers in observation order, a pair of physical-validity flags, an `EventResult`, and an optional tuple of `TracePoint` values. The shortened horizon in the example is for likelihood calls. Use the full horizon when classifying a predicted shot. Frames after a terminal event may have mathematical continuations but are marked invalid. B2 is distance-based and returns its frames at the latent input abscissae. Its event and trace omit arrival times. An invalid input or unsupported evaluation yields `NUMERICAL_FAILURE` with a reason.

| Model | Parameter mapping |
|---|---|
| B0 | Optional `v0` or `frame_centers`. The default fits the public point observations with equal coordinate weights. |
| B1 | Optional `v0` and `a0` together, or `frame_centers`. The default interpolates the case's three centers. |
| B2 | Optional `frame_centers`, with strictly increasing x. The default interpolates the case's three centers in x. |
| M1 | `v0`, `cd`. |
| M2 | `v0`, `cd`, optional `cy`, `cz` (default zero). |
| M3 | `v0`, `cd_anchor`, `reference_speed_m_s`, and `curve` (a registered ID or a mapping of `reynolds` and `cd` arrays). Optional `cy`, `cz`, `dynamic_viscosity_pa_s` and `curve_policy` (`error` or `clamp`). |

Velocity and acceleration vectors follow x/y/z order. `frame_centers` is a pair of latent positions in the same order as `case.times`. Keep the official times for the contest case. Use `dataclasses.replace` for an alternative case or integration configuration. Omit `include_trace` during fitting to avoid computing unused trace fields.

## Experimental curves and F1 handoff

M3 includes `goff2026_trionda_b` and `goff2026_jabulani_b`, digitized from the fixed, nonspinning orientation B traces in Figure 7. The JSON files under [curves/](curves/) identify the plotted data, calibration, units, source domain and transition. The default policy rejects out-of-domain evaluations. Explicit clamping is available as a separate sensitivity case and marked on the trace. The fitted drag anchor shifts the curve vertically, so an anchored flight coefficient is a model input informed by the measured shape. [Goff et al., 2026](https://doi.org/10.3390/app16062808)

```sh
python -B -m physics.demo
```

This regenerates [traces.csv](examples/public_case/traces.csv) and [events.json](examples/public_case/events.json). The traces contain the launch, available observed times, and terminal event, with the M3 Reynolds and drag values. F1 can read them directly and add WP2's posterior samples after the main-model run is frozen.

The demo uses the exact point observations for B0–B2. For M1–M3 it holds the historical M2 launch velocity and drag anchor fixed to isolate changes in force law. M1 omits transverse force, and the two M3 scenarios use a 30 m/s reference speed. These demonstrations use fixed parameters, and the ball model in the contest case is unknown. The nominal trace Reynolds range is about 389,000–483,000, within both measured curve domains. The Jabulani trace approaches the upper edge of the transition estimated from Figure 7 and brackets the critical Reynolds number reported in Table 1. The Trionda trace stays above both transition references. Comparisons between refitted ball-type scenarios belong to WP2.

## Acceptance checks

```sh
python -B -m unittest discover -s physics/tests -v
```

The B1 public fixture crosses at approximately 0.405008361 s, with `y=2.494824414 m` and `z=1.920367056 m`. These are deterministic baseline values. Model selection, posterior uncertainty and blind validation belong to WP2/WP3.
