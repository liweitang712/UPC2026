# Problem B inference and predictive reporting

Read the public observations and constants from [case.json](case.json). Follow [schema.md](schema.md) for units, event codes, result fields, probability denominators and missing values. Use the forward models in [physics.md](physics.md). The [model registry](models.csv) and [validation protocol](validation.md) govern the model IDs, input splits and model-selection thresholds. This specification defines what to estimate from the two frames and which diagnostics accompany the estimates.

## Inputs and model targets

Each fit receives only the case ID, known launch center, two reported times and center coordinates, physical configuration and a predeclared uncertainty scenario. Stack both three-coordinate frames in schema order. Use the same observation inputs for every candidate. Keep truth events, later positions and target-plane coordinates out of inference, prior tuning and scenario selection. Freeze any required preprocessing before validation.

Let $F(\theta)$ be the six forward-modeled coordinates, $\mathbf q$ their reported values and $L(\mathbf q\mid\theta)$ the scenario likelihood. The parameter target is

$$
p(\theta\mid\mathbf q)\ \propto\ L(\mathbf q\mid\theta)\,\pi(\theta).
$$

For the airborne forecasting model, require a parameter state to remain in free flight through the last observation and to start the prediction window before reaching the goal plane. Give an explicit applicability reason if the provided input falls outside that domain. The validation protocol must document any such fixture and how it is scored. Keep ground and miss outcomes after the observation window in the predictive sample. When only the applicability of B2 fails, preserve the failed weight and reason.

| Model | Estimation |
|---|---|
| **B0** | Estimate $\mathbf v_0$ in the analytic gravity model. For independent equal-variance Gaussian coordinates, the unconstrained fit is $\hat{\mathbf v}_0=\sum_i t_i[\mathbf q_i-\mathbf r_0+\tfrac12gt_i^2\mathbf e_z]/\sum_i t_i^2$. Use weighted or generalized least squares for Gaussian covariance variants. Use the specified prior or physical support and the corresponding likelihood for uncertainty draws. |
| **B1** | Report the exact three-point prediction as a deterministic reference. For uncertainty, draw the six latent frame coordinates under a flat latent-coordinate reference prior and the same measurement model, then transform each draw to the time-domain quadratic. The six coordinates are sampled jointly when the scenario uses covariance. |
| **B2** | Use the same latent-coordinate draws as B1 when practicable. Interpolate in $x$ as defined in the physics specification. This shares uncertainty in the longitudinal frame coordinates and leaves time-based summaries unavailable. Track draws that violate the spatial model's ordered-knot requirement. |
| **M1–M3** | Evaluate the two-frame likelihood with the physical forward model. Fit $\mathbf v_0$ and the model's effective coefficients. Fix the ball curve, air and wind configuration within each fit. For M3 refit the anchor and the other free parameters for every registered curve scenario. |

For the flat latent-coordinate reference used by B1/B2, direct Gaussian draws are $\mathbf q+\boldsymbol\epsilon$ for centered Gaussian measurement error. In a rounded Gaussian scenario draw a pre-round value uniformly in each observed cell, then add a draw from the centered error distribution. This yields the correct reference posterior by integrating the latent pre-round coordinates. With rounding alone use the uniform cell draw. Apply physical or applicability constraints explicitly and report their discarded or failed mass under the predeclared policy. Numerical failures must never disappear into a sampling filter.

## Measurement likelihoods

Use separate scenario IDs for each assumption. A printed decimal place describes resolution if the source is a rounding process. It supplies no estimate of camera accuracy.

1. **Gaussian reference.** Treat $\mathbf q=F(\theta)+\boldsymbol\epsilon$ with $\boldsymbol\epsilon\sim N(\mathbf0,\Sigma)$. The legacy benchmark uses independent coordinates with $\sigma=0.010\,\mathrm m$. A Gaussian noise sweep can use the legacy $\sigma$ values 0.003, 0.005, 0.010, 0.020 and 0.040 m if registered. Use a Cholesky solve for correlated Gaussian residuals and retain the log-determinant when comparing normalized likelihoods across noise models.
2. **Rounding alone.** With centimetre rounding and exact input times, require each forward coordinate $\mu$ to lie in its reported half-open cell $[q-h,q+h)$ with $h=0.005\,\mathrm m$. The likelihood is an indicator. The $h/\sqrt3\simeq2.89$ mm scale describes a uniform rounding error assumption.
3. **Rounding after Gaussian error.** For one coordinate with $\sigma>0$, use
   $$
   \Pr(q\mid\mu,\sigma)=
   \Phi((q+h-\mu)/\sigma)-\Phi((q-h-\mu)/\sigma).
   $$
   Multiply cell probabilities for independent errors, evaluating them on a stable log scale. Use upper-tail probabilities when both arguments are in the upper tail. A correlated scenario needs the joint Gaussian box probability or an equivalent latent-variable computation.
