"""Evaluate the frozen selection or blind predictions one bundle at a time."""

import argparse
import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from itertools import groupby
from math import fsum, isclose, isfinite
from pathlib import Path
from random import Random
from statistics import mean, stdev

from figures.evidence import PLANE, summarize_draws, wilson
from validation.generate_cases import HERE, PROTOCOL_PATH, read_json, write_csv
from validation.locked_score import PUBLIC, check_hash, selection_record, verify_inputs, verify_lock
from validation.score_entry import FAILURE, METRIC_FIELDS, PHYSICAL_EVENTS, by_case, read_rows


TARGETS = ("entry", "arrival", "clearance", "ground_first")
EVENTS = PHYSICAL_EVENTS | {FAILURE}
PRIMARY = "entry_brier_failure_penalized"
DRAW_FIELDS = (
    "case_id", "model_id", "scenario_id", "draw_id", "weight", "event", "y_m", "z_m", "clearance_goal",
)


@dataclass(frozen=True)
class ForecastScore:
    losses: tuple[float, ...] = (1.0,) * len(TARGETS)
    failed: bool = True
    entirely_invalid: bool = True
    coverage_95: bool | None = None


def indicators(row):
    event = row["event"]
    clearance = row["clearance_goal"]
    if (event not in EVENTS or (event in PLANE and clearance not in ("0", "1"))
            or (event not in PLANE and clearance) or (clearance == "1" and event != "PLANE_GOAL")):
        raise ValueError("Invalid event or clearance flag")
    return event == "PLANE_GOAL", event in PLANE, clearance == "1", event == "GROUND_FIRST"


def score_bundle(draws, truth, decision):
    weights = [[] for _ in TARGETS]
    all_weights, failed_weights = [], []
    seen = set()
    try:
        for row in draws:
            outcomes = indicators(row)
            draw_id = row["draw_id"]
            w = float(row["weight"])
            if not draw_id.strip() or draw_id in seen or not isfinite(w) or not 0 <= w <= 1:
                return ForecastScore()
            seen.add(draw_id)
            all_weights.append(w)
            if row["event"] == FAILURE:
                failed_weights.append(w)
            for target_weights, outcome in zip(weights, outcomes):
                if outcome:
                    target_weights.append(w)
    except ValueError:
        return ForecastScore()

    total = fsum(all_weights)
    if not isclose(total, 1, rel_tol=0, abs_tol=1e-9):
        return ForecastScore()
    true_point = (float(truth["y_m"]), float(truth["z_m"])) if truth["event"] in PLANE else None
    summary = summarize_draws(draws, true_point, decision)
    if not summary.resolved:
        return ForecastScore()
    unresolved = fsum(failed_weights) / total
    losses = []
    for target_weights, outcome in zip(weights, indicators(truth)):
        known = fsum(target_weights) / total
        lo, hi = known, min(1.0, known + unresolved)
        losses.append(max((lo - outcome) ** 2, (hi - outcome) ** 2))
    return ForecastScore(tuple(losses), bool(unresolved), False, summary.hits[-1] if summary.hits else None)


def load_scores(cases_path, truth_path, draws_path, protocol, split, models):
    cases = by_case(read_rows(cases_path, ("case_id", "split", "stratum", "scenario_id")), "cases")
    truth = by_case(read_rows(truth_path, ("case_id", "event", "y_m", "z_m", "clearance_goal")), "truth")
    if not cases or cases.keys() != truth.keys() or "upc2026-b" in cases:
        raise ValueError("Scoring cases must match truth exactly and exclude the supplied kick")
    strata = (*protocol["core_strata"], protocol["challenge_stratum"])
    for case_id, row in cases.items():
        if row["split"] != split or row["stratum"] not in strata or row["scenario_id"] != protocol["scenario_id"]:
            raise ValueError(f"Unexpected split, stratum or scenario for {case_id!r}")
        label = truth[case_id]
        indicators(label)
        if label["event"] in PLANE and not all(isfinite(float(label[axis])) for axis in ("y_m", "z_m")):
            raise ValueError(f"Invalid truth crossing for {case_id!r}")

    def bundle_key(row):
        case_id, model = row["case_id"], row["model_id"]
        if case_id not in cases or model not in models or row["scenario_id"] != cases[case_id]["scenario_id"]:
            raise ValueError(f"Unexpected prediction key for {case_id!r}, {model!r}")
        return case_id, model

    scores = {}
    for key, rows in groupby(read_rows(draws_path, DRAW_FIELDS), bundle_key):
        if key in scores:
            raise ValueError(f"Draw rows must be contiguous for {key!r}")
        scores[key] = score_bundle(list(rows), truth[key[0]], protocol["decision"])
    groups = {stratum: [] for stratum in strata}
    for case_id, row in cases.items():
        groups[row["stratum"]].append((case_id, truth[case_id]["event"]))
    return groups, scores


