# Independent blind reproduction

The independent run uses WP2 source `98d6970b05220c26e725a7550313acb703753efb`,
WP1 `02b67b2a8e1e7fda974385c98b76f66b33dbfaa0`, and the public input and
bridge from WP3 release `f0f6b618d16be223f38724826b898d1a85f4653f`.
The selected pair is B0/B2, with 1024 draws per case and inference seed 2028.
All 520 public blind cases were recomputed.

Both independent output hashes exactly match the published blind lock.

| Artifact | SHA-256 |
|---|---|
| cases.csv | 17cef584731195978af3b66399a3db111fca16530e3cf00d8f0f76b927f14bf7 |
| predictions.csv | 114efba3736e518e20b8317a07f9670a22fa27952e03c221b11fc97f6e3f80a2 |
| point-status.csv | 852e2016545238c85e9c8a78ce9dffdaf99169b98ac6e46647aa9cca481f0df1 |

Use the reproduction command in the frozen `releases/README.md`.
Independent settings and point status are included under `blind-independent/`.
Raw predictions remain available locally and can be regenerated.

## Scope of acceptance

This check establishes exact reproduction of the published forecast pair.
WP3 reports substantial undercoverage of both nominal joint regions. The M2
figures under `wp2-public/` are exploratory candidate results. Final manuscript
numbers and figures must use release `upc2026-wp3-v1`.

The aerodynamic sampler terminates a case/model forecast if a likelihood
evaluation fails. In selection this produced 81 M3 groups with a curve domain
error, in addition to five unsupported groups. These failures were preserved
in the frozen bundle and contributed to WP3 scoring. Review this behavior
before freezing any new forecast version.

Further WP2 acceptance work includes simulation-based calibration and
prior-to-posterior contraction and profile diagnostics. Shared LaTeX chapters
and the full AI transcript also require final team integration.