4. **Structural observation variants.** Test anisotropic and correlated camera error, shared calibration offsets and uncertain frame times separately where registered. Use a positive-definite covariance or an explicit low-dimensional latent error model. Specify the timing model, preserve the order of the two frame times, and propagate any timing nuisance parameter through the forward evaluation. Keep these nuisance distributions externally specified unless independent calibration data support fitting them.

The case's known launch position is fixed in the main model. For equally spaced frames with independent coordinate errors on the two measured frames, the three-point acceleration noise is $\sqrt5\,\sigma/(t_1)^2$. This diagnostic assumes exact $t_0,t_1,t_2,\mathbf r_0$ and precedes uncertainty in the plane-crossing time.

## Priors and local identifiability

Record every prior as a normalized distribution or as a density with its support and normalization policy. Retain compatible prior choices when comparing nested models. The legacy M2 reproduction uses the following choices. These are scenario defaults rather than externally calibrated distributions.

| Quantity | Legacy reference prior |
|---|---|
| $v_{x0}$ | Uniform on $(8,48)\,\mathrm{m\,s^{-1}}$. |
| $v_{y0}$ | Uniform on $(-20,20)\,\mathrm{m\,s^{-1}}$. |
| $v_{z0}$ | Uniform on $(0,20)\,\mathrm{m\,s^{-1}}$. |
| $C_D$ | $N(0.27,0.14^2)$ truncated to $(0.08,0.55)$. |
| $C_y,C_z$ | Centered independent normals with standard deviation 0.22 before truncation to $\sqrt{C_y^2+C_z^2}<0.55$. |

In M1 omit the transverse prior. In M3 apply the drag prior to the anchor within the reference curve's admissible support, recording its normalization when needed. Freeze at least two prior sensitivities, one changing the drag center or scale and one changing the transverse scales or support. Keep the same likelihood in these comparisons. Cover validation cases near the launch-speed support boundaries and label unsupported cases. Document any change to the prior used for the reference reproduction.

At a stated fit and a smooth measurement scenario, compute the observation Jacobian $J=\partial F/\partial\theta$, whiten it by the observation error scale and normalize parameter columns with declared reference scales, preferably prior standard deviations. A useful diagnostic is the SVD of $\Sigma^{-1/2}J S_\theta$. Report the full spectrum and, for the aerodynamic spectrum, orthogonally project the whitened and scaled aerodynamic columns off the three initial-velocity columns before the SVD. Check derivative-step stability or compare independent derivatives. For rounding alone, use an explicit reference scale such as the equivalent uniform-cell standard deviation for this diagnostic. Interpret its singular values as local sensitivities under that scale.

Compare weak directions to prior-to-posterior contraction and correlations. When normalized by prior scale and Gaussian error, a singular value near one gives a local likelihood precision comparable to the prior precision in that direction. Choose the weakest aerodynamic directions, perturb within support, and re-fit initial velocities or profile the likelihood while holding that perturbation. Propagate those changes to the plane and report the position shifts in metres or a change in event class. The example figure should include two parameter sets consistent with the same predeclared early-data criterion. Prefer a pair on opposite sides of the crossbar if one exists. Otherwise report their observed differences and landing separation without implying a boundary switch.

## Posterior computation and quality gates

Initialize with an analytic baseline or a constrained nonlinear fit. For a smooth likelihood, a scaled Gauss–Newton or Laplace Gaussian around a suitable mode is an acceptable importance proposal. Evaluate the full likelihood and priors for every proposal draw and normalize $\log w_i=\log L_i+\log\pi_i-\log q_{\rm prop}(\theta_i)$ using a log-sum-exp. Respect hard bounds and evaluate the proposal density for the actual sampling distribution, including a mixture or truncation if used. When the posterior has hard rounding cells or appreciable skew, use a support-aware or broader proposal, a suitable conditional sampler or an independently checked alternative. The sampler is acceptable when its numerical and stochastic diagnostics meet the frozen protocol.

The prediction run must report attempted draws, finite weights, rejected or failed proposals and reasons, effective sample size $1/\sum_i \tilde w_i^2$, largest normalized weight, run seed and numerical settings. Keep zero-weight prior rejections distinct from numerical failures. If resampling, retain pre-resample ESS and the number of distinct propagated draws. Repeat representative fits with an independent seed and larger sample budget. Compare event probabilities, quantiles and mode rather than only parameter means. Set explicit recovery and failure thresholds before validation, including the minimum effective support for each conditional estimate. Flag low ESS or sensitivity to one proposal or seed. Log retries and stop at a declared computation limit if diagnostics remain poor.