def model_metrics(group, scores, model):
    eligible = [(case_id, event) for case_id, event in group if event != FAILURE]
    predictions = [scores.get((case_id, model), ForecastScore()) for case_id, _ in eligible]
    exact = [score for score in predictions if not score.failed]
    supported = [score.coverage_95 for score in predictions if score.coverage_95 is not None]
    metrics = {
        "n_total": len(group), "n_eligible": len(eligible),
        "n_truth_plane": sum(event in PLANE for _, event in eligible),
        "n_failed": sum(score.failed for score in predictions),
        "n_entirely_invalid": sum(score.entirely_invalid for score in predictions),
        "n_region_failed": sum(score.failed for score, (_, event) in zip(predictions, eligible) if event in PLANE),
        "n_region_supported": len(supported), "n_region_hits": sum(supported),
        "coverage_95": mean(supported) if supported else None,
        "truth_outcomes": {event: sum(actual == event for _, actual in group) for event in sorted(EVENTS)},
    }
    for index, target in enumerate(TARGETS):
        metrics[f"{target}_brier_failure_penalized"] = mean(score.losses[index] for score in predictions) if predictions else None
        metrics[f"{target}_brier"] = mean(score.losses[index] for score in exact) if exact else None
        metrics[f"{target}_brier_n"] = len(exact)
    return metrics


def equal_core(rows):
    """Equal-weight stratum loss, with pooled denominators for failure and coverage."""
    totals = {key: sum(row[key] for row in rows) for key in rows[0] if key.startswith("n_")}
    totals["truth_outcomes"] = {event: sum(row["truth_outcomes"][event] for row in rows) for event in sorted(EVENTS)}
    n_region = totals["n_region_supported"]
    totals["coverage_95"] = totals["n_region_hits"] / n_region if n_region else None
    for key in rows[0]:
        if "_brier" not in key:
            continue
        values = [row[key] for row in rows]
        totals[key] = sum(values) if key.endswith("_n") else mean(values) if None not in values else None
    return totals


def interval(samples, confidence):
    ordered = sorted(samples)

    def at(p):
        index = (len(ordered) - 1) * p
        lower = int(index)
        upper = min(lower + 1, len(ordered) - 1)
        return ordered[lower] + (index - lower) * (ordered[upper] - ordered[lower])

    return at((1 - confidence) / 2), at((1 + confidence) / 2)


def paired_comparison(candidate, comparator, groups, scores, core, decision):
    def differences(group):
        return [scores.get((key, comparator), ForecastScore()).losses[0]
                - scores.get((key, candidate), ForecastScore()).losses[0]
                for key, event in group if event != FAILURE]

    rng = Random(decision["bootstrap_seed"])
    per_stratum = {stratum: differences(group) for stratum, group in groups.items()}
    active = {stratum: values for stratum, values in per_stratum.items() if values}
    replicate_count = decision["bootstrap_replicates"]
    core_supported = all(stratum in active for stratum in core)
    replicates = {stratum: [] for stratum in active}
    core_replicates = []
    for _ in range(replicate_count):
        means = {stratum: mean(rng.choices(values, k=len(values))) for stratum, values in active.items()}
        for stratum, value in means.items():
            replicates[stratum].append(value)
        if core_supported:
            core_replicates.append(mean(means[stratum] for stratum in core))
    confidence = decision["blind_ci_level"]
    strata = {}
    for stratum, values in per_stratum.items():
        lo, hi = interval(replicates[stratum], confidence) if values else (None, None)
        strata[stratum] = {"n_paired": len(values), "gain": mean(values) if values else None,
                           "interval_lo": lo, "interval_hi": hi}
    lo, hi = interval(core_replicates, confidence) if core_replicates else (None, None)
    return {
        "candidate": candidate, "comparator": comparator,
        "gain": mean(strata[stratum]["gain"] for stratum in core) if core_supported else None,
        "bootstrap_se": stdev(core_replicates) if len(core_replicates) > 1 else None,
        "interval_lo": lo, "interval_hi": hi, "stratum_gains": strata,
    }


