# Historical Problem B materials

This folder snapshots the first B draft and its Python model, plots, and outputs. It is a reproducible baseline for development. Use the current repository specs for new work. In particular, the legacy prose uses a different side description, the 1 cm observation error is an assumption, and the historical synthetic evaluation filtered to airborne true crossings and sufficiently supported predictive crossings. These outputs are not the repository's new blind-test release.

Run `python reference/penalty/penalty_model.py --coords 1.50 0.45 0.44 2.96 0.86 0.74 --sigma 0.01` from the repository root for the historical supplied-case prediction on standard output. For the full historical synthetic run, copy the script to a scratch directory and run it without arguments there. The draft's figure paths are relative to this historical snapshot.
