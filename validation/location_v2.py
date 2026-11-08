"""Lock fresh forecasts and score joint crossing locations for the M2 study."""

import argparse
import csv
from itertools import groupby
from math import sqrt
from pathlib import Path
from statistics import mean

import numpy as np

from figures.evidence import PLANE, summarize_draws
from validation.assess_models import score_bundle
from validation.conditional import conditional_scores
from validation.generate_cases import read_json, sha256, write_csv
from validation.locked_score import check_hash
from validation.score_entry import FAILURE
from validation.wp2_bridge import point_status, write_json


RELEASE = Path("releases/upc2026-location-v2")
REGISTRY = Path("inference/selection-scenarios.json")


def lock_forecasts(custody, forecast, protocol, freeze):
    diagnostics = forecast / "diagnostics.json"
    metadata = read_json(diagnostics)
    design = protocol["location_analysis"]
    models = [design["working_model"], *design["comparators"]]
    expected = dict(models=models, seed=design["forecast_seed"], draw_budget=design["draws"],
                    cases_sha256=freeze["splits"]["blind"]["public_cases_sha256"],
                    scenario_sha256=sha256(REGISTRY))
    for field, value in expected.items():
        if metadata[field] != value:
            raise ValueError(f"Forecast {field} does not match frozen design")
    record = dict(run_id=protocol["run_id"], **expected, python=metadata["python"],
                  protocol_sha256=sha256(RELEASE / "protocol.json", text_source=True),
                  predictions_sha256=sha256(forecast / "predictions.csv"),
                  diagnostics_sha256=sha256(diagnostics),
                  inference_source_sha256=metadata["source_sha256"])
    write_json(custody / "predictions-lock.json", record)