def technical_eligible(summary, decision):
    return bool(summary["n_eligible"] and summary["n_entirely_invalid"] / summary["n_eligible"]
                <= decision["maximum_entirely_invalid_fraction"])


def comparison_checks(comparison, summaries, protocol, split):
    core, decision = protocol["core_strata"], protocol["decision"]
    candidate, comparator = comparison["candidate"], comparison["comparator"]
    primary = summaries[candidate]["core"]
    coverage = primary["coverage_95"]
    gain, error = comparison["gain"], comparison["bootstrap_se"]
    checks = {
        "minimum_core_counts": all(comparison["stratum_gains"][stratum]["n_paired"]
                                   >= protocol["minimum_counts"][split] for stratum in core),
        "practical_gain": gain is not None and gain >= decision["minimum_brier_gain"],
        "candidate_failure": technical_eligible(primary, decision),
        "core_degradation": all(
            comparison["stratum_gains"][stratum]["gain"] is not None
            and comparison["stratum_gains"][stratum]["gain"] >= -decision["maximum_core_brier_degradation"]
            for stratum in core
        ),
    }
    if split == "selection":
        checks["one_paired_standard_error"] = (gain is not None and error is not None
                                              and gain > decision["selection_bootstrap_se_multiplier"] * error)
        checks["coverage_95"] = (coverage is not None and coverage >= decision["coverage_level"]
                                 - decision["maximum_undercoverage"])
    else:
        checks["positive_paired_interval"] = (comparison["interval_lo"] is not None and comparison["interval_lo"] > 0)
        checks["comparator_failure"] = technical_eligible(summaries[comparator]["core"], decision)
    return checks


def assess(groups, scores, models, protocol, split, blind_pair=None):
    core, decision = protocol["core_strata"], protocol["decision"]
    summaries = {}
    for model in models:
        by_stratum = {stratum: model_metrics(group, scores, model) for stratum, group in groups.items()}
        summaries[model] = {"core": equal_core([by_stratum[stratum] for stratum in core]), "strata": by_stratum}

    def ranking_key(model):
        loss = summaries[model]["core"][PRIMARY]
        return (float("inf") if loss is None else loss, protocol["models"].index(model))

    ranking = sorted(models, key=ranking_key)
    comparisons = []

    def compare(candidate, comparator):
        row = paired_comparison(candidate, comparator, groups, scores, core, decision)
        row["checks"] = comparison_checks(row, summaries, protocol, split)
        row["passes"] = all(row["checks"].values())
        comparisons.append(row)
        return row["passes"]

    if split == "selection":
        baselines = [model for model in ranking if model in ("B0", "B1", "B2")
                     and technical_eligible(summaries[model]["core"], decision)]
        if len(baselines) < 2:
            raise ValueError("At least two technically eligible baselines are required to lock a blind pair")
        selected, comparator = baselines[:2]
        for model in ("M1", "M2", "M3"):
            if compare(model, selected):
                comparator, selected = selected, model
        upgrade = selected not in ("B0", "B1", "B2")
        if upgrade:
            rationale = f"{selected} passed every selection gate against {comparator}, the strongest accepted simpler model."
        else:
            rationale = (f"No richer model passed every gate. Retain {selected}, the strongest technically eligible baseline. "
                         f"Use the runner-up baseline {comparator} as the descriptive blind comparator.")
    else:
        selected, comparator = blind_pair
        passed = compare(selected, comparator)
        upgrade = selected not in ("B0", "B1", "B2")
        confirmed = passed and upgrade
        rationale = ("The locked richer candidate met the blind confirmation gates." if confirmed else
                     "The locked baseline pair is reported descriptively." if not upgrade else
                     "The locked richer candidate did not meet every blind confirmation gate. Retain the simpler comparator.")

    return {
        "split": split, "models": summaries, "ranking": ranking, "comparisons": comparisons,
        "selected_model": selected, "comparator_model": comparator, "rationale": rationale,
        "recommended_model": comparator if split == "blind" and upgrade and not confirmed else selected,
        "upgrade_adopted": upgrade, "confirmed": confirmed if split == "blind" else None,
        "bootstrap": {"replicates": decision["bootstrap_replicates"], "seed": decision["bootstrap_seed"],
                      "confidence": decision["blind_ci_level"], "unit": "case within stratum",
                      "gain_sign": "comparator minus candidate"},
        "denominators": {"core_loss": "equal stratum means over all physically resolved truths",
                         "entirely_invalid_fraction": "pooled core cases with physically resolved truths",
                         "coverage_95": "pooled core true plane crossings with conditional ESS support",
                         "challenge": "reported separately from the core average and gates"},
    }


