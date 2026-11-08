# Pre-selection review

The current evidence is `upc2026-wp3-v1`. The review neither changes the frozen files nor assigns a model for the next release. Keep the diagnostics below separate from the manuscript's frozen numerical claims until the next evidence package is published.

## Reproduce

From the repository root:

```sh
python -B -m physics.audit_frozen_v1 . WP2_CHECKOUT/inference/selection-v1/predictions.csv.gz
python -B -m paper.check_release_consistency releases/upc2026-wp3-v1 --abstract PATH_TO_00_SUMMARY_TEX
python -B -m figures.render_paper_figures . PRESENTATION_OUTPUT
```

The consistency check tests the v1 abstract's display values, probability identities, T2 and T3 reconciliation, and claim source selectors. Existing broad ledger entries index source groups. Numerical comparisons at the individual claim level require a scalar `numeric_key` and `numeric_value` in the ledger.

The alternative region-width replay requires the sealed blind truth and case strata. The custody owner can run the following command. It checks the input hashes and verifies the frozen-width replay before reporting the exploratory grid results. The original scoring protocol remains the reference.

```sh
python -B -m validation.region_grid_sensitivity --repository . --release releases/upc2026-wp3-v1 --private PRIVATE_RUN_DIR --draws LOCKED_DRAWS --point-status LOCKED_POINT_STATUS
```

The fixed-launch drag sweep is a physical sensitivity, not an arrival-time posterior. The rejected M3 Reynolds values are evaluated trial states, not latent truth. The trigger counts can be reproduced from the public selection forecast. Assignment of those triggers to core or challenge strata requires the custody join.

Matched parameter-rank calibration belongs to [the inference QA record](../inference/qa-v2/calibration-manifest.json). It measures inference implementation under the generating assumptions. Blind crossing calibration tests a separate predictive question.
