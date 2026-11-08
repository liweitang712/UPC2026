# Predicting a Penalty Kick from Its First 100 Milliseconds

We infer the arrival point of a soccer ball from its launch position and two early observations. A three-dimensional flight model with gravity, quadratic drag and transverse aerodynamic force propagates measurement and parameter uncertainty to the first forward crossing of the goal plane. For the supplied kick and 1 cm assumed coordinate error, the most probable point conditional on entry is near (11, 2.9, 1.8) m. The median arrival time is 0.398 s, and the central 95% intervals for the plane-crossing coordinates are 2.16–3.61 m laterally and 1.23–2.68 m vertically. The model assigns 90% probability to a crossing within the goal rectangle and 84% to a crossing with ball-radius clearance. The nominal 95% joint region covers 118 of 120 synthetic crossings from the fitted model and 112 of 120 with wind and varying aerodynamic forces. The entry probabilities depend strongly on the assumed tracking precision.

<!-- page -->

## 1. What the goalkeeper can infer

The goal plane is x = 11 m, with y measured laterally and z upward. The center of the ball is initially r(0) = (0, 0, 0.11) m. The observations at 0.05 and 0.10 s are (1.50, 0.45, 0.44) and (2.96, 0.86, 0.74) m [1]. We estimate the distribution of (Y, Z) at the first forward crossing of x = 11 m, the corresponding arrival time, and the probability that the crossing lies in the goal. Here positive y denotes the side toward which the observed ball initially moves.

### Two direct extrapolations

With a constant acceleration on each axis, the unique quadratic through the three positions, in meters with time in seconds, is

= x(t) = 30.4t − 8t²,   y(t) = 9.4t − 8t²,   z(t) = 0.11 + 6.9t − 6t².   (1)

The first crossing occurs at 0.405 s, at (Y, Z) = (2.49, 1.92) m. As a second baseline, fitting a gravity-only trajectory to both frames by least squares gives 0.371 s and (3.22, 1.96) m. The 0.73 m difference in lateral prediction matters for a dive. Equation (1) assumes that the curvature observed during the first tenth of a second persists as the ball slows. The gravity-only fit assumes zero lateral curvature. The data invite a model between those simplifications, with forces that depend on the speed and direction of the ball.

### Why two frames leave substantial uncertainty

Let s = t/(0.05 s). With the initial position fixed, the quadratic interpolant gives weights s(2 − s) and s(s − 1)/2 to the two noisy position measurements. At 0.405 s these weights are approximately −49 and +29. At fixed time, independent 1 cm coordinate errors would therefore contribute about 0.57 m standard deviation to each extrapolated coordinate in this model. Uncertainty in the plane-crossing time changes this calculation, and the physical model regularizes the curvature. The amplification explains why a small early fit residual offers little evidence of a precise arrival point.

@ penalty/penalty_paths.png
Figure 1. A representative trajectory from the local aerodynamic fit and the exact quadratic baseline. The shaded part contains the observations. Both fits agree closely there, and their lateral paths separate during extrapolation.

<!-- page -->

## 2. Flight and observation models

Use r and v for position and velocity, w for the wind velocity, and u = v − w for the velocity relative to the air. Set β = ρπR²/(2m), where ρ is air density, R is ball radius and m is ball mass. The equations in SI units are

= dr/dt = v,   dv/dt = −g e_z + β ‖u‖ [−C_D u + b × u].   (2)

Here e_z points vertically upward, g is gravitational acceleration, C_D is the drag coefficient, and b = (0, −C_z, C_y) is a dimensionless effective lift vector. For predominantly forward motion, positive C_y produces a force toward positive y and positive C_z toward positive z. The cross product keeps this force perpendicular to u. The effective coefficients account for transverse acceleration over one short flight. The first two frames give too little information to recover a full spin vector and a separate lift law. Experiments show that spin, speed and panel construction can affect soccer-ball forces [3, 4].

We use R = 0.11 m, m = 0.43 kg, ρ = 1.225 kg/m³ and g = 9.80665 m/s², giving β ≈ 0.0541 m⁻¹. The baseline assumes still air and constant C_D, C_y and C_z. The ball dimensions and mass are consistent with IFAB Law 2 [5].

