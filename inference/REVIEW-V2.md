# WP2 revision 2 review

The frozen report remains [upc2026-wp3-v1](../releases/upc2026-wp3-v1/release.json).
Its public F1–F4, T2 and blind comparison retain B0 as the reference and B2
as the descriptive comparator. The original prediction locks are unchanged.
The revised sampler and diagnostics are exploratory and have no fresh blind score.

On the public development inputs (84 cases), the revised 1,024-draw run
returned 16 M3, 3 M2 and 3 M1 complete abstentions, all with no finite
proposal. M3 rejected 17,338 strict curve support proposals without turning
an individual rejection into a whole-case error. These counts do not meet
the 1% candidate selection gate and cannot be compared directly with the
86 M3 failures from a different, 260-case selection split. Do not promote
an aerodynamic candidate on this evidence.

The 192 matched synthetic fits in [qa-v2](qa-v2/) passed the prespecified
parameter rank screen under independent 10 mm Gaussian measurement noise.
Minimum ESS by model was 653, 111 and 243 respectively (rounded). This is
a finite-sample screening result, not evidence of physical coverage under
misspecification. The selected B0 uses an improper flat reference prior;
a prior predictive SBC for that prior is undefined. The frozen benchmark
continues to show joint region undercoverage for both baselines.

The public M2 identifiability record contains posterior/prior SD ratios,
correlations, projected weak directions, velocity refits and first events
along two profile directions. Fixed-parameter half-step checks are kept
separate from the independent-seed sampling comparison. The initial
16k/32k runs exceeded the 0.03 m endpoint tolerance (0.032 m).
The 32k/64k comparison passed the probability and endpoint tolerances
(0.21 percentage points and 0.0168 m), but the entry mode shifted
0.146 m (limit 0.10 m). The exploratory M2 mode is unstable and should
not be used as a point recommendation. See [the repeat](qa-v2/repeat/public-manifest.json).

The review does not clear the revised candidate for a new frozen release.
A fresh holdout belongs to WP3. Inference, physics, validation and figures
passed 41 local unit tests in total; the frozen release files were not edited.

Run from the repository root on the integrated WP1 interface:

```sh
python -m pip install numpy matplotlib
python -B -m unittest discover -s inference/tests
python -B -m inference.qa NEW_QA --workers 10
python -B -m inference.qa NEW_REPEAT --part public --public-budget-multiplier 2
python -B -m inference.forecast releases/upc2026-wp3-v1/cases/development/cases.csv inference/selection-scenarios.json NEW_DEV --draws 1024 --seed 2026 --workers 8
```

The revised reporting script uses conditional ESS 100 and origin-anchored
0.10 m square cells including cutoff ties. Run
`./inference/run_public.ps1 NEW_PUBLIC` for exploratory figure assets;
the committed `wp2-public/` files are archival v1 drafts.

For the integrator: [section 03](paper/03-wp2-inference.tex) and
[section 05](paper/05-wp2-case.tex) are paste-ready handoffs for the matching
files under `sections/` in shared LaTeX. Use the frozen release figures,
not the exploratory plots, in the shared draft. Integrator owns compilation,
the discussion, and the team AI disclosure.
