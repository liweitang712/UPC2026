"""Rescore blind crossing-region coverage on the frozen and finer grids.

Run from the WP3 checkout with access to the external truth custody directory.
The output is an exploratory aggregate, separate from the frozen release.
"""

import argparse
from collections import Counter
from hashlib import file_digest
import json
from pathlib import Path
import sys


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def require_hash(path, expected):
    with path.open("rb") as stream:
        if file_digest(stream, "sha256").hexdigest() != expected:
            raise ValueError(f"SHA-256 differs from frozen input: {path.name}")


def aggregate(shots, models, strata, plane):
    counts = Counter()
    for shot in shots:
        if shot.event not in plane:
            continue
        group = "core" if shot.stratum in strata else "challenge"
        for model in models:
            hits = shot.forecasts[model].hits
            counts[group, model, "truth_plane"] += 1
            if hits is not None:
                counts[group, model, "supported"] += 1
                counts[group, model, "covered"] += hits[2]
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--release", required=True, type=Path)
    parser.add_argument("--private", required=True, type=Path)
    parser.add_argument("--draws", required=True, type=Path)
    parser.add_argument("--point-status", required=True, type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.repository.resolve()))
    from figures.evidence import PLANE, load_shots

    root = args.release.resolve()
    manifest = read(root / "release.json")
    for name in ("input-freeze.json", "protocol.json", "blind-predictions/lock.json", "blind-results.json"):
        require_hash(root / name, manifest["artifact_sha256"][name])
    lock = read(root / "blind-predictions/lock.json")
    freeze = read(root / "input-freeze.json")["splits"]["blind"]
    protocol = read(root / "protocol.json")
    models = (manifest["recommended_model"], manifest["comparator_model"])
    cases = args.private / "blind-cases.csv"
    truth = args.private / "blind-truth.csv"
    require_hash(cases, freeze["scoring_cases_sha256"])
    require_hash(truth, freeze["truth_sha256"])
    require_hash(args.draws, lock["predictions_sha256"])
    require_hash(args.point_status, lock["point_status_sha256"])
    original = read(root / "blind-results.json")
    result = []
    for width in (protocol["decision"]["joint_region_grid_m"], 0.02):
        decision = {**protocol["decision"], "joint_region_grid_m": width}
        shots = load_shots(cases, truth, args.draws, args.point_status, models,
                           {**protocol, "decision": decision})
        counts = aggregate(shots, models, protocol["core_strata"], PLANE)
        for model in models:
            for group in ("core", "challenge"):
                truth_plane, support, covered = (counts[group, model, k]
                                                 for k in ("truth_plane", "supported", "covered"))
                result.append(dict(grid_m=width, model=model, group=group, truth_plane=truth_plane,
                                   supported=support, covered=covered, coverage=covered / support if support else None))
                if group == "core" and width == protocol["decision"]["joint_region_grid_m"]:
                    core = original["models"][model]["core"]
                    if (truth_plane, support, covered) != tuple(
                            core[k] for k in ("n_truth_plane", "n_region_supported", "n_region_hits")):
                        raise ValueError(f"Frozen-grid replay differs for {model}")
    print(json.dumps(dict(run_id=manifest["run_id"], exploratory=True, nominal_level=0.95,
                          results=result), indent=2))


if __name__ == "__main__":
    main()