### Inference from two positions

The unknown vector is θ = (v_x(0), v_y(0), v_z(0), C_D, C_y, C_z). Conditional on θ, each observed coordinate is modeled as the integrated position plus independent, zero-mean Gaussian error of standard deviation σ. The posterior is proportional to the parameter prior times

= exp[−(‖r_obs(0.05) − r_θ(0.05)‖² + ‖r_obs(0.10) − r_θ(0.10)‖²)/(2σ²)].   (3)

Initial velocity has a uniform prior over 8 < v_x < 48, |v_y| < 20 and 0 < v_z < 20 m/s. The aerodynamic coefficients have independent Gaussian factors with means (0.27, 0, 0) and standard deviations (0.14, 0.22, 0.22), jointly truncated to 0.08 < C_D < 0.55 and (C_y² + C_z²)^(1/2) < 0.55. These broad modeling choices allow substantial drag and signed lift. They are held fixed across the observation-error sweep. The baseline σ = 0.010 m is a working assumption for tracking error. Decimal rounding alone would imply a smaller error, about 0.0029 m standard deviation under uniform rounding to the nearest centimeter.

Five Gauss–Newton iterations initialize a local Gaussian proposal. Each of 8,192 proposals is reweighted by the full posterior divided by the proposal density. From these weighted samples we resample 4,096 draws for trajectory propagation. We integrate with fourth-order Runge–Kutta (RK4), with 25 ms steps for fitting and 10 ms steps for prediction. A bracketed RK4 substep localizes the crossing.

### Crossing and goal definitions

For each retained parameter draw, integrate to the first forward crossing of x = 11 m or a prior return of the ball center to z = R. A valid geometric center crossing satisfies |Y| < 3.66 m and 0 < Z < 2.44 m. A radius-adjusted proxy tests clearance of the side posts and crossbar by R, with the center at least R above the ground. A ball that first hits the ground is classified separately. The stricter proxy is useful near the frame. Resolving contact, bounce and the exact whole-ball crossing requires a separate model [5].

<!-- page -->

## 3. Prediction for the supplied kick

The highest estimated entry density is near (Y, Z) = (2.9, 1.8) m. We estimate the mode from the in-goal samples using a Gaussian kernel with 0.05 m bandwidth on a 0.02 m grid. Doubling the bandwidth or repeating the inference with another seed shifts the mode by less than 0.09 m. The median among all plane crossings is (2.85, 1.94) m, and the median arrival time is 0.398 s, leaving about 0.30 s after the second observation.

@ penalty/penalty_prediction.png
Figure 2. The left panel zooms in on the upper right of the goal at σ = 0.010 m. The solid frame marks the goal and the dashed frame the one-radius inset. The joint 95% ellipse uses the mean and covariance of the plane crossings and the 95th percentile of their squared Mahalanobis distances. The right panel shows how the entry probabilities change with σ.

The 95% marginal intervals over all plane crossings are [0.378, 0.419] s for arrival time, [2.16, 3.61] m for Y and [1.23, 2.68] m for Z. Conditional on entry, the 95% intervals for Y and Z are [2.16, 3.52] m and [1.22, 2.40] m. All draws in this run reached the plane. Of these, 90.2% crossed within the goal rectangle and 83.5% met the radius-clearance criterion. The effective sample size of the importance proposal was about 7,880 out of 8,192 draws.

<!-- page -->

## 4. Verification and stress tests

The RK4 vacuum test agrees with the analytic crossing within 6 × 10⁻¹⁰ m in position. Reducing the nominal trajectory step from 20 to 5 ms shifts the crossing by about 4 × 10⁻⁹ m. The validation sets comprise 120 synthetic shots each, selected to reach the plane in the air and yield at least ten predictive crossings. Launch velocities are sampled over 22–35 m/s forward, −7 to 9 m/s lateral and 4–10 m/s vertical. Each synthetic observation has 1 cm coordinate noise. In the second set the generating model adds longitudinal wind up to 2 m/s in either direction, crosswind up to 4 m/s, a speed-dependent drag increase up to 0.18, and 2 Hz fluctuations in C_y and C_z with amplitudes 0.14 and 0.08. Prediction uses the same still-air model for both sets.

