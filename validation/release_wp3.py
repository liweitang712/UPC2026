"""Assemble a reproducible release from verified WP3 forecast and evidence locks."""

import argparse
import csv
import json
import re
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from validation.generate_cases import CASE_PATH, CASE_FIELDS, HERE, PROTOCOL_PATH, read_json, sha256, write_csv, write_json
from validation.locked_score import PUBLIC, check_hash, selection_record, verify_inputs, verify_lock
from validation.score_entry import METRIC_FIELDS, by_case, read_rows
from validation.summarize_wp3 import KEY, compare_kick, summarize_file

FIGURE_FIELDS = ("asset_id", "run_id", "version", "owner", "population", "scenario_id", "condition",
                 "statistic", "units", "source_artifact", "row_filters", "pdf", "png", "caption", "source_hashes")
EXTRAS = ("T1.csv", "blind-conditional.csv", "blind-paired-conditional.csv")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def copy_relative(source_root, name, target_root):
    relative = Path(name)
    require(not relative.is_absolute() and not relative.drive and ".." not in relative.parts,
            f"Unsafe artifact path {name!r}")
    source = (source_root / relative).resolve()
    require(source.is_relative_to(source_root.resolve()), f"Artifact escapes source directory: {name!r}")
    target = target_root / relative
    if target.exists():
        require(sha256(target) == sha256(source), f"Conflicting artifacts share {name!r}")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return target


def collect_figures(folder, output, run_id, expected_ids, frozen_hashes=None):
    rows = list(read_rows(folder / "figures_manifest.csv", FIGURE_FIELDS))
    ids = [row["asset_id"] for row in rows]
    require(len(ids) == len(set(ids)) and set(ids) == set(expected_ids), "Figure manifest IDs differ from release plan")
    for row in rows:
        require(row["run_id"] == run_id and "preview" not in row["population"].lower(),
                f"{row['asset_id']} has a foreign or preview run ID")
        if frozen_hashes is not None:
            source_hashes = dict(part.strip().split("=", 1) for part in row["source_hashes"].split(";"))
            require(source_hashes == frozen_hashes, f"{row['asset_id']} does not match the blind freeze")
        for name in (row["pdf"], row["png"], row["caption"]):
            copy_relative(folder, name, output)
        for source in row["source_artifact"].split(";"):
            name = source.strip()
            require(bool(name), f"{row['asset_id']} is missing an evidence source")
            if name != "summary.json":
                copy_relative(folder, name, output)
        row["source_artifact"] = "; ".join(
            "../summary.json" if name.strip() == "summary.json" else name.strip()
            for name in row["source_artifact"].split(";")
        )
    return rows


def expected_bundles(path, models, run_split, scenario):
    cases = by_case(read_rows(path, ("case_id", "split", "scenario_id")), "cases")
    require(bool(cases) and all(row["split"] == run_split and row["scenario_id"] == scenario
                              for row in cases.values()), f"Unexpected {run_split} case split or scenario")
    return {(case_id, model, scenario) for case_id in cases for model in models}


def check_report(report, split, run_id, metadata, decision, models):
    require(report["split"] == split and report["run_id"] == run_id
            and report["predictions_sha256"] == metadata["predictions_sha256"]
            and report["forecast_sha256"] == metadata["forecast_sha256"],
            f"{split} report does not describe the locked forecast")
    require(set(report["models"]) == set(models), f"{split} report does not cover the locked roster")
    require((report["selected_model"], report["comparator_model"]) == decision,
            f"{split} report describes a different model decision")


def metric_rows(path, split, run_id, scenario, models):
    seen = set()
    for row in read_rows(path, METRIC_FIELDS):
        key = tuple(row[field] for field in METRIC_FIELDS[:6])
        require(key not in seen and row["run_id"] == run_id and row["split"] == split
                and row["scenario_id"] == scenario and row["model_id"] in models,
                f"Unexpected {split} metric key {key!r}")
        seen.add(key)
        yield {field: row[field] for field in METRIC_FIELDS}
    require(bool(seen), f"No {split} metrics")


