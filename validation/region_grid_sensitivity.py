"""Rescore blind crossing-region coverage on the frozen and finer grids.

Run from the WP3 checkout with access to the external truth custody directory.
The output is an exploratory aggregate, separate from the frozen release.
"""

import argparse
from collections import Counter
import csv
from hashlib import file_digest, sha256
from itertools import groupby
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


def location_grid_replay(root, custody, draws):
    from figures.evidence import PLANE, summarize_draws

    protocol_path = root / "protocol.json"
    protocol = read(protocol_path)
    freeze = read(root / "inputs/freeze.json")
    lock = read(root / "forecast-lock.json")
    run_id = protocol["run_id"]
    digest = sha256(protocol_path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    if any(record["run_id"] != run_id or record["protocol_sha256"] != digest
           for record in (freeze, lock)):
        raise ValueError("Location protocol does not match the public locks")
    entry = freeze["splits"]["blind"]
    if lock["cases_sha256"] != entry["public_cases_sha256"]:
        raise ValueError("Location forecast and input locks disagree")
    paths = (custody / "blind-cases.csv", custody / "blind-truth.csv", draws)
    for path, expected in zip(paths, (entry["scoring_cases_sha256"], entry["truth_sha256"],
                                      lock["predictions_sha256"])):
        require_hash(path, expected)

    def rows(path):
        with path.open(encoding="utf-8", newline="") as stream:
            yield from csv.DictReader(stream)

    cases = {row["case_id"]: row["stratum"] for row in rows(paths[0])}
    truth = {row["case_id"]: row for row in rows(paths[1])}
    if cases.keys() != truth.keys() or len(cases) != entry["n_cases"]:
        raise ValueError("Location case IDs disagree")
    models = lock["models"]
    missing = {(case_id, model) for case_id in cases for model in models}
    frozen_width = protocol["decision"]["joint_region_grid_m"]
    decisions = {width: {**protocol["decision"], "joint_region_grid_m": width}
                 for width in (frozen_width, 0.02)}
    totals = Counter()
    for (case_id, model), group in groupby(rows(draws), lambda row: (row["case_id"], row["model_id"])):
        missing.remove((case_id, model))
        label = truth[case_id]
        if label["event"] not in PLANE:
            continue
        category = "core" if cases[case_id] in protocol["core_strata"] else "challenge"
        bundle = list(group)
        point = float(label["y_m"]), float(label["z_m"])
        for width, decision in decisions.items():
            hit = summarize_draws(bundle, point, decision).hits
            key = width, category, model
            totals[*key, "truth_plane"] += 1
            if hit is not None:
                totals[*key, "supported"] += 1
                totals[*key, "covered"] += hit[2]
    if missing:
        raise ValueError("Location forecast is incomplete")
    original = {(row["group"], row["model"]): row for row in rows(root / "T3.csv")}
    results = []
    for width in decisions:
        for category in ("core", "challenge"):
            for model in models:
                key = width, category, model
                observed = tuple(totals[*key, field] for field in ("truth_plane", "supported", "covered"))
                expected = original[category, model]
                if width == frozen_width and observed != tuple(
                        int(expected[field]) for field in ("n_truth_plane", "n_supported", "n_hit_95")):
                    raise ValueError(f"Frozen location replay differs for {category}/{model}")
                n_plane, n_supported, n_covered = observed
                results.append(dict(grid_m=width, model=model, group=category,
                                    truth_plane=n_plane, supported=n_supported, covered=n_covered,
                                    coverage=n_covered / n_supported if n_supported else None))
    return dict(run_id=run_id, exploratory=True, nominal_level=0.95, results=results)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--release", required=True, type=Path)
    parser.add_argument("--private", required=True, type=Path)
    parser.add_argument("--draws", required=True, type=Path)
    parser.add_argument("--point-status", type=Path, help="required for the v1 lock")
    args = parser.parse_args()
    sys.path.insert(0, str(args.repository.resolve()))
    from figures.evidence import PLANE, load_shots

    root = args.release.resolve()
    if (root / "forecast-lock.json").is_file():
        print(json.dumps(location_grid_replay(root, args.private, args.draws), indent=2))
        return
    if args.point_status is None:
        parser.error("--point-status is required for the v1 lock")
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
