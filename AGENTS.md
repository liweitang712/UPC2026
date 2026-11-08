# Agent instructions for UPC 2026 Problem B

1. Read [HANDOFF.md](HANDOFF.md), [spec/case.json](spec/case.json), [spec/schema.md](spec/schema.md), and [spec/models.csv](spec/models.csv) before editing. Read the role's specialist spec next.
2. Claim a work package with a branch and a repository issue or PR comment. State owner, base commit, expected files, and dependencies. Work on that role's branch and paths. Ask the human integrator to resolve changes to the common contract.
3. Use SI units, stable IDs, explicit conditioning and denominators, and the right-handed coordinate frame in the schema. Keep `reference/` read-only. Do not use historical numbers as new results.
4. Validation owns the held-out truth. Inference only receives permitted inputs before scoring. Do not commit unreleased blind truth, credentials, or private chat exports to the shared branch.
5. Handoff in an issue or PR with commit, changed files, exact reproduction command, checks, open questions, and next owner. Put data and code in Git. Messages should point to the relevant files and run ID.
6. Figures, manuscript, and abstract use the integrator's same frozen release. Any new configuration or data release requires recomputing affected claims and plots. Never describe a simulated or historical case as a new real-world result.
7. For the team's eventual AI disclosure, save original prompts and full outputs used in the entry in a team-controlled log. Make team members able to verify, explain and defend their portions.
8. For manuscript work, use [PAPER_WRITING.md](PAPER_WRITING.md) for the shared LaTeX entry, section ownership, and work-package prompts. Use the shared project for the manuscript and this repository for reproducible evidence and handoffs.