def rows(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def case_scores(custody, forecast, models, protocol, freeze):
    lock = read_json(custody / "predictions-lock.json")
    check_hash(forecast / "predictions.csv", lock["predictions_sha256"])
    check_hash(forecast / "diagnostics.json", lock["diagnostics_sha256"])
    if lock["protocol_sha256"] != sha256(RELEASE / "protocol.json", text_source=True):
        raise ValueError("Protocol changed after forecast lock")
    entry = freeze["splits"]["blind"]
    cases_path = custody / "blind-cases.csv"
    truth_path = custody / "blind-truth.csv"
    check_hash(cases_path, entry["scoring_cases_sha256"])
    check_hash(truth_path, entry["truth_sha256"])
    cases = {row["case_id"]: row["stratum"] for row in rows(cases_path)}
    truth = {row["case_id"]: row for row in rows(truth_path)}
    if set(cases) != set(truth) or len(cases) != entry["n_cases"]:
        raise ValueError("Truth and case IDs differ")
    decision = protocol["decision"]
    missing = {(case, model) for case in cases for model in models}
    results = []
    with (forecast / "predictions.csv").open(encoding="utf-8", newline="") as stream:
        groups = groupby(csv.DictReader(stream), lambda row: (row["case_id"], row["model_id"]))
        for (case_id, model), group in groups:
            missing.remove((case_id, model))
            bundle = list(group)
            if any(r["scenario_id"] != protocol["scenario_id"] for r in bundle):
                raise ValueError("Unexpected forecast scenario")
            target = truth[case_id]
            event = target["event"]
            point = tuple(float(target[axis]) for axis in ("y_m", "z_m")) if event in PLANE else None
            region = summarize_draws(bundle, point, decision)
            location = conditional_scores(bundle, target, decision) if region.hits is not None else None
            if (location is None) != (region.hits is None):
                raise ValueError("Coverage and energy support disagree")
            event_score = score_bundle(bundle, target, decision) if event != FAILURE else None
            status = point_status(bundle, decision["minimum_conditional_effective_draws"])
            results.append(dict(case_id=case_id, model=model, stratum=cases[case_id],
                                event=event, region=region, location=location,
                                event_score=event_score, status=status))
    if missing:
        raise ValueError(f"Missing {len(missing)} forecasts")
    return results


def summarize(results, models, protocol):
    core = protocol["core_strata"]
    challenge = protocol["challenge_stratum"]
    groups = {name: [name] for name in (*core, challenge)}
    groups["core"] = core
    metrics, comparisons = [], []
    design = protocol["location_analysis"]
    rng = np.random.default_rng(design["bootstrap_seed"])
    for group, strata in groups.items():
        eligible = [r for r in results if r["stratum"] in strata and r["event"] != FAILURE]
        scores = {}
        for model in models:
            items = [r for r in eligible if r["model"] == model]
            supported = [r for r in items if r["location"] is not None]
            scores[model] = {r["case_id"]: r for r in supported}
            truth_plane = sum(r["event"] in PLANE for r in items)
            exact = [r["event_score"].losses[0] for r in items if not r["event_score"].failed]
            row = dict(run_id=protocol["run_id"], group=group, model=model,
                       n_eligible=len(items), n_truth_plane=truth_plane, n_supported=len(supported),
                       n_technical=sum(r["event_score"].failed for r in items),
                       n_entirely_invalid=sum(r["event_score"].entirely_invalid for r in items),
                       n_entry_support_abstained=sum(r["status"] == "abstained" for r in items),
                       n_entry_support_assessed=sum(r["status"] is not None for r in items),
                       entry_brier_failure_penalized=mean(r["event_score"].losses[0] for r in items),
                       n_entry_brier=len(exact), entry_brier=mean(exact) if exact else None,
                       energy_m=mean(r["location"][0] for r in supported) if supported else None,
                       mean_position_rmse_m=sqrt(mean(r["region"].squared_error for r in supported))
                       if supported else None)
            for i, level in enumerate((50, 80, 95)):
                row[f"n_hit_{level}"] = sum(r["region"].hits[i] for r in supported)
                row[f"area_{level}_m2"] = mean(r["location"][i + 2] for r in supported) if supported else None
            metrics.append(row)
        primary = models[0]
        for model in models[1:]:
            common = sorted(scores[primary].keys() & scores[model].keys())
            by_stratum = [
                [scores[primary][case]["location"][0] - scores[model][case]["location"][0]
                 for case in common if scores[primary][case]["stratum"] == stratum]
                for stratum in strata
            ]
            difference = lo = hi = None
            if min(map(len, by_stratum)) >= design["minimum_paired_per_stratum"]:
                difference = mean(map(mean, by_stratum))
                bootstrap = [rng.choice(d, size=(design["bootstrap_replicates"], len(d))).mean(axis=1)
                             for d in by_stratum]
                lo, hi = map(float, np.quantile(np.mean(bootstrap, axis=0), [.025, .975]))
            comparisons.append(dict(run_id=protocol["run_id"], group=group, model=primary,
                                    comparator=model, n_paired=len(common),
                                    energy_difference_m=difference, lo_m=lo, hi_m=hi))
    return metrics, comparisons


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=("lock", "score"))
    parser.add_argument("custody", type=Path)
    parser.add_argument("forecast", type=Path)
    args = parser.parse_args()
    protocol = read_json(RELEASE / "protocol.json")
    freeze = read_json(RELEASE / "inputs/freeze.json")
    if freeze["protocol_sha256"] != sha256(RELEASE / "protocol.json", text_source=True):
        raise ValueError("Public input freeze does not match the protocol")
    if args.step == "lock":
        lock_forecasts(args.custody, args.forecast, protocol, freeze)
        return
    design = protocol["location_analysis"]
    models = [design["working_model"], *design["comparators"]]
    result = case_scores(args.custody, args.forecast, models, protocol, freeze)
    metrics, paired = summarize(result, models, protocol)
    write_csv(RELEASE / "T3.csv", list(metrics[0]), metrics)
    write_csv(RELEASE / "paired-energy.csv", list(paired[0]), paired)


if __name__ == "__main__":
    main()
