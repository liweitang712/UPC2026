"""Check frozen UPC probability identities and manuscript evidence."""

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import re


def load(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream)) if path.suffix == ".csv" else json.load(stream)


def close(left, right):
    return math.isclose(float(left), float(right), rel_tol=0, abs_tol=1e-9)


def resolves(data, selector):
    """Resolve JSON paths and field-equality filters used in the release ledger."""
    head, _, filters = selector.partition("[")
    for key in head.split("."):
        data = data[key]
    if filters:
        pairs = [part.split("=", 1) for part in filters.rstrip("]").split(",")]
        return any(all(str(row[key]) == value for key, value in pairs) for row in data)
    return True


def check_location_release(root, abstract_path):
    run_id = load(root / "forecast-lock.json")["run_id"]
    t2 = load(root / "T2.json")
    t3 = load(root / "T3.csv")
    reach, goal, ground, no_reach, failure = (
        t2[key] for key in ("p_reach", "p_goal", "p_ground_first", "p_no_reach", "p_failure")
    )
    mode = t2["entry_mode_assessment"]["recommended_mode_yz_m"]
    arrival = t2["plane_intervals"]["t_s"][1]
    counts = [row for row in t3 if row["group"] == "core"]
    figure_rows = load(root / "figures/figures_manifest.csv")
    claims = load(root / "claims.csv")
    abstract = re.sub(r"(?m)^%.*$", "", abstract_path.read_text(encoding="utf-8-sig"))
    required = [f"({mode[0]:.2f},{mode[1]:.2f})", f"{arrival:.3f}",
                f"{100 * goal:.1f}\\%"]
    required.extend(f"{row['n_hit_95']} of {row['n_supported']}" for row in counts)
    for axis in ("y_m", "z_m"):
        lo, _, hi = t2["goal_intervals"][axis]
        required.append(f"[{lo:.2f},{hi:.2f}]")
    checks = {
        "location run IDs": all(row["run_id"] == run_id for row in t3 + figure_rows + claims),
        "T2 event mass and conditional identity": (
            all(0 <= value <= 1 for value in (reach, goal, ground, no_reach, failure))
            and 0 <= t2["p_clearance_goal"] <= goal <= reach
            and close(reach + ground + no_reach + failure, 1)
            and (close(goal, reach * t2["p_goal_given_reach"]) if reach
                 else t2["p_goal_given_reach"] is None)
        ),
        "T3 core counts sum from strata": all(
            sum(int(row[field]) for row in t3 if row["model"] == core["model"]
                and row["group"] not in {"core", "challenge"}) == int(core[field])
            for core in counts for field in ("n_eligible", "n_truth_plane", "n_supported", "n_hit_95")
        ),
        "claim ledger sources exist": all((root / row["evidence"]).is_file() for row in claims),
        "figure hashes": len(figure_rows) == 6 and all(
            hashlib.sha256((root / "figures" / f"{row['figure']}.pdf").read_bytes()).hexdigest()
            == row["pdf_sha256"] for row in figure_rows
        ),
        "location abstract display values": all(value in abstract for value in required),
    }
    for label, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'} {label}")
    for value in required:
        if value not in abstract:
            print(f"  Missing abstract value: {value}")
    return not all(checks.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release", type=Path)
    parser.add_argument("--abstract", type=Path, required=True,
                        help="00-summary.tex in the manuscript to audit")
    args = parser.parse_args()
    root = args.release.resolve()
    if (root / "T2.json").is_file() and (root / "forecast-lock.json").is_file():
        return check_location_release(root, args.abstract)
    failed = []

    def report(label, errors):
        print(f"{'FAIL' if errors else 'PASS'} {label}")
        for error in errors:
            print(f"  {error}")
        failed.extend(errors)

    release = load(root / "release.json")
    summary = load(root / "summary.json")
    blind = load(root / "blind-results.json")
    run = release["run_id"]
    report("release, summary and blind run IDs", [
        name for name, data in (("summary", summary), ("blind", blind)) if data["run_id"] != run
    ])
    errors = []
    keys = ("p_reach", "p_goal", "p_clearance_goal", "p_ground_first", "p_no_reach", "p_failure")
    for row in summary["results"] + summary.get("supplied_kick_repeat", []):
        reach, goal, clearance, ground, no_reach, failure = (row[k] for k in keys)
        conditional = row["p_goal_given_reach"]
        if (not all(0 <= row[k] <= 1 + 1e-9 for k in keys)
                or clearance > goal + 1e-9 or goal > reach + 1e-9
                or not close(reach + ground + no_reach + failure, 1)
                or (reach > 0 and (conditional is None or not close(goal, reach * conditional)))
                or (reach == 0 and conditional is not None)):
            errors.append(f"{row['case_id']} {row['model_id']} {row['scenario_id']}")
    report("event partition, nesting and conditional identity", errors)

    supplied = {(r["case_id"], r["model_id"], r["scenario_id"]): r
                for r in summary["results"] if r["split"] == "supplied_kick"}
    t2 = load(root / "T2.csv")
    errors = []
    for row in t2:
        key = tuple(row[k] for k in ("case_id", "model_id", "scenario_id"))
        match = supplied.pop(key, None)
        if match is None or row["run_id"] != run or not all(close(row[k], match[k]) for k in keys):
            errors.append(str(key))
            continue
        for key in ("entry_mode_yz_m", "entry_mode", "plane_intervals", "goal_intervals"):
            if json.loads(row[key]) != match[key]:
                errors.append(f"{row['model_id']} {key}")
    report("T2 matches supplied-kick summary", errors + [str(key) for key in supplied])

    t3 = load(root / "paper/T3.csv")
    errors = []
    for model, score in blind["models"].items():
        rows = [r for r in t3 if r["model_id"] == model and r["stratum"] != "challenge"]
        core = score["core"]
        for field in ("n_total", "n_eligible", "n_truth_plane", "n_region_supported", "n_region_hits"):
            if sum(int(r[field]) for r in rows) != core[field]:
                errors.append(f"{model} {field}")
        if not rows or not close(sum(float(r["penalized_entry_brier"]) for r in rows) / len(rows),
                                 core["entry_brier_failure_penalized"]):
            errors.append(f"{model} core Brier")
    report("T3 core totals and equal-stratum Brier", errors)

    ledger = root / "paper/claims.csv"
    errors = []
    seen = set()
    for claim in load(ledger):
        claim_id = claim["claim_id"]
        source = (ledger.parent / claim["source_artifact"]).resolve()
        try:
            if claim_id in seen or claim["run_id"] != run or not source.is_relative_to(root):
                raise ValueError("duplicate ID, wrong run, or path outside release")
            seen.add(claim_id)
            data = load(source)
            selector = claim["source_key_or_filter"]
            if source.suffix == ".json":
                parts = re.split(r",\s*(?![^\[]*\])", selector)
                # The v1 ledger uses the prose alias selected_model for recommended_model.
                parts = ["recommended_model" if key == "selected_model" and key not in data else key
                         for key in parts]
                if not all(resolves(data, part) for part in parts):
                    raise ValueError("JSON selector matches no rows")
            elif "=" in selector:
                key, value = selector.split("=", 1)
                if not any(row[key] == value for row in data):
                    raise ValueError("CSV filter matches no rows")
            elif not data:
                raise ValueError("empty CSV source")
            if claim.get("numeric_value"):
                value = claim["numeric_value"]
                path = claim.get("numeric_key") or selector
                target = data
                for key in path.split("."):
                    target = target[int(key)] if isinstance(target, list) else target[key]
                if not close(value, target):
                    raise ValueError("explicit numeric claim differs from its source")
        except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
            errors.append(f"{claim_id}: {exc}")
    report("claim ledger source references and explicit numeric values", errors)

    abstract = re.sub(r"(?m)^%.*$", "", args.abstract.read_text(encoding="utf-8-sig"))
    reference = release["recommended_model"]
    kick = next(r for r in t2 if r["model_id"] == reference)
    plane = json.loads(kick["plane_intervals"])
    mode = json.loads(kick["entry_mode_yz_m"])
    counts = json.loads(kick["entry_mode"])["contributing_count"]
    required = [f"({mode[0]:.2f},{mode[1]:.2f})", f"{plane['t_s'][1]:.3f}",
                f"{plane['t_s'][1] - .10:.3f}", f"{counts:,}",
                *[f"[{plane[k][0]:.2f},{plane[k][2]:.2f}]" for k in ("y_m", "z_m")]]
    for model in (reference, release["comparator_model"]):
        core = blind["models"][model]["core"]
        required.extend((f"{core['entry_brier_failure_penalized']:.4f}",
                         f"{core['coverage_95']:.1%}".replace("%", r"\%")))
    report("v1 abstract display values", [f"missing {value}" for value in required if value not in abstract])
    return bool(failed)


if __name__ == "__main__":
    raise SystemExit(main())
