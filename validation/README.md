# WP3 validation

WP3 owner is Wukong0515 ([Issue #3](https://github.com/liweitang712/UPC2026/issues/3)).
The first implementation covers the primary center-in-goal Brier score from the
[validation protocol](../spec/validation.md) and uses the
[shared CSV fields](../spec/schema.md). It requires Python 3.10+ and uses the
standard library. It can run independently of the WP1 solver.

From the repository root, run the public synthetic checks with:

```sh
python -B -m unittest discover -s validation/tests -v
```

After predictions are locked, score the corresponding frozen split locally:

```sh
python -B -m validation.score_entry --run-id YOUR_RUN_ID --split blind --models B0 B1 --cases cases.csv --truth truth.csv --predictions predictions.csv --output metrics.csv
```

Use the expected model IDs from the frozen protocol. The scorer expects one
declared observation scenario per case and returns rows per stratum, scenario
and model. The output path must be new. It emits ordinary Brier loss on
exact-probability forecasts and failure-penalized Brier loss on every case with
resolved truth. For a partially unresolved prediction the penalized score uses
the worse endpoint of the probability range. Missing or invalid draw bundles
score one. The scorer accepts a draw-weight sum within an absolute tolerance
of 1e-9 and normalizes that floating-point discrepancy before scoring.
It checks only the columns needed for this event score.

- `n_total` counts all locked cases, including unresolved truth.
- `n_eligible` counts cases with a physical truth label.
- `n_scored` counts the forecasts in the specific metric's mean.
- `n_failed` counts eligible cases with unresolved forecast weight or missing
  or invalid forecasts. Intervals are blank in this first implementation.

The split design, independent truth generator, secondary scores, paired
bootstrap and figures are subsequent WP3 deliverables. Run the final blind
score only after WP2 submits the locked forecast bundle. Keep unreleased truth
and generation seeds outside the shared repository.