| Synthetic test | Joint 95% region coverage | All-case RMSE (m) | Paired RMSE, physical / quadratic (m) |
| Matched physics | 118/120 (98.3%) | 0.509 | 0.513 / 1.105 (106 shots) |
| Perturbed physics | 112/120 (93.3%) | 0.587 | 0.583 / 1.289 (104 shots) |

RMSE is the root mean squared Euclidean error of the predicted mean in the goal plane. The paired comparison includes the shots for which the constant-acceleration extrapolation returns a crossing above the turf. The coverage proportions have sampling uncertainty and refer to the synthetic test distributions.

### What sets the uncertainty

| Assumed coordinate σ (m) | Center-in-goal probability | Radius-clearance probability |
| 0.003 | 100.0% | 99.5% |
| 0.005 | 98.9% | 95.7% |
| 0.010 | 90.2% | 83.5% |
| 0.020 | 74.4% | 65.0% |
| 0.040 | 66.9% | 57.9% |

The first center-in-goal percentage rounds to 100.0%, with two misses among 4,096 trajectory draws.

With six measured coordinates and six model parameters, a close fit can coexist with a wide spread of future trajectories. Measurement error, the prior on the aerodynamic coefficients and model mismatch enter the calculation differently. The synthetic matched test checks the numerical inference under its own assumptions. The perturbed test probes sensitivity to physics outside those assumptions. Field calibration would require full-flight tracks from multiple balls and shots, along with measurement errors from the actual tracking system.

<!-- page -->

## 5. Practical interpretation

At 0.10 s, a goalkeeper can use the predicted crossing distribution to decide how far laterally to commit and whether to reach high or low. Arrival time is measured from the kick, so the time remaining for a response is the predicted arrival time minus 0.10 s. The fitted uncertainty is for ball flight to the goal plane and excludes a model of the goalkeeper's reach, reaction time or saving probability.

The implementation accepts another pair of three-dimensional measurements at 0.05 and 0.10 s. It reports the frequency of ground-first or other non-crossing trajectories alongside the conditional crossing distribution. Close to a post, the joint distribution matters because a marginal interval on each coordinate obscures which draws miss the frame. The model is designed for an airborne, forward-moving shot and needs a bounce model for trajectories that contact the turf.

The 2022 UPC gold paper on penalty kicks studied how selected initial velocities and spin affect a shot [2]. Here the prediction starts with observed positions and averages over the combinations of launch velocity and aerodynamics consistent with the measurements.

### References

[1] The University Physics Competition. [2026 competition problems](https://university-physics-competition.com/2026-competition), Problem B.
[2] UPC Team 480. [Analysis of the Optimal Initial Velocities and Spins of Soccer in Penalty Kicks](https://www.uphysicsc.com/2022-GM-B-480.pdf). 2022 UPC gold paper, Problem B.
[3] Asai, T., and Seo, K. [Aerodynamic drag of modern soccer balls](https://doi.org/10.1186/2193-1801-2-171). SpringerPlus 2, 171 (2013).
[4] Goff, J. E., and Carré, M. J. [Soccer ball lift coefficients via trajectory analysis](https://doi.org/10.1088/0143-0807/31/4/007). European Journal of Physics 31, 775–784 (2010).
[5] The International Football Association Board. [Law 2: The Ball](https://www.theifab.com/laws/latest/the-ball/) and [Law 10: Determining the Outcome of a Match](https://www.theifab.com/laws/latest/determining-the-outcome-of-a-match/).
[6] The University Physics Competition. [Contest rules](https://university-physics-competition.com/contest-rules), section 5.

### Report on the Use of AI

OpenAI Codex was used to develop the computational model and code, run simulations, review sources, generate figures and draft this paper. The supplied materials include the user prompt in AI_user_prompt.txt, the generated draft, and the model source and outputs. For a formal entry, append the exact queries and complete corresponding AI outputs to this section, including any subsequent AI assistance [6]. The team must verify the implementation and numerical results and be able to explain and defend them.
