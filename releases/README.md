# UPC2026 validation release

The frozen WP3 results are in [upc2026-wp3-v1](upc2026-wp3-v1/).
Start with [release.json](upc2026-wp3-v1/release.json) for revisions, model
settings, seeds, tolerances, input commitments and artifact hashes.

- [Selection results](upc2026-wp3-v1/selection-results.json) and
  [blind results](upc2026-wp3-v1/blind-results.json) record the selection gates
  and paired comparison. B0 is the retained event reference and B2 is a
  descriptive comparator. Both baselines undercovered the nominal joint regions.
- [T1](upc2026-wp3-v1/T1.csv), [T2](upc2026-wp3-v1/T2.csv) and
  [T3](upc2026-wp3-v1/paper/T3.csv) give the assumptions, supplied-kick
  summaries and blind scores. [Candidate sensitivities](upc2026-wp3-v1/T2-candidates.json)
  are labeled separately from the locked reference.
- [Figures manifest](upc2026-wp3-v1/figures/figures_manifest.csv) links F1–F6,
  captions and source evidence. [WP3 LaTeX](upc2026-wp3-v1/paper/sections/04-wp3-validation.tex)
  and [claims](upc2026-wp3-v1/paper/claims.csv) are the validation handoff for
  the shared team manuscript.

## Reproduction

Use WP1 `02b67b2a8e1e7fda974385c98b76f66b33dbfaa0` and WP2 source
`98d6970b05220c26e725a7550313acb703753efb` from WP2's verified bundle. The
WP2 handoff in [Issue #3](https://github.com/liweitang712/UPC2026/issues/3#issuecomment-6716642400)
records the bundle hash and result revision. Export `physics/` from the
WP1 revision into a separate directory on the Python import path. The
bridge runs WP2's original forecast logic, with bounded process scheduling
on Python 3.13.

```sh
python -B -m validation.wp2_bridge blind --wp2 WP2_CHECKOUT --wp1 WP1_EXPORT --selection-config WP2_CHECKOUT/inference/selection-v1/forecast.json --cases validation/frozen/v1/blind/cases.csv --freeze validation/frozen/v1/freeze.json --output BLIND_OUTPUT --models B0 B2 --seed 2028 --workers 12
python -B -m unittest discover -s validation/tests -v
python -B -m unittest discover -s figures/tests -v
```

Compare the prediction and point-status SHA-256 digests to
[the blind lock](upc2026-wp3-v1/blind-predictions/lock.json).
The WP3 scoring custody directory holds the true events, per-case strata,
generation seeds and raw locked blind draws. WP3 can rerun the scores and
figures after checking their locks:

```sh
python -B -m validation.assess_models --private PRIVATE_RUN_DIR --split blind --output NEW_BLIND_ASSESSMENT
python -B -m validation.conditional --private PRIVATE_RUN_DIR --output NEW_CONDITIONAL_OUTPUT
python -B -m figures.render_wp3 --private PRIVATE_RUN_DIR --output NEW_F5_F6
```

For the official shot, run the bridge's `public` subcommand with the same
WP1, WP2, selection config and B0/B2 pair. Use 4,000 draws and seed 2026 for
the primary run and 8,000 draws and seed 2027 for the repeat. Add
`--trace-model B0` to the primary run to reproduce F1. The commands
`python -B -m figures.render_public --help` and
`python -B -m validation.release_wp3 --help` describe final assembly.
