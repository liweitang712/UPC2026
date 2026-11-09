"""Score timing and ellipse coverage on the locked location holdout.

Run with the scoring custodian's files. Only aggregates leave custody.
"""

import argparse
from collections import Counter, defaultdict
from csv import DictReader
from itertools import groupby
import json
from math import sqrt
from pathlib import Path
from statistics import mean

import numpy as np

from figures.evidence import LEVELS, PLANE, summarize_draws
from inference.report import ellipse, quantile
from validation.generate_cases import read_json, sha256
from validation.location_v2 import RELEASE, rows
from validation.locked_score import check_hash


def audit(release, custody, draws):
    protocol_path = release / "protocol.json"
    protocol = read_json(protocol_path)
    freeze = read_json(release / "inputs/freeze.json")
    lock = read_json(release / "forecast-lock.json")
    run_id = protocol["run_id"]
    digest = sha256(protocol_path, text_source=True)
    if any(x["protocol_sha256"] != digest or x["run_id"] != run_id for x in (freeze, lock)):
        raise ValueError("Protocol differs from the frozen location locks")
    blind = freeze["splits"]["blind"]
    if lock["cases_sha256"] != blind["public_cases_sha256"]:
        raise ValueError("Forecast and input locks disagree")
    cases_path, truth_path = custody / "blind-cases.csv", custody / "blind-truth.csv"
    check_hash(cases_path, blind["scoring_cases_sha256"])
    check_hash(truth_path, blind["truth_sha256"])
    check_hash(draws, lock["predictions_sha256"])
    cases = {r["case_id"]: r["stratum"] for r in rows(cases_path)}
    truth = {r["case_id"]: r for r in rows(truth_path)}
    if cases.keys() != truth.keys() or len(cases) != blind["n_cases"]:
        raise ValueError("Frozen truth and case identifiers disagree")

    expected = {(c, m) for c in cases for m in lock["models"]}
    counts, errors = defaultdict(Counter), defaultdict(list)
    with draws.open(encoding="utf-8", newline="") as stream:
        groups = groupby(DictReader(stream), lambda r: (r["case_id"], r["model_id"]))
        for (case_id, model), group in groups:
            expected.remove((case_id, model))
            bundle = list(group)
            if any(r["scenario_id"] != protocol["scenario_id"] for r in bundle):
                raise ValueError("Unexpected forecast scenario")
            target = truth[case_id]
            if target["event"] not in PLANE:
                continue
            stratum = cases[case_id]
            keys = [(stratum, model)]
            if stratum in protocol["core_strata"]:
                keys.append(("core", model))
            point = np.array([float(target["y_m"]), float(target["z_m"])])
            grid_hits = summarize_draws(bundle, point, protocol["decision"]).hits
            for key in keys:
                counts[key]["truth_plane"] += 1
            if grid_hits is None:
                continue
            ellipse_hits, timing = diagnostics(bundle, target, point)
            for key in keys:
                count = counts[key]
                count["supported"] += 1
                for level, hit in zip(LEVELS, grid_hits, strict=True):
                    count[f"grid_{level:g}"] += hit
                if ellipse_hits is not None:
                    count["ellipse_supported"] += 1
                    for level, hit in zip(LEVELS, ellipse_hits, strict=True):
                        count[f"ellipse_{level:g}"] += hit
                if timing is not None:
                    error_ms, hit = timing
                    errors[key].append(error_ms)
                    count["time_hits_95"] += hit
    if expected:
        raise ValueError(f"Forecast is missing {len(expected)} case/model groups")

    output = []
    for row in rows(release / "T3.csv"):
        key = row["group"], row["model"]
        count = counts[key]
        for field, metric in (("truth_plane", "n_truth_plane"), ("supported", "n_supported"),
                              *((f"grid_{p:g}", f"n_hit_{p*100:.0f}") for p in LEVELS)):
            if count[field] != int(row[metric]):
                raise ValueError(f"Formal grid replay mismatch for {key}: {metric}")
        error = errors[key]
        output.append(dict(group=key[0], model=key[1], truth_plane=count["truth_plane"],
                           supported=count["supported"], timed=len(error),
                           time_bias_ms=mean(error) if error else None,
                           time_rmse_ms=sqrt(mean(e**2 for e in error)) if error else None,
                           time_hits_95=count["time_hits_95"],
                           ellipse_supported=count["ellipse_supported"],
                           ellipse_hits=[count[f"ellipse_{p:g}"] for p in LEVELS]))
    return dict(run_id=run_id, forecast_sha256=lock["predictions_sha256"],
                exploratory=True, ellipse_levels=LEVELS, results=output)


def diagnostics(bundle, target, point):
    plane = [r for r in bundle if r["event"] in PLANE and float(r["weight"]) > 0]
    weights = np.array([float(r["weight"]) for r in plane])
    weights /= weights.sum()
    locations = np.array([[float(r["y_m"]), float(r["z_m"])] for r in plane])
    shape = ellipse(locations, weights)
    ellipse_hits = None
    if shape is not None:
        center, axes, eigenvalues, thresholds = shape
        distance = np.sum(((point - center) @ axes)**2 / eigenvalues)
        ellipse_hits = (distance <= thresholds).tolist()

    timing = None
    if target["t_s"] and all(r["t_s"] for r in plane):
        times = np.array([float(r["t_s"]) for r in plane])
        measured = float(target["t_s"])
        if not np.isfinite(times).all() or not np.isfinite(measured):
            raise ValueError("Nonfinite crossing time")
        low, high = quantile(times, weights, [0.025, 0.975])
        timing = (1000 * float(weights @ times - measured), bool(low <= measured <= high))
    return ellipse_hits, timing


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, default=RELEASE)
    parser.add_argument("--private", type=Path, required=True)
    parser.add_argument("--draws", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.release, args.private, args.draws), indent=2))


if __name__ == "__main__":
    main()
