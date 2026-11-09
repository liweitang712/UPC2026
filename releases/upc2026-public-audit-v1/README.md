# Supplied-kick supplemental audit

This snapshot supplements [the locked location study](../upc2026-location-v2/README.md).
It preserves the existing model choice and holdout scores. The nominal replay
checks entry, arrival and the time quantiles against the locked T2. Misses
are split using the strict center-entry geometry. A center exactly on a post
or the bar belongs to the corresponding miss category.

The two lower-drag fits change only the parent-normal drag-prior center to
0.18. They refit the launch velocity. Launch speed and angles are from the
two-frame gravity-only fit. The curve speed limit uses nominal air properties.

Run from the repository root with the location study's Python dependencies.

    python -B -m validation.public_kick_audit 0.27 718020 64000 nominal.json
    python -B -m validation.public_kick_audit 0.18 718020 64000 cd018.json
    python -B -m validation.public_kick_audit 0.18 718019 32000 cd018-repeat.json

| Frozen file | SHA-256 |
| --- | --- |
| nominal.json | 09f24475437ab5d3d25f623e2e6485ddf0003ba7566292be5f2c88d3d751afa0 |
| cd018.json | e4b5d0f19418e95f03e8485ab1593695b78fd9f901e06c75ac8bbfe9696c6ed1 |
| cd018-repeat.json | ce5abce08118dfbb0a99f6fe7b2dfff7514e3192df5d25bbced2c14e8f3b7302 |

The formal per-stratum coverage counts come from the location-study T3.
To report timing and continuous-region diagnostics on those same forecasts,
the custodian can run the following command. It checks the sealed inputs and
replays the formal grid counts before returning the exploratory aggregates.
Time bias and RMSE use the conditional predictive mean. Interval coverage
uses the 2.5th and 97.5th percentiles among weighted plane draws.

    python -B -m validation.location_timing_audit --private CUSTODY --draws LOCKED_FORECAST/predictions.csv > timing-ellipse.json
