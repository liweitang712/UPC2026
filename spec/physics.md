# Problem B physical and numerical models

[case.json](case.json) supplies the public example and its constants. [schema.md](schema.md) governs serialized fields, event names, geometric boundaries and priority. [models.csv](models.csv) supplies the model IDs. The equations and checks here define what the forward models calculate. In SI units the right-handed axes point toward the goal ($+x$), to the kicker's left ($+y$) and upward ($+z$).

## Forward calculation

Accept a model ID, a case or public validation input, the model parameters and the numerical configuration. Expose the following operations to inference and validation.

- Evaluate the modeled ball center at both supplied observation times. Preserve the schema's time and coordinate order. Reject nonfinite parameters and invalid times with an explicit status.
- Predict the first event and expose whether the calculation reached the goal plane. For a plane event, provide its coordinates and, where the model has a time law, its time. A trajectory that reaches the plane outside the mouth is still a plane crossing. Use the schema to assign the center and clearance classifications.
- On request, return a trace with the launch, exact observation times and terminal event included. A time-domain trace provides $t,\mathbf r,\mathbf v$. For M3 also supply relative airspeed, $Re$, $C_D$ and curve-domain status along the trace. B2 provides spatial samples.
- Return the reason for an unsupported input or failed numerical evaluation. A failed calculation and a valid trajectory without a crossing have separate statuses. Never use a zero coordinate as a missing-value sentinel.

Use the known initial center $\mathbf r_0$. Interpret the free-flight models as beginning immediately after launch. Predictions stop at the first event or the configured horizon. For likelihood evaluation the implementation may also return mathematical continuations to the two observation times, with their physical validity flagged. The inference contract controls their eligibility.

## B0, B1 and B2

| ID | Inputs beyond the case | Evaluation | Event and output |
|---|---|---|---|
| **B0** | Initial velocity $\mathbf v_0$ | $\mathbf r(t)=\mathbf r_0+\mathbf v_0 t-\tfrac12gt^2\mathbf e_z$. Estimate $\mathbf v_0$ from both frames as specified in [inference.md](inference.md). | Solve the plane equation analytically for a forward crossing and compare it to the first turf event. Supply time and coordinates for a crossing. |
| **B1** | Initial velocity and constant acceleration, or two latent frame centers that determine them | $\mathbf r(t)=\mathbf r_0+\mathbf v_0t+\tfrac12\mathbf a t^2$. For $s_i=(\mathbf r_i-\mathbf r_0)/t_i$, use $\mathbf a=2(s_2-s_1)/(t_2-t_1)$ and $\mathbf v_0=s_1-\tfrac12\mathbf a t_1$. | Select the earliest in-domain positive-time root with positive $v_x$. Check turf first. Handle a vanishing quadratic term with the linear limit and use a numerically stable quadratic root computation. |
| **B2** | Two latent frame centers with strictly increasing $x$, following the launch center | Fit independent quadratic interpolants to $y(x)$ and $z(x)$ through the launch center and both frames. Use Newton divided differences or an equivalent stable formulation. Reject degenerate spacing with a reason. | Advance in $x$ and compare the first turf intersection in that direction with the goal-plane position. Supply plane coordinates and mark arrival time unavailable. Include B2 in spatial and event comparisons when the interface supports them. |

B2 is a spatial extrapolator. It assumes increasing $x$ throughout the extrapolation and has no launch velocity or arrival-time estimate. Preserve both longitudinal and transverse frame errors when producing B2 draws. Compare the analytical turf and plane abscissae directly. At an exact tie give priority to turf, and use only a declared spatial root tolerance to resolve numerical ambiguity. The drag-only identity below is a model check and can also motivate a separately named straight-line lateral sensitivity. Keep the B2 ID reserved for the quadratic spatial baseline above.

For $v_x>0$, $y''(x)=(a_y-v_y a_x/v_x)/v_x^2$. In still air, drag is collinear with the velocity and cancels from this expression. With gravity as the only other force, $y(x)$ is linear and $z''(x)=-g/v_x^2$. For a given time-domain trajectory an independent spatial integration, using $\mathrm dt/\mathrm dx=1/v_x$, should agree at the plane on strictly forward segments.

