# WP3 validation

The current manuscript uses the [M2 location study](../releases/upc2026-location-v2/README.md).
The steps below reproduce the archived event-first release.

WP3 owner is Wukong0515 ([Issue #3](https://github.com/liweitang712/UPC2026/issues/3)).
This work follows the [validation protocol](../spec/validation.md) and
[shared CSV fields](../spec/schema.md). Run the Python 3.10+ commands from the
repository root. The generator and scorer use the standard library.

## Frozen input handoff

Run ID `upc2026-wp3-v1` identifies the input freeze. The
[preregistration](protocol-v1.json) fixes the launch distributions, noise,
stress strata, model roster, selection gates and numerical tolerances.
These choices define a synthetic benchmark distribution.

| Split | Public inputs | Scoring truth |
| --- | --- | --- |
| Development (84) | [cases](frozen/v1/development/cases.csv) | [public truth](frozen/v1/development/truth.csv) |
| Selection (260) | [cases](frozen/v1/selection/cases.csv) | WP3 custody |
| Blind (520) | [cases](frozen/v1/blind/cases.csv) | WP3 custody |

The [freeze record](frozen/v1/freeze.json) commits to public cases, private
stratum membership and truth using SHA-256. For selection and blind inputs,
the public stratum field is `withheld`. Case IDs are shuffled within each
split, and the forecast scenario is `nominal_gaussian_10mm`. Fit from the
times, observed coordinates, and public forecast assumptions. WP3 joins the
locked prediction bundle to the sealed scoring strata by case ID. Report
alternate model configurations as separately identified sensitivity runs.

Do not regenerate v1 for prediction. The checked-in inputs are the canonical
snapshot. The generator creates a new seed set when run. WP3 retains the
original per-split seeds and verifies private hashes before scoring. The
independent solver checks event/clearance identity and bounds changes to frame
coordinates, plane coordinates, and event times under step halving.

Verify the public files and run the independent numerical/scoring checks:

```sh
python -B -c "from validation.locked_score import PUBLIC, verify_inputs; [verify_inputs(PUBLIC, split) for split in ('development', 'selection', 'blind')]"
python -B -m unittest discover -s validation/tests -v
```

## Prediction freeze and scoring

1. WP2 delivers schema-compatible `predictions.csv` for selection and a
   forecast JSON with `source_commit` and a `models` object keyed by the six
   registered model IDs. Record the exact per-model configuration, M3
   curve, region method and draw budget, plus the independent inference seed
   and reproduction command. Record refits of alternative curves separately.
2. WP3 snapshots both files and records their hashes against the case freeze.
   Use `selection` first. The score command reads the local truth only after
   all hashes match.
3. Before blind prediction, WP3 records `selection-decision.json` beside the
   private data, with `selected_model`, `comparator_model`,
   `selection_predictions_sha256`, and `rationale`. Retain the evidence
   supporting the decision. For the blind split submit the chosen pair using
   the frozen model settings. Keep the selection and blind locks as separate
   artifacts.

```sh
python -B -m validation.locked_score --private PRIVATE_RUN_DIR --split selection freeze --predictions predictions.csv --config forecast.json
python -B -m validation.locked_score --private PRIVATE_RUN_DIR --split selection score
```

The scorer currently emits ordinary Brier loss on exact-probability forecasts
and failure-penalized Brier loss on every case with resolved truth. It uses the
worse endpoint of the probability range when a forecast is partly unresolved.
Missing or invalid draw bundles score one. A draw-weight sum within an
absolute tolerance of 1e-9 is normalized before scoring. Only columns needed
for this event score are checked.

- `n_total` counts all locked cases, including unresolved truth.
- `n_eligible` counts cases with a physical truth label.
- `n_scored` counts the forecasts in the specific metric's mean.
- `n_failed` counts eligible cases with unresolved forecast weight or missing
  or invalid forecasts. Intervals are blank in the current implementation.

The formal release requires the remaining secondary scores, model-selection
checks, paired bootstrap, F5–F6, WP2's figures and forecasts, and independent
reproduction. The [English methods draft](../paper/methods-draft.md) has
placeholders for frozen evidence. Keep unreleased truth, private seeds and
raw AI logs outside the shared repository.
