"""Reproduce the physical checks from public, locked UPC inputs."""

import argparse
from collections import Counter, defaultdict
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import sys


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def run(root, predictions):
    sys.path.insert(0, str(root.resolve()))
    from physics import SolverConfig, load_case, solve
    from physics.aerodynamics import DEFAULT_VISCOSITY_PA_S, REGISTERED_CURVES

    release = root / "releases" / "upc2026-wp3-v1"
    case = load_case(release / "case.json")
    manifest = read_json(release / "release.json")
    candidates_path = release / "T2-candidates.json"
    if hashlib.sha256(candidates_path.read_bytes()).hexdigest() != manifest["artifact_sha256"]["T2-candidates.json"]:
        raise ValueError("Candidate artifact does not match release")
    candidates = read_json(candidates_path)
    fit = solve("B0", case, include_trace=True)
    launch = fit.trace[0]
    velocity = launch.vx_m_s, launch.vy_m_s, launch.vz_m_s
    reference_time = case.times[-1]

    def times(arrival):
        return {"arrival_s": arrival, "after_second_frame_s": arrival - reference_time}

    sweep = []
    for i in range(15, 46):
        cd = i / 100
        params = {"v0": velocity, "cd": cd}
        coarse = solve("M1", case, params)
        fine = solve("M1", case, params, SolverConfig(max_step_s=0.005))
        if coarse.event.event != "PLANE_GOAL" or fine.event.event != coarse.event.event:
            raise ValueError(f"Unexpected event at Cd={cd}")
        sweep.append({"cd": cd, **times(coarse.event.t_s),
                      "refinement_delta_s": abs(coarse.event.t_s - fine.event.t_s)})

    reynolds_factor = case.density * (2 * case.radius) / DEFAULT_VISCOSITY_PA_S
    curves = {}
    for curve in REGISTERED_CURVES:
        curve_path = root / "physics" / "curves" / f"{curve}.json"
        knots = read_json(curve_path)["reynolds"]
        shot = solve("M3", case, {"v0": velocity, "cd_anchor": 0.27, "curve": curve,
                                  "reference_speed_m_s": 30.0, "curve_policy": "error"},
                     include_trace=True)
        if shot.event.event == "NUMERICAL_FAILURE":
            raise ValueError(shot.event.reason)
        values = [point.reynolds for point in shot.trace]
        curves[curve] = {"knots": [knots[0], knots[-1]], "anchor_re": 30 * reynolds_factor,
                         "trace_re": [min(values), max(values)], "solver_domains": shot.curve_domains}

    sha = hashlib.sha256()
    with gzip.open(predictions, "rb") as compressed:
        for chunk in iter(lambda: compressed.read(1024 * 1024), b""):
            sha.update(chunk)
    lock = read_json(release / "selection-predictions" / "lock.json")
    if sha.hexdigest() != lock["predictions_sha256"]:
        raise ValueError("Selection predictions do not match their lock")
    cases = set()
    full_failures = set()
    other = Counter()
    beyond = defaultdict(list)
    with gzip.open(predictions, "rt", encoding="utf-8", newline="") as source:
        for row in csv.DictReader(source):
            if row["model_id"] != "M3":
                continue
            case_id = row["case_id"]
            cases.add(case_id)
            if row["event"] != "NUMERICAL_FAILURE" or float(row["weight"]) != 1.0:
                continue
            full_failures.add(case_id)
            reason = row["reason"]
            match = re.search(r"Reynolds number ([\d.e+-]+) is outside \[([\d.e+-]+), ([\d.e+-]+)\]", reason)
            if match is None:
                other[re.sub(r"proposal \d+", "proposal", reason)] += 1
                continue
            value, low, high = map(float, match.groups())
            side = "below" if value < low else "above"
            if value == high or low <= value <= high:
                raise ValueError("Rounded triggering Reynolds value is ambiguous")
            beyond[side, low, high].append(value)

    return {
        "release": manifest["run_id"],
        "selection_predictions_sha256": sha.hexdigest(),
        "fixed_velocity_m_s": velocity,
        "cd_0_27_initial_drag_m_s2": 0.5 * case.density * math.pi * case.radius**2 / case.mass
                                     * 0.27 * math.hypot(*velocity)**2,
        "timing": {
            "B0_deterministic": times(fit.event.t_s),
            "B1_deterministic": times(solve("B1", case).event.t_s),
            **{key.upper() + "_v1_candidate_median": times(candidates[key]["plane_intervals"]["t_s"][1])
               for key in ("m1", "m2")},
        },
        "M1_fixed_velocity_cd_sweep": sweep,
        "M3_fixed_velocity_shot": curves,
        "M3_all_selection_cases": len(cases),
        "M3_all_selection_full_failures": len(full_failures),
        "M3_full_failure_domain_triggers": [
            {"side": side, "knots": [low, high], "count": len(values),
             "first_recorded_re": [min(values), max(values)]}
            for (side, low, high), values in sorted(beyond.items())
        ],
        "M3_other_full_failures": dict(other),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="checkout containing the frozen release")
    parser.add_argument("predictions", type=Path, help="locked WP2 selection predictions.csv.gz")
    args = parser.parse_args()
    print(json.dumps(run(args.root, args.predictions), indent=2, allow_nan=False))
