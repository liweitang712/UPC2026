# M2 location study

This release supports the current Team 540 manuscript. M2 is the working
location forecast. The supplied frames suggest forward deceleration and a
small change in horizontal direction. A bounded, zero-centred transverse
force allows both straight and curved extrapolations. M1 tests the effect of
removing that term and B0 is the gravity-only reference.

- [T2](T2.json) reports the supplied kick. The 0.10 m smoothed entry peak
  is reported together with the repeat shift and the instability at 0.05 m.
  [Sensitivity refits](T2-sensitivity.json) come from the integrated WP2 QA.
- [T3](T3.csv) gives supported and total crossing counts, region coverage and
  size, location scores, and secondary event scores. [Paired differences](paired-energy.csv)
  report M2 minus each comparator on their common supported true crossings.
  Core differences average the six stratum means equally. The challenge set
  is separate. Blank intervals indicate insufficient overlap.
- [Protocol](protocol.json), [input freeze](inputs/freeze.json) and
  [forecast lock](forecast-lock.json) identify the evidence. The
  inherited event decision fields do not rank models in this study.
- [Figures](figures/) include the M2 trajectory fan and crossing density,
  the published WP2 identifiability and sensitivity panels, and new holdout
  event and location panels.

The 260 fresh synthetic shots use the integrated generator, with 40 in each
core stratum and 20 challenge shots. The matched force family includes
transverse forces, which favours M2 structurally. The stress scenarios probe
departures from that family. This comparison measures performance on the
synthetic distribution and does not establish calibration on field data.

Run from the repository root with Python, NumPy, SciPy and Matplotlib.

```sh
python -B -m inference.forecast releases/upc2026-location-v2/inputs/blind/cases.csv inference/selection-scenarios.json NEW_FORECAST --models M2 M1 B0 --draws 2048 --seed 812026 --workers 12
python -B -m figures.render_location_v2 public
python -B -m figures.render_location_v2 validation
```

Compare the new prediction digest with `forecast-lock.json`. For rescoring,
the custodian uses the frozen cases with strata and frozen truth in
`CUSTODY`. Run the lock step before scoring a new prediction directory.

```sh
python -B -m validation.location_v2 lock CUSTODY NEW_FORECAST
python -B -m validation.location_v2 score CUSTODY NEW_FORECAST
```

Source base is integrated main `bfe0b3c35c82ecdf82a9a8623bfb345b01bc569b`.
The original [event-first release](../upc2026-wp3-v1/release.json) documents
the historical B0/B2 comparison.