def kick_summary(args, output, case, protocol, models, nominal):
    decision = protocol["decision"]
    scenario = protocol["scenario_id"]
    registry = read_json(args.kick_registry)
    require(set(registry) == {scenario}, "Supplied-shot registry must contain exactly the locked nominal scenario")
    settings = registry[scenario]
    require(settings.get("sigma_m") == nominal["sigma_m"] and not settings.get("rounding_width_m", 0)
            and settings.get("wind_m_s", [0, 0, 0]) == nominal["wind_m_s"],
            "Supplied-shot observation settings differ from the selected forecast")
    cases = list(read_rows(args.kick_cases, CASE_FIELDS))
    require(len(cases) == 1 and cases[0]["case_id"] == case["case_id"]
            and cases[0]["scenario_id"] == scenario, "Expected the supplied kick in the nominal scenario")
    for i, observed in enumerate(case["observations"], 1):
        for field, value in observed.items():
            axis, unit = field.split("_")
            require(float(cases[0][f"{axis}{i}_{unit}"]) == value,
                    "Supplied-shot observation differs from spec/case.json")
    expected = {(case["case_id"], model, scenario) for model in models}
    manifest = {}
    results = {}
    for name, folder in (("primary", args.kick_run), ("repeat", args.kick_repeat)):
        target = output / "kick" / name
        diagnostics = read_json(folder / "diagnostics.json")
        require(diagnostics["cases_sha256"] == sha256(args.kick_cases)
                and diagnostics["scenario_sha256"] == sha256(args.kick_registry),
                f"{name} supplied-shot diagnostics do not match the declared inputs")
        groups = diagnostics["diagnostics"]
        require(len(groups) == len(expected) and {tuple(g[field] for field in KEY) for g in groups} == expected,
                f"{name} supplied-shot diagnostics do not match the selected pair")
        budgets = {group["budget"] for group in groups}
        require(len(budgets) == 1, f"{name} uses mixed supplied-shot draw budgets")
        manifest[name] = {"seed": diagnostics["seed"], "draw_budget": budgets.pop()}
        results[name] = list(summarize_file(folder / "predictions.csv", expected, decision, case["goal"]))
        for filename in ("diagnostics.json", "predictions.csv"):
            copy_relative(folder, filename, target)
    require(manifest["primary"]["seed"] != manifest["repeat"]["seed"]
            and 2 * manifest["primary"]["draw_budget"] == manifest["repeat"]["draw_budget"],
            "Supplied-shot repeat requires an independent seed and twice the primary draw budget")
    shutil.copyfile(args.kick_cases, output / "kick" / "cases.csv")
    shutil.copyfile(args.kick_registry, output / "kick" / "scenarios.json")
    for primary, repeat in zip(results["primary"], results["repeat"], strict=True):
        repeat_check = compare_kick(primary, repeat)
        primary["diagnostics"]["repeat"] = repeat_check
        if primary["entry_mode_yz_m"] is not None:
            primary["entry_mode"]["numerical_stability"] = (
                "within repeat tolerance" if repeat_check["entry_mode_stable"] else "outside repeat tolerance"
            )
    return results["primary"], results["repeat"], manifest


