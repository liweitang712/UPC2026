"""Score conditional blind location forecasts and collect T3 denominators."""

import argparse
import csv
from collections import Counter, defaultdict
from itertools import groupby
from math import floor, fsum, isclose, isfinite, sqrt
from pathlib import Path
from statistics import mean

import numpy as np
from scipy.spatial.distance import cdist

from figures.evidence import DRAW_FIELDS, LEVELS, PLANE, STATUS_FIELDS, load_shots
from validation.generate_cases import HERE, PROTOCOL_PATH, read_json, write_csv
from validation.locked_score import PUBLIC, check_hash, selection_record, verify_inputs, verify_lock
from validation.score_entry import FAILURE, read_rows

EVENTS = ("PLANE_GOAL", "PLANE_WIDE", "GROUND_FIRST", "NO_REACH", FAILURE)


def joint_areas(points, weights, width):
    cells = defaultdict(list)
    for (y, z), weight in zip(points, weights):
        cells[floor(y / width), floor(z / width)].append(float(weight))
    ranked = sorted((fsum(parts) for parts in cells.values()), reverse=True)
    counts, accumulated = [], 0.0
    for mass, tied in groupby(ranked):
        size = sum(1 for _ in tied)
        accumulated += mass * size
        count = size + (counts[-1][1] if counts else 0)
        counts.append((accumulated, count))
    return tuple(next(count for mass, count in counts if mass >= level) * width ** 2 for level in LEVELS)


def conditional_scores(rows, target, decision):
    points = []
    weights = []
    times = []
    seen = set()
    total = 0.0
    for row in rows:
        try:
            weight = float(row["weight"])
            event = row["event"]
            draw_id = row["draw_id"]
            if (not draw_id.strip() or draw_id in seen or event not in EVENTS
                    or not isfinite(weight) or not 0 <= weight <= 1):
                return None
            seen.add(draw_id)
            total += weight
            if weight and event in PLANE:
                point = float(row["y_m"]), float(row["z_m"])
                time = float(row["t_s"]) if row["t_s"] else None
                if not all(map(isfinite, point)) or (time is not None and not isfinite(time)):
                    return None
                points.append(point)
                weights.append(weight)
                times.append(time)
        except ValueError:
            return None
    if not points or not isclose(total, 1, rel_tol=0, abs_tol=1e-9):
        return None
    weights = np.asarray(weights) / fsum(weights)
    ess = 1 / fsum(weights ** 2)
    minimum = decision["minimum_conditional_effective_draws"]
    if ess < minimum and not isclose(ess, minimum, rel_tol=1e-12):
        return None
    points = np.asarray(points)
    observed_distances = np.linalg.norm(points - [float(target["y_m"]), float(target["z_m"])], axis=1)
    forecast_distances = cdist(points, points)
    energy = float(weights @ observed_distances - (weights @ forecast_distances @ weights) / 2)
    time_error = None
    if target["t_s"] and all(time is not None for time in times):
        time_error = float(weights @ np.asarray(times) - float(target["t_s"]))
    areas = joint_areas(points, weights, decision["joint_region_grid_m"])
    return energy, time_error, *areas


def evaluate(cases_path, truth_path, predictions, point_status, models, protocol, run_id):
    shots = load_shots(cases_path, truth_path, predictions, point_status, models, protocol)
    truth = {row["case_id"]: row for row in read_rows(truth_path, ("case_id", "event", "t_s", "y_m", "z_m"))}
    cases = [row["case_id"] for row in read_rows(cases_path, ("case_id",))]
    shot_map = dict(zip(cases, shots, strict=True))
    decision = protocol["decision"]
    scores = {}
    fields = (*DRAW_FIELDS, "t_s")
    for key, group in groupby(read_rows(predictions, fields), lambda row: (row["case_id"], row["model_id"])):
        if truth[key[0]]["event"] in PLANE:
            result = conditional_scores(group, truth[key[0]], decision)
            if result is not None:
                scores[key] = result
    rng = np.random.default_rng(decision["bootstrap_seed"])
    rows, paired_rows = [], []
    for stratum in (*protocol["core_strata"], protocol["challenge_stratum"]):
        stratum_shots = {case_id: shot for case_id, shot in shot_map.items() if shot.stratum == stratum}
        counts = Counter(shot.event for shot in stratum_shots.values())
        for model in models:
            eligible = [shot for shot in stratum_shots.values() if shot.event != FAILURE]
            measured = [scores[key] for case_id in stratum_shots if (key := (case_id, model)) in scores]
            timing = [record[1] for record in measured if record[1] is not None]
            rows.append(dict(run_id=run_id, split="blind", stratum=stratum, model_id=model,
                             scenario_id=protocol["scenario_id"], n_total=len(stratum_shots),
                             n_eligible=len(eligible), **{f"truth_{event.lower()}": counts[event] for event in EVENTS},
                             n_truth_plane=sum(counts[event] for event in PLANE),
                             n_resolved_forecast=sum(shot.forecasts[model].resolved for shot in eligible),
                             n_technical_failure=sum(shot.forecasts[model].technical for shot in eligible),
                             n_point_abstained=sum(shot.point_status[model] == "abstained"
                                                   for shot in eligible if shot.forecasts[model].resolved),
                             n_energy=len(measured), energy_score_m=mean(r[0] for r in measured) if measured else None,
                             n_time=len(timing), arrival_rmse_s=sqrt(mean(t * t for t in timing)) if timing else None,
                             **{f"mean_region_area_{int(level * 100)}_m2": mean(r[i + 2] for r in measured) if measured else None
                                for i, level in enumerate(LEVELS)}))
        a, b = models
        differences = [scores[case_id, a][0] - scores[case_id, b][0] for case_id in stratum_shots
                       if (case_id, a) in scores and (case_id, b) in scores]
        n = len(differences)
        result = lo = hi = None
        if n >= decision["minimum_paired_truth_plane_cases"]:
            result = mean(differences)
            draws = rng.choice(differences, size=(decision["bootstrap_replicates"], n))
            lo, hi = np.quantile(draws.mean(axis=1), (0.025, 0.975))
        paired_rows.append(dict(run_id=run_id, split="blind", stratum=stratum, selected=a, comparator=b,
                                n_paired=n, selected_minus_comparator_m=result, interval_lo=lo, interval_hi=hi))
    return rows, paired_rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        private = args.private.resolve()
        if private.is_relative_to(HERE.parent):
            raise ValueError("Use the external WP3 custody directory")
        manifest = verify_inputs(PUBLIC, "blind")
        lock = private / "blind-predictions"
        metadata, forecast = verify_lock(lock, "blind", manifest)
        decision, models = selection_record(private, manifest)
        check_hash(decision, metadata["selection_decision_sha256"])
        if set(forecast["models"]) != set(models):
            raise ValueError("Wrong blind model pair")
        entry = manifest["splits"]["blind"]
        cases, truth = private / "blind-cases.csv", private / "blind-truth.csv"
        check_hash(cases, entry["scoring_cases_sha256"])
        check_hash(truth, entry["truth_sha256"])
        check_hash(lock / "point-status.csv", metadata["point_status_sha256"])
        rows, paired = evaluate(cases, truth, lock / "predictions.csv", lock / "point-status.csv", models,
                                read_json(PROTOCOL_PATH), manifest["run_id"])
        args.output.mkdir(parents=True, exist_ok=True)
        write_csv(args.output / "blind-conditional.csv", tuple(rows[0]), rows)
        write_csv(args.output / "blind-paired-conditional.csv", tuple(paired[0]), paired)
    except (OSError, ValueError, KeyError, csv.Error) as error:
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    main()