## M1, M2 and M3

Define $\mathbf u=\mathbf v-\mathbf w$, $U=\|\mathbf u\|$, $A=\pi R^2$, and $\beta=\rho A/(2m)$. Here $\mathbf w$ is air velocity in the same axes, $R$ is ball radius, $m$ is mass and $\rho$ is air density. $C_D,C_y,C_z$ are dimensionless, $\beta$ has units $\mathrm m^{-1}$, and acceleration is in $\mathrm{m\,s^{-2}}$. The common equations are

$$
\dot{\mathbf r}=\mathbf v,\qquad
\dot{\mathbf v}=-g\mathbf e_z+\beta U[-C_D\mathbf u+\mathbf b\times\mathbf u],
\qquad \mathbf b=(0,-C_z,C_y).
$$

Use zero wind in the primary fitted models unless the scenario supplies a fixed external wind. Set the aerodynamic acceleration to zero when $U=0$. For $C_D\ge 0$, the drag acceleration dotted with $\mathbf u$ is $-\beta C_D U^3$, and the cross-product contribution is orthogonal to $\mathbf u$. For $\mathbf u$ along $+x$, positive $C_y$ and $C_z$ accelerate toward $+y$ and $+z$, respectively. The instantaneous magnitude coefficient of the transverse force is $\|\mathbf b\times\hat{\mathbf u}\|$. The two coefficients describe effective force. At launch any coefficient vector component parallel to the initial relative velocity gives zero instantaneous force, and its later effect is weak when the flight direction changes little.

| ID | Fitted parameters | Aerodynamics |
|---|---|---|
| **M1** | $(v_{x0},v_{y0},v_{z0},C_D)$ | Constant $C_D$. Set $C_y=C_z=0$. |
| **M2** | $(v_{x0},v_{y0},v_{z0},C_D,C_y,C_z)$ | Constant $C_D,C_y,C_z$. This is the legacy model family. |
| **M3** | $(v_{x0},v_{y0},v_{z0},C_D^\ast,C_y,C_z)$ for each fixed reference curve | Use the reference curve's shape and fit its early drag anchor. Keep the effective transverse coefficients constant for this model ID. |

For M3 calculate $Re=\rho(2R)U/\mu$ with dynamic viscosity $\mu$ in $\mathrm{Pa\,s}$. Predeclare a reference speed $U_\ast$ in the early flight range and use the same anchor policy across curve scenarios:

$$
C_D(Re)=C_D^\ast+D_{\rm ref}(Re)-D_{\rm ref}(Re_\ast),
\qquad Re_\ast=\rho(2R)U_\ast/\mu .
$$

Store tabulated experimental curves and interpolate by a declared method that preserves local shape and positive drag. A piecewise-linear interpolant is sufficient. State the behavior outside the source domain before running comparisons. Flag every extrapolated trajectory and report its weight. Use an explicit failure status when a curve cannot be evaluated under the configured policy. Candidate anchors that would give nonpositive drag over the usable curve domain are outside the model's support. Freeze that support before fitting and retain scenario-specific normalizations if comparing evidence. A constant reference curve must reduce M3 to M2 for otherwise identical inputs.

For each curve, record the ball, orientation and spin conditions, experimental speed or Reynolds range, source figure or table, digitization method, interpolation, reference density and viscosity if used in conversions, and out-of-domain policy. Compare the case's in-flight $Re$ envelope to the actual transition interval of each reference curve. A simple transition function can support synthetic stress testing when separately labeled. Use the published curve when a scenario claims to represent a tested ball.