For matched statistical checks, simulate parameters from the same prior and observations from the fitted likelihood, then check posterior ranks and conditional coverage. Freeze the sampling plan and distinguish it from independently generated prediction stress tests. The run manifest records all parameters that affect reproducibility. [SBC methodology](https://arxiv.org/abs/1804.06788) · [Importance-sampling diagnostics](https://www.jmlr.org/papers/v25/19-556.html)

## First-event probabilities and conditional summaries

Propagate the weighted parameter draws to their first events using the physical numerical settings. Write one prediction record for each retained draw. Keep coordinates missing when no valid plane event exists. B2 can supply spatial coordinates at the plane with arrival time unavailable. Separate physical no-reach outcomes from numerical failures or unsupported inputs.

Let $C$ be first forward plane crossing, $G$ be center inside the goal on that crossing, and $H$ be the clearance event. Read the exact classification rules and denominators from the schema. The resulting probabilities satisfy $H\subseteq G\subseteq C$. For complete classification, verify $P(G\mid D)=P(C\mid D)P(G\mid C,D)$ and the mutual-event weight sum. When solver failure mass is nonzero, report it separately with the schema's probability bounds. For example, the unconditional goal probability is bounded by the known goal weight and that weight plus the unresolved weight, both relative to total assigned weight. The ratio within resolved crossings is a conditional statistic of that resolved sample and requires its own denominator.

Report the following quantities where their conditioning support is adequate.

- Event probability, assigned and resolved weight, effective sample size or draw count as applicable, and reasons for missing estimates. A zero observed count is an estimate under the sampled model. Keep any Monte Carlo upper bound distinct from a proof of impossibility.
- $T,Y,Z$ medians and marginal 95% intervals conditional on $C$, and separately on $G$. At the case's second frame report $T-t_2$ if the model has a time law. For spatial-only B2 give $Y,Z$ summaries.
- Joint 50%, 80% and 95% regions for $(Y,Z)$ conditional on $C$, as needed by the validation protocol. An ellipse based on a weighted covariance and empirical Mahalanobis distance quantile is acceptable for a roughly elliptical cloud. For a degenerate or multimodal distribution use an explicitly defined alternative such as a highest-density grid region, or mark the ellipse unavailable. Keep any regularization and minimum effective support visible.
- A two-dimensional conditional mode of $(Y,Z)\mid G,D$ computed using the goal samples only and a density restricted to the goal interior. State kernel, bandwidth, grid, boundary treatment and maximum search rule. The legacy comparison uses 0.05 m bandwidth and a 0.02 m grid, with a 0.10 m bandwidth and a second seed as checks. Declare a deterministic tie rule and report separated competing modes when a single peak is unstable.

When there are no or too few plane or goal draws, return the available event probabilities and diagnostics. Mark the affected conditional intervals or mode missing with the corresponding reason. When the truth case falls into a subgroup whose model prediction has no usable conditional distribution, retain that case in the validation counts and report the missingness rate.

## Sensitivity, handoff and acceptance

Rerun inference when changing the observation scenario, prior or aerodynamic model. Keep those three perturbations separately identifiable and report numerical or Monte Carlo variability using repeat runs under identical assumptions. For a changed reference ball, wind or physical scenario, fit again to the same first two frames and report the resulting mode, probabilities, intervals and failures side by side. Report model-structure variation across cases or as a scenario envelope. A mixed posterior needs declared, defensible weights and a method for conditioning the mixture on the observations.

Deliver schema-compatible per-draw predictions and case summaries, a run manifest, an observation scenario comparison table, a prior sensitivity table, the Jacobian and profile diagnostics, and the early-compatible trajectory pair and plot data. Join inputs by the public case and scenario IDs. Provide code and input versions, seeds, priors, tolerances and a reproduction command to the integration owner. Keep validation truth in its separate handoff.

Acceptance requires the following checks.

1. **Likelihood limits.** Reproduce the analytic B0 Gaussian fit. Confirm the interval likelihood approaches the rounding indicator as noise decreases at points strictly inside or outside a cell. Check finite values for narrow tail cells and check a correlated Gaussian against an equivalent whitened representation.
2. **Predictive accounting.** Test no crossing, a crossing outside the frame, a degenerate cloud and an intentional numerical failure. Check the event identities, conditional denominators, missing coordinates and probability bounds. Verify that known misses contribute to unconditional denominators.
3. **Numerical versus sampling stability.** Hold sample parameters fixed for the integration comparison. Hold integration fixed when repeating the sampling and KDE comparisons. Compare against the frozen tolerance and diagnostic thresholds.
4. **Legacy benchmark.** Reproduce B1 with the point observations and recover the legacy M2 Gaussian-reference results within declared Monte Carlo tolerance when using its priors and equivalent integration settings. Benchmark values are about 0.398 s median crossing, 0.902 geometric entry probability and 0.835 radius-clearance probability. Differences under a new likelihood, prior, applicability rule or bandwidth belong in the scenario comparison.
5. **Blind model comparison.** Evaluate both arrival and entry probabilities over the full frozen set. Report event Brier scores, calibration and failure counts. For cases with truth plane coordinates, report conditional coverage and a two-dimensional energy score when a distribution is available, plus the availability denominator. Compare point RMSE on a shared subset and show its size. Keep matched and misspecified validation strata separate. Use the protocol's predeclared selection gates for added model complexity.
