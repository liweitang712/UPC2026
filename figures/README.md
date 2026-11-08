# WP3 validation figures

F5 and F6 are generated from the WP3 input freeze and the locked blind
forecast pair. Figure methods follow [the figure specification](../spec/figures-and-paper.md)
and [the v1 protocol](../validation/protocol-v1.json). Python 3.10+ and
Matplotlib are required for rendering. The evidence checks use the standard library.

## Preview and checks

From the repository root:

```sh
python -B -m unittest discover -s figures/tests -v
python -B -m figures.render_wp3 --demo --output figures-preview
```

The demo uses independent constructed forecasts, carries a visible
illustrative label and uses a separate demo run ID. Keep its numbers out of
the contest paper and results release.

## Formal rendering

WP2 provides `point-status.csv` with header
`case_id,model_id,scenario_id,point_status`. Use `available` when the model
offers a point recommendation and `abstained` when it provides at least one
resolved forecast draw but withholds a point. Provide one row for each
case/model/scenario with any resolved weight. The draw CSV must have
contiguous rows within each case/model/scenario bundle so it can be processed
without loading the entire draw file into memory. The order of bundles can vary.

WP3 includes this file when locking the blind forecasts. From the repository root:

```sh
python -B -m validation.locked_score --private PRIVATE_RUN_DIR --split blind freeze --predictions predictions.csv --config forecast.json --point-status point-status.csv
python -B -m figures.render_wp3 --private PRIVATE_RUN_DIR --output NEW_OUTPUT_DIR
```

The renderer checks the blind prediction lock, selected pair, point-status hash,
truth hash, and frozen scoring strata before reading the underlying CSV evidence.
It creates vector PDF and PNG files, English captions, per-stratum aggregate
CSV files and `figures_manifest.csv` under a new output directory. Release
the formal assets through WP3 after the blind result has been reviewed.

- **F5** uses exact entry and arrival probabilities. Report decile counts
  even when support falls below the locked minimum, with Wilson 95% intervals
  on displayed observed rates. Technical failure includes missing and
  invalid bundles and unresolved forecast mass. The point-abstention
  denominator is the resolved-forecast population with locked point status.
- **F6** uses the 0.10 m highest-mass grid, ties included at the region
  cutoff, and the locked minimum plane-conditioned effective sample size.
  Partial technical failure is tracked in F5. A conditional region in F6
  uses the resolved plane-crossing mass. Paired crossing RMSE uses the
  conditional mean on the models' shared supported true crossings. Report
  the selected-minus-comparator difference and the 95% percentile interval
  from the locked paired bootstrap. Leave a row unresolved when it falls
  below the locked overlap minimum.

The single-factor display panels pool the four single-factor strata.
Individual stratum results remain in the CSV files. The challenge stratum
is labeled separately. CSV probabilities are on the 0–1 scale.
