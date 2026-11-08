"""Record a forecast snapshot and score only after verifying its freeze hashes."""

import argparse
import csv
import json
import re
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from validation.generate_cases import CASE_PATH, HERE, PROTOCOL_PATH, read_json, sha256, write_json
from validation.score_entry import METRIC_FIELDS, score_entry

PUBLIC = HERE / "frozen" / "v1"


def check_hash(path, expected, *, text_source=False):
    if sha256(path, text_source=text_source) != expected:
        raise ValueError(f"Freeze hash mismatch: {path.name}")


def verify_inputs(public, split):
    manifest = read_json(public / "freeze.json")
    entry = manifest["splits"][split]
    check_hash(PROTOCOL_PATH, manifest["protocol_sha256"], text_source=True)
    check_hash(HERE / "generate_cases.py", manifest["generator_sha256"], text_source=True)
    check_hash(CASE_PATH, manifest["case_spec_sha256"], text_source=True)
    check_hash(public / split / "cases.csv", entry["public_cases_sha256"])
    return manifest


def verify_lock(lock, split, manifest):
    metadata = read_json(lock / "lock.json")
    if (metadata["split"] != split or metadata["run_id"] != manifest["run_id"]
            or metadata["cases_sha256"] != manifest["splits"][split]["public_cases_sha256"]):
        raise ValueError("Prediction lock belongs to a different case freeze")
    check_hash(lock / "predictions.csv", metadata["predictions_sha256"])
    check_hash(lock / "forecast.json", metadata["forecast_sha256"])
    if metadata.get("point_status_sha256"):
        check_hash(lock / "point-status.csv", metadata["point_status_sha256"])
    return metadata, read_json(lock / "forecast.json")


def selection_record(private, manifest):
    selection_lock = private / "selection-predictions"
    verify_lock(selection_lock, "selection", manifest)
    path = private / "selection-decision.json"
    decision = read_json(path)
    if decision["selection_predictions_sha256"] != sha256(selection_lock / "predictions.csv"):
        raise ValueError("Model choice refers to a different selection forecast")
    candidates = read_json(PROTOCOL_PATH)["models"]
    pair = decision["selected_model"], decision["comparator_model"]
    if len(set(pair)) != 2 or any(model not in candidates for model in pair):
        raise ValueError("Record distinct registered selected and comparator models")
    if not decision["rationale"].strip():
        raise ValueError("Record the selection rationale")
    return path, pair


def freeze_predictions(private, public, split, predictions, config, point_status=None):
    manifest = verify_inputs(public, split)
    if split == "blind" and point_status is None:
        raise ValueError("Blind prediction freeze requires point status for F5")
    destination = private / f"{split}-predictions"
    if destination.exists():
        raise ValueError("This split already has a prediction lock")
    with TemporaryDirectory(dir=private) as temp:
        stage = Path(temp) / "bundle"
        stage.mkdir()
        shutil.copyfile(predictions, stage / "predictions.csv")
        shutil.copyfile(config, stage / "forecast.json")
        if point_status is not None:
            shutil.copyfile(point_status, stage / "point-status.csv")
        forecast = read_json(stage / "forecast.json")
        models = forecast["models"]
        if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", forecast["source_commit"]):
            raise ValueError("Forecast config requires a full source commit hash")
        if not isinstance(models, dict) or not all(isinstance(value, dict) and value for value in models.values()):
            raise ValueError("Forecast config requires a settings object for each model")
        if split == "selection":
            expected = read_json(PROTOCOL_PATH)["models"]
            decision_hash = None
        else:
            decision_path, expected = selection_record(private, manifest)
            decision_hash = sha256(decision_path)
            selected_config = read_json(private / "selection-predictions" / "forecast.json")
            if (forecast["source_commit"] != selected_config["source_commit"]
                    or any(models.get(model) != selected_config["models"][model] for model in expected)):
                raise ValueError("Blind source revision or model settings differ from the selection lock")
        if set(models) != set(expected):
            raise ValueError("Forecast model set differs from the preregistered or selected set")
        write_json(stage / "lock.json", {
            "run_id": manifest["run_id"], "split": split,
            "cases_sha256": manifest["splits"][split]["public_cases_sha256"],
            "forecast_sha256": sha256(stage / "forecast.json"),
            "predictions_sha256": sha256(stage / "predictions.csv"),
            "selection_decision_sha256": decision_hash,
            "point_status_sha256": sha256(stage / "point-status.csv") if point_status is not None else None,
        })
        stage.rename(destination)


def score_locked(private, public, split):
    manifest = verify_inputs(public, split)
    lock = private / f"{split}-predictions"
    metadata, forecast = verify_lock(lock, split, manifest)
    if split == "blind":
        decision_path, _ = selection_record(private, manifest)
        check_hash(decision_path, metadata["selection_decision_sha256"])
    entry = manifest["splits"][split]
    cases, truth = private / f"{split}-cases.csv", private / f"{split}-truth.csv"
    check_hash(cases, entry["scoring_cases_sha256"])
    check_hash(truth, entry["truth_sha256"])
    rows = list(score_entry(cases, truth, lock / "predictions.csv", run_id=manifest["run_id"],
                            split=split, models=forecast["models"]))
    with (private / f"{split}-entry-metrics.csv").open("x", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=METRIC_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private", required=True, type=Path)
    parser.add_argument("--split", required=True, choices=("selection", "blind"))
    commands = parser.add_subparsers(dest="command", required=True)
    freeze = commands.add_parser("freeze")
    freeze.add_argument("--predictions", required=True, type=Path)
    freeze.add_argument("--config", required=True, type=Path)
    freeze.add_argument("--point-status", type=Path)
    commands.add_parser("score")
    args = parser.parse_args()
    private = args.private.resolve()
    if private.is_relative_to(HERE.parent):
        parser.error("Private validation artifacts must stay outside the repository")
    try:
        if args.command == "freeze":
            freeze_predictions(private, PUBLIC, args.split, args.predictions, args.config, args.point_status)
        else:
            score_locked(private, PUBLIC, args.split)
    except (OSError, ValueError, KeyError, TypeError, csv.Error) as error:
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    main()
