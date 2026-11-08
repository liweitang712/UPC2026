# Forecasting a penalty kick from two early observations

## Problem and prediction targets

The prediction starts at the kick, with the ball centre at \((0,0,0.11)\) m.
The horizontal \(x\)-axis points towards the goal, the horizontal \(y\)-axis
points to the kicker's left, and \(z\) points upward. The observations are ball
centres at 0.05 and 0.10 s. The target plane is \(x=11\) m. We model free
flight up to the first forward crossing of this plane, the first downward
contact with the turf, or the 2 s horizon. Turf contact takes precedence
when the two event times differ by no more than the declared time tolerance.

The centre enters the goal when a forward crossing occurs before turf contact
and lies strictly within \(-3.66<y<3.66\) m and \(0<z<2.44\) m. We also
evaluate a stricter geometric clearance proxy with a one-radius margin from
both posts, the crossbar and the turf. We report event probabilities over the
entire forecast distribution. The distribution of crossing coordinates is
conditional on reaching the plane. An entry-location statistic is conditional
on entering the goal. Those conditions define different populations.

## Candidate flight models

Three baselines use gravity-only flight, constant acceleration inferred from
the launch centre and the two frames, or a quadratic fit of each transverse
coordinate against forward distance. The distance-based baseline supplies a
crossing position and event when its spatial trajectory is defined. Its model
has no clock.

The flight models use air-relative velocity
\(\mathbf u=\mathbf v-\mathbf w\). Aerodynamic acceleration is scaled by
\(\rho A\|\mathbf u\|/(2m)\), where \(A=\pi R^2\) is the cross-sectional area.
The drag component is proportional to \(-C_D\mathbf u\). The transverse
component is proportional to \(\mathbf b\times\mathbf u\), where
\(\mathbf b=(0,-C_z,C_y)\). The candidate ladder uses constant drag, then adds
effective transverse force, then allows drag to vary with Reynolds number
using a fixed reference curve for each ball scenario. Gravity acts downward
in each time-domain model. In still air without transverse force, drag cancels
from the lateral curvature when forward motion is used as the independent
variable, leaving a straight lateral path. Its effect on forward speed still
changes the vertical curvature through gravity.

The observation model and scenario fits will be documented from the frozen
inference configuration. The draft will then describe the actual likelihood,
priors, sampling diagnostics and treatment of unsuccessful draws.

## Synthetic validation and model comparison

We generate synthetic trial trajectories with an independent third-order
Runge–Kutta solver. A step ends at each observation time. A bracketed event
search refines candidate plane and turf crossings, with the same geometry and
event priority as the forecasting models. Step halving checks observation
coordinates, terminal event identity, time and crossing position.

The benchmark distinguishes a matched constant-coefficient family, separate
stress strata for wind, speed-dependent drag, time-varying transverse force
and correlated sensor error, and a combined stress stratum. These are
constructed scenarios. The baseline sensor perturbations have a 10 mm
standard deviation on each coordinate. The sensor stress uses 25 mm and
correlates errors between the two frames on each axis. An enriched challenge
stratum probes lateral misses, shallow launches and nearly vertical launches.
It is reported separately from the equal-weight comparison across core strata.

Development, model selection and final blind evaluation use distinct physical
shots. The supplied kick is evaluated separately. Each forecasting method
receives the public case identifier and two noisy observations under the
declared forecast scenario. Held-out truth and stress assignments are kept
separately until the corresponding forecasts are locked. The primary score
is the squared error of the centre-entry probability. With unresolved draw
weight \(f\) and resolved entry weight \(p\), the event probability lies in
\([p,p+f]\). We score the endpoint with the larger squared error. An absent or
wholly invalid forecast receives loss one. We report the ordinary Brier score
on forecasts with exact event probabilities and give its denominator.

A more complex model must improve the selection score by the declared
practical margin and exceed one paired bootstrap standard error. Its stress,
coverage and failure checks must also pass. After selection, we freeze the
selected model and simpler comparator and evaluate their final blind
predictions. The blind comparison uses a paired interval and the preregistered
practical margin.

<!-- Pending frozen evidence: F1–F6; T1–T3; model choice, calibration and
supplied-kick results; limitations, abstract and final references. Add the
registered team number at typesetting. -->

## Report on the Use of AI

Codex assisted with validation code and this methods draft. The final report
will record the exact queries and complete outputs used in writing, along
with the systems used for computational development. The team will verify
the implementation and the evidence underlying all reported results.