def build(args, output):
    protocol = read_json(PROTOCOL_PATH)
    case = read_json(CASE_PATH)
    scenario = protocol["scenario_id"]
    freeze = verify_inputs(PUBLIC, "blind")
    verify_inputs(PUBLIC, "selection")
    run_id = freeze["run_id"]
    private = args.private.resolve()
    require(not private.is_relative_to(HERE.parent), "Private inputs must remain outside the repository")
    decision_path, pair = selection_record(private, freeze)
    split_metadata, split_forecast = {}, {}
    for split in ("selection", "blind"):
        split_metadata[split], split_forecast[split] = verify_lock(private / f"{split}-predictions", split, freeze)
    blind = split_metadata["blind"]
    check_hash(decision_path, blind["selection_decision_sha256"])
    require(set(split_forecast["blind"]["models"]) == set(pair), "Blind lock does not use the selected pair")
    require(bool(blind["point_status_sha256"]), "Blind lock lacks point statuses")
    for split in ("selection", "blind"):
        entry = freeze["splits"][split]
        check_hash(private / f"{split}-cases.csv", entry["scoring_cases_sha256"])
        check_hash(private / f"{split}-truth.csv", entry["truth_sha256"])
    models = {split: forecast["models"] for split, forecast in split_forecast.items()}
    all_metrics = []
    records = []
    for split in ("selection", "blind"):
        report_dir = getattr(args, f"{split}_report_dir") or private
        path = report_dir / f"{split}-results.json"
        report = read_json(path)
        check_report(report, split, run_id, split_metadata[split], pair, models[split])
        require(report["protocol_sha256"] == freeze["protocol_sha256"] and report["scenario_id"] == scenario,
                f"{split} report used a different preregistration")
        copy_relative(report_dir, path.name, output)
        all_metrics.extend(metric_rows(report_dir / f"{split}-metrics.csv", split, run_id, scenario, models[split]))
        expected = expected_bundles(PUBLIC / split / "cases.csv", models[split], split, scenario)
        draws = private / f"{split}-predictions" / "predictions.csv"
        records.extend(dict(record, split=split) for record in summarize_file(draws, expected, protocol["decision"]))
    require(isinstance(report["confirmed"], bool), "Blind report must resolve the aggregate improvement gate")
    recommended = report["recommended_model"]
    require(recommended in pair, "Blind recommendation must be one of the locked models")
    write_csv(output / "metrics.csv", METRIC_FIELDS, all_metrics)
    copy_relative(private, decision_path.name, output)
    shutil.copyfile(CASE_PATH, output / "case.json")
    shutil.copyfile(PROTOCOL_PATH, output / "protocol.json")
    shutil.copyfile(PUBLIC / "freeze.json", output / "input-freeze.json")
    for split in freeze["splits"]:
        copy_relative(PUBLIC, f"{split}/cases.csv", output / "cases")
    copy_relative(PUBLIC, "development/truth.csv", output / "cases")
    kick_repeats, kick_provenance = [], None
    if args.kick_run is not None:
        kick_records, kick_repeats, kick_provenance = kick_summary(
            args, output, case, protocol, pair, models["selection"][recommended]
        )
        records.extend(dict(record, split="supplied_kick") for record in kick_records)
    payload = {"run_id": run_id, "results": records, "supplied_kick_repeat": kick_repeats}
    (output / "summary.json").write_text(json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n",
                                        encoding="utf-8", newline="\n")
    if kick_provenance:
        from validation.summarize_wp3 import write_kick_table

        write_kick_table(output / "T2.csv", run_id, kick_records)
    entry = freeze["splits"]["blind"]
    figure_hashes = {"cases": entry["scoring_cases_sha256"], "truth": entry["truth_sha256"],
                     "predictions": blind["predictions_sha256"], "point_status": blind["point_status_sha256"],
                     "protocol": freeze["protocol_sha256"]}
    figures = collect_figures(args.figures, output / "figures", run_id, ("F5", "F6"), figure_hashes)
    if args.extras_dir:
        for filename in EXTRAS:
            copy_relative(args.extras_dir, filename, output)
        if (args.extras_dir / "T2-candidates.json").is_file():
            copy_relative(args.extras_dir, "T2-candidates.json", output)
        figures.extend(collect_figures(args.extras_dir, output / "figures", run_id, ("F1", "F2", "F3", "F4")))
    write_csv(output / "figures" / "figures_manifest.csv", FIGURE_FIELDS,
              [{field: row[field] for field in FIGURE_FIELDS} for row in sorted(figures, key=lambda row: row["asset_id"])])
    for split in ("selection", "blind"):
        for filename in ("forecast.json", "lock.json"):
            copy_relative(private, f"{split}-predictions/{filename}", output)
    seeds = {
        "inference": {split: forecast["seed"] for split, forecast in split_forecast.items()},
        "bootstrap": protocol["decision"]["bootstrap_seed"],
        "generation_and_observation_noise_sha256": sha256(private / "seeds.json"),
    }
    if args.include_generation_seeds:
        seeds["generation_and_observation_noise"] = read_json(private / "seeds.json")
    artifacts = {path.relative_to(output).as_posix(): sha256(path) for path in sorted(output.rglob("*")) if path.is_file()}
    release = {
        "run_id": run_id, "status": "validation_and_supplied_kick" if kick_provenance else "blind_evaluation_complete",
        "schema_version": case["schema_version"], "case_id": case["case_id"], "wp3_commit": args.wp3_commit,
        "wp2_commit": split_forecast["blind"]["source_commit"], "wp2_bundle_revision": args.wp2_bundle_revision,
        "wp1_commit": split_forecast["selection"].get("wp1_revision"),
        "input_freeze": freeze, "model_configurations": models, "scenario_id": scenario,
        "numerical_tolerances": {"prediction": case["protocol_defaults"], "validation": protocol["solver"]},
        "seeds": seeds, "selected_model": pair[0], "comparator_model": pair[1],
        "confirmed_aggregate_improvement": report["confirmed"], "recommended_model": recommended,
        "supplied_kick": kick_provenance, "artifact_sha256": artifacts,
        "metrics_path": "metrics.csv", "summary_path": "summary.json", "figure_manifest_path": "figures/figures_manifest.csv",
        "custody": {split: {
            "scoring_cases": f"{split}-cases.csv", "truth": f"{split}-truth.csv",
            "predictions": f"{split}-predictions/predictions.csv",
            "predictions_sha256": split_metadata[split]["predictions_sha256"],
        } for split in ("selection", "blind")},
    }
    if args.team_number is not None:
        from paper.build_wp3_paper import paper_outputs

        paper_outputs(release, output, output / "paper", args.team_number)
        for path in sorted((output / "paper").rglob("*")):
            if path.is_file():
                artifacts[path.relative_to(output).as_posix()] = sha256(path)
    write_json(output / "release.json", release)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ("private", "figures", "output"):
        parser.add_argument("--" + argument, type=Path, required=True)
    for argument in ("extras-dir", "kick-cases", "kick-registry", "kick-run", "kick-repeat",
                     "selection-report-dir", "blind-report-dir"):
        parser.add_argument("--" + argument, type=Path)
    parser.add_argument("--wp3-commit", required=True)
    parser.add_argument("--wp2-bundle-revision")
    parser.add_argument("--include-generation-seeds", action="store_true")
    parser.add_argument("--team-number")
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise FileExistsError(f"Release output already exists: {args.output}")
        require(re.fullmatch(r"[0-9a-f]{40}", args.wp3_commit), "A full WP3 Git revision is required")
        supplied = (args.kick_cases, args.kick_registry, args.kick_run, args.kick_repeat)
        require(not any(supplied) or all(supplied), "Supply all four kick inputs or omit them all")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=args.output.parent) as folder:
            temporary = Path(folder) / "release"
            temporary.mkdir()
            build(args, temporary)
            temporary.rename(args.output)
    except (OSError, ValueError, KeyError, csv.Error, StopIteration) as error:
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    main()
