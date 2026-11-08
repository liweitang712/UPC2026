# Locked location holdout timing and ellipse diagnostics

These aggregate diagnostics use the same cases and locked predictions as the
[location study](../upc2026-location-v2/README.md). Timing error is the posterior
mean crossing time minus the synthetic truth. The denominator is the number
of true plane crossings with at least 100 effective weighted plane draws and
complete timing values. The interval is the weighted equal-tail 95% interval.
Ellipse cutoffs are weighted quantiles of the squared Mahalanobis distances
of the crossing draws. The three ellipse levels are 50%, 80%, and 95%.

Run from the repository root in the custody environment.

    python -B -m validation.location_timing_audit --private CUSTODY --draws LOCKED_FORECAST/predictions.csv

The run verified the locked input and forecast digests and reproduced the
formal T3 support and grid coverage at all three levels before releasing
the supplement. The replay reproduced the previously reported 95% ellipse
counts for all three models in the core and challenge sets. This supplement
retains the original scoring protocol. Only aggregated diagnostics appear
in the release. The hashes in release.json use LF for published text.