Asai and Seo provide measured drag across ball models. Hong and Asai report effects of panel geometry and orientation. The 2026 four-ball wind-tunnel comparison supplies a Trionda example, and the independent Trionda orientation study separates six fixed orientations. The case does not identify a ball model. [Asai and Seo](https://doi.org/10.1186/2193-1801-2-171) · [Hong and Asai](https://doi.org/10.1038/srep05068) · [Four-ball wind-tunnel study](https://www.nature.com/articles/s41598-026-56275-1) · [Trionda orientation study](https://doi.org/10.3390/fluids11050128)

## Independent truth scenarios

The validation owner generates truth independently and holds it back from inference. Use the IDs and frozen ranges in the [validation protocol](validation.md). Keep the forward estimator and the following scenario mechanisms separately configurable.

- Change wind, drag curve, ball or fixed panel orientation one at a time before testing combinations. Record whether a scenario uses measured curve data or constructed stress parameters.
- For spin-dependent truth define $S_\perp=R\|\boldsymbol\omega\times\hat{\mathbf u}\|/U$. A lift acceleration of magnitude $\beta U^2 C_M(Re,S_\perp)$ points along $\boldsymbol\omega\times\mathbf u$ for positive $C_M$. Set it to zero when the cross product is zero. Set spin axis, magnitude and any decay from the generating scenario. Low-spin time-varying transverse force can be modeled separately with specified amplitude, timescale and phase or random process. Express its acceleration in the plane orthogonal to $\mathbf u$. Record these choices in the truth metadata.
- Generate rounding, correlated coordinate error and timing error in the observation layer. A perturbed observation does not change the truth trajectory. Record contact and geometric variants separately where their event definitions differ from the primary prediction.

Published spin experiments can supply force scales and plausible regimes. Their full-trajectory fit residuals measure a different task from the two-frame extrapolation. [Goff and Carré, spin and lift](https://doi.org/10.1088/0143-0807/31/4/007) · [Goff et al., measured trajectory curves](https://doi.org/10.1088/1361-6404/aa6fcd) · [Passmore et al., rotating-ball loads](https://doi.org/10.1177/1754337116677429) · [Hong and Asai, unsteady force](https://www.jstage.jst.go.jp/article/jjpehss/55/2/55_09053/_article/-char/en)

## Event location and numerical acceptance

Use a coupled position–velocity integrator, such as fixed-step RK4 with a demonstrated step limit or adaptive Runge–Kutta with declared error controls. Evaluate observation times exactly by shortening a step or using accuracy-matched dense output. Root-find the plane and turf candidates within the same step using dense output or reintegration from its start. Locate both before choosing the earliest. Apply the schema's direction tests, surface tolerances and tie priority to these localized events. In particular, distinguish launch on the turf from a later landing. Near tangencies, bracket and refine or subdivide until the event order and direction are resolved. Run the geometry classification on the located state. Record numerical tolerances, step settings, horizon and boundary-near flags.

The physics handoff includes the callable forward interface, reproducible public-case traces, scenario and curve metadata, and checks with expected and computed values. Acceptance covers the following cases.

1. **Analytic vacuum.** With drag and transverse terms disabled, compare both frame centers and a plane crossing against B0. Include an analytic first-turf case and a plane/turf tie.
2. **Analytic drag.** Set gravity and transverse force to zero and use $v_{x0}>0$ and $k=\beta C_D>0$. Compare $v_x(t)=v_{x0}/(1+kv_{x0}t)$ and $x(t)=x_0+\ln(1+kv_{x0}t)/k$ in an elevated test case.
3. **Event fixtures.** Exercise goal center, both post boundaries, crossbar, clearance boundaries, launch then landing, turf before plane, plane before turf, a backward or tangential plane encounter, no plane before the horizon and a deliberate solver failure. Report time error in seconds and spatial error in metres. Require consistent classification outside the schema's near-boundary tolerance.
4. **Convergence.** Hold parameters fixed and rerun the public case and representative validation-edge fixtures with finer numerical settings. Compare observation coordinates, event time where defined, plane coordinates and event class against the frozen tolerances. Keep the independent truth integrator's numerical error materially smaller than the prediction tolerance.
5. **Baseline and limits.** Reproduce the public B1 reference $T\simeq0.405008$ s, $Y\simeq2.494824$ m and $Z\simeq1.920367$ m using the point observations. Check M2 with both transverse coefficients zero against M1, and M3 with a flat reference curve against M2. Document B2's spatial-only output.

Provide the integration settings and crossing fixtures to validation. Provide nominal and sample trajectories, including the observation cutoff and domain flags, to the figure and paper owners. Use the predeclared comparisons in the [validation protocol](validation.md) to select the paper's models.