def metrics_rows(report):
    common = {key: report[key] for key in ("run_id", "split", "scenario_id")}
    for model, summaries in report["models"].items():
        for stratum, summary in {**summaries["strata"], "core_equal": summaries["core"]}.items():
            base = dict(common, stratum=stratum, model_id=model, n_total=summary["n_total"],
                        n_failed=summary["n_failed"], unit="1", interval_lo=None, interval_hi=None)
            for target in TARGETS:
                metric = f"{target}_brier_failure_penalized"
                yield dict(base, metric=metric, value=summary[metric], n_eligible=summary["n_eligible"],
                           n_scored=summary["n_eligible"])
                metric = f"{target}_brier"
                yield dict(base, metric=metric, value=summary[metric], n_eligible=summary["n_eligible"],
                           n_scored=summary[f"{metric}_n"])
            lo, hi = wilson(summary["n_region_hits"], summary["n_region_supported"])
            yield dict(base, metric="coverage_95", value=summary["coverage_95"], n_eligible=summary["n_truth_plane"],
                       n_scored=summary["n_region_supported"], n_failed=summary["n_region_failed"],
                       interval_lo=lo, interval_hi=hi)
            eligible = summary["n_eligible"]
            yield dict(base, metric="entirely_invalid_fraction", n_eligible=eligible, n_scored=eligible,
                       value=summary["n_entirely_invalid"] / eligible if eligible else None)


def locked_assessment(private, public, split):
    manifest = verify_inputs(public, split)
    lock = private / f"{split}-predictions"
    metadata, forecast = verify_lock(lock, split, manifest)
    protocol = read_json(PROTOCOL_PATH)
    pair = None
    if split == "blind":
        decision_path, pair = selection_record(private, manifest)
        check_hash(decision_path, metadata["selection_decision_sha256"])
    models = protocol["models"] if pair is None else pair
    if set(models) != set(forecast["models"]):
        raise ValueError("Locked model settings do not match the evaluated candidates")
    entry = manifest["splits"][split]
    cases, truth = private / f"{split}-cases.csv", private / f"{split}-truth.csv"
    check_hash(cases, entry["scoring_cases_sha256"])
    check_hash(truth, entry["truth_sha256"])
    groups, scores = load_scores(cases, truth, lock / "predictions.csv", protocol, split, models)
    report = assess(groups, scores, models, protocol, split, pair)
    report.update(run_id=manifest["run_id"], scenario_id=protocol["scenario_id"],
                  protocol_sha256=manifest["protocol_sha256"], cases_sha256=entry["public_cases_sha256"],
                  scoring_cases_sha256=entry["scoring_cases_sha256"], truth_sha256=entry["truth_sha256"],
                  predictions_sha256=metadata["predictions_sha256"], forecast_sha256=metadata["forecast_sha256"],
                  source_commit=forecast["source_commit"])
    return report


def write_json_exclusive(path, record):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(record, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private", type=Path, required=True)
    parser.add_argument("--split", choices=("selection", "blind"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--record-decision", action="store_true", help="Lock the computed selection pair")
    args = parser.parse_args()
    private = args.private.resolve()
    if private.is_relative_to(HERE.parent):
        parser.error("Private validation artifacts must stay outside the repository")
    if args.record_decision and args.split != "selection":
        parser.error("A selection decision can only be recorded from the selection split")
    decision_path = private / "selection-decision.json"
    result_path = args.output / f"{args.split}-results.json"
    metrics_path = args.output / f"{args.split}-metrics.csv"
    if result_path.exists() or metrics_path.exists() or (args.record_decision and decision_path.exists()):
        parser.error("Assessment outputs already exist. Use a fresh output directory and preserve the decision lock.")
    try:
        report = locked_assessment(private, PUBLIC, args.split)
        args.output.mkdir(parents=True, exist_ok=True)
        write_csv(metrics_path, METRIC_FIELDS, metrics_rows(report))
        write_json_exclusive(result_path, report)
        if args.record_decision:
            record = {key: report[key] for key in ("run_id", "selected_model", "comparator_model", "rationale",
                                                   "upgrade_adopted", "protocol_sha256", "forecast_sha256")}
            record["selection_predictions_sha256"] = report["predictions_sha256"]
            write_json_exclusive(decision_path, record)
        print(report["rationale"])
    except (OSError, ValueError, KeyError, TypeError, csv.Error) as error:
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    main()
