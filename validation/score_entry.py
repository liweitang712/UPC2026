"""Score frozen center-in-goal forecasts using the WP3 validation protocol."""

import argparse
import csv
from collections import defaultdict
from math import fsum, isclose, isfinite
from pathlib import Path
from statistics import mean

PHYSICAL_EVENTS = {"PLANE_GOAL", "PLANE_WIDE", "GROUND_FIRST", "NO_REACH"}
FAILURE = "NUMERICAL_FAILURE"
METRIC_FIELDS = (
    "run_id", "split", "stratum", "model_id", "scenario_id", "metric", "value",
    "unit", "n_total", "n_eligible", "n_scored", "n_failed", "interval_lo", "interval_hi",
)


def read_rows(path, required):
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source, strict=True)
        fields = reader.fieldnames or []
        if not set(required).issubset(fields) or len(fields) != len(set(fields)):
            raise ValueError(f"{path}: missing or duplicate CSV columns")
        for row in reader:
            if None in row or None in row.values():
                raise ValueError(f"{path}:{reader.line_num}: inconsistent column count")
            yield row


def by_case(rows, name):
    indexed = {}
    for row in rows:
        case_id = row["case_id"]
        if not case_id.strip() or case_id in indexed:
            raise ValueError(f"{name}: blank or duplicate case_id {case_id!r}")
        indexed[case_id] = row
    return indexed


def entry_loss(draws, outcome):
    """Return penalized loss, exact-probability loss, and unresolved status."""
    seen = set()
    weights = defaultdict(list)
    for draw in draws:
        draw_id, event = draw["draw_id"], draw["event"]
        try:
            weight = float(draw["weight"])
        except ValueError:
            return 1.0, None, True
        if (not draw_id.strip() or draw_id in seen
                or event not in PHYSICAL_EVENTS | {FAILURE}
                or not isfinite(weight) or not 0 <= weight <= 1):
            return 1.0, None, True
        seen.add(draw_id)
        weights[event].append(weight)

    total = fsum(fsum(values) for values in weights.values())
    if not isclose(total, 1.0, rel_tol=0, abs_tol=1e-9):
        return 1.0, None, True

    lower = fsum(weights["PLANE_GOAL"]) / total
    unresolved = fsum(weights[FAILURE]) / total
    lower_loss = (lower - outcome) ** 2
    if not unresolved:
        return lower_loss, lower_loss, False
    return max(lower_loss, (min(1.0, lower + unresolved) - outcome) ** 2), None, True


def score_entry(cases_path, truth_path, predictions_path, *, run_id, split, models):
    """Yield metrics.csv rows for the locked case scenarios and expected models."""
    models = tuple(models)
    if not models or len(set(models)) != len(models) or any(not m.strip() for m in models):
        raise ValueError("Supply distinct expected model IDs")
    if not run_id.strip():
        raise ValueError("Supply a nonblank run ID")

    cases = by_case(read_rows(cases_path, ("case_id", "split", "stratum", "scenario_id")), "cases")
    selected = {key: row for key, row in cases.items() if row["split"] == split}
    if not selected or "upc2026-b" in selected:
        raise ValueError("Select a nonempty validation split that excludes the supplied kick")
    truth = by_case(read_rows(truth_path, ("case_id", "event")), "truth")
    if set(selected) - truth.keys() or truth.keys() - cases.keys():
        raise ValueError("Truth rows must cover the selected split and use known case IDs")

    predictions = defaultdict(list)
    columns = ("case_id", "model_id", "scenario_id", "draw_id", "weight", "event")
    for row in read_rows(predictions_path, columns):
        case_id, model_id, scenario_id = (row[key] for key in columns[:3])
        if case_id not in cases:
            raise ValueError(f"Unknown prediction case_id {case_id!r}")
        if case_id not in selected:
            continue
        if model_id not in models or scenario_id != selected[case_id]["scenario_id"]:
            raise ValueError(f"Unexpected model or scenario for {case_id!r}: {model_id!r}, {scenario_id!r}")
        predictions[case_id, model_id].append(row)

    groups = defaultdict(list)
    for case_id, case in selected.items():
        event = truth[case_id]["event"]
        if event not in PHYSICAL_EVENTS | {FAILURE}:
            raise ValueError(f"Unknown truth event for {case_id!r}: {event!r}")
        stratum, scenario_id = case["stratum"], case["scenario_id"]
        if not stratum.strip() or not scenario_id.strip():
            raise ValueError(f"Blank stratum or scenario_id for {case_id!r}")
        groups[stratum, scenario_id].append((case_id, event))

    for (stratum, scenario_id), group in sorted(groups.items()):
        eligible = [(case_id, event == "PLANE_GOAL") for case_id, event in group if event != FAILURE]
        for model_id in models:
            scores = [entry_loss(predictions.get((case_id, model_id), ()), outcome)
                      for case_id, outcome in eligible]
            penalized = [loss for loss, _, _ in scores]
            exact = [loss for _, loss, _ in scores if loss is not None]
            for metric, values in (("entry_brier_failure_penalized", penalized), ("entry_brier", exact)):
                yield {
                    "run_id": run_id, "split": split, "stratum": stratum, "model_id": model_id,
                    "scenario_id": scenario_id, "metric": metric,
                    "value": mean(values) if values else "", "unit": "1",
                    "n_total": len(group), "n_eligible": len(eligible), "n_scored": len(values),
                    "n_failed": sum(failed for _, _, failed in scores),
                    "interval_lo": "", "interval_hi": "",
                }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("cases", "truth", "predictions", "output"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--split", required=True, choices=("development", "selection", "blind"))
    parser.add_argument("--models", nargs="+", required=True)
    args = parser.parse_args()
    try:
        rows = list(score_entry(args.cases, args.truth, args.predictions,
                                run_id=args.run_id, split=args.split, models=args.models))
        with args.output.open("x", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=METRIC_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
    except (OSError, ValueError, csv.Error) as error:
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    main()
