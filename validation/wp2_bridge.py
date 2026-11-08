"""Reproduce a WP2 forecast from public inputs and prepare its WP3 lock files."""

import argparse
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, replace
import csv
import hashlib
from itertools import groupby, islice
import json
from math import fsum, isclose, isfinite
from pathlib import Path
from random import Random
import subprocess
import sys
from tempfile import TemporaryDirectory


STATUS_KEYS = ("case_id", "model_id", "scenario_id")
EVENTS = {"PLANE_GOAL", "PLANE_WIDE", "GROUND_FIRST", "NO_REACH", "NUMERICAL_FAILURE"}
PUBLIC_COLUMNS = ("case_id", "split", "stratum", "scenario_id",
                  "t1_s", "x1_m", "y1_m", "z1_m", "t2_s", "x2_m", "y2_m", "z2_m")
REGISTRY = Path("inference/selection-scenarios.json")
WP2_SOURCES = (
    "inference/forecast.py", "inference/baseline.py", "inference/m2.py",
    "inference/likelihood.py", REGISTRY.as_posix(), "spec/case.json",
)


class BufferedExecutor(ProcessPoolExecutor):
    """Backport bounded, ordered map for the WP2 entry point on Python 3.13."""

    def map(self, fn, jobs, *, buffersize):
        jobs = iter(jobs)
        pending = deque(self.submit(fn, job) for job in islice(jobs, buffersize))
        for job in jobs:
            yield pending.popleft().result()
            pending.append(self.submit(fn, job))
        while pending:
            yield pending.popleft().result()


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, data):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(data, stream, indent=2, allow_nan=False)
        stream.write("\n")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def check_wp2(path, config):
    revision = config["source_commit"]
    subprocess.run(["git", "-C", str(path), "diff", "--quiet", revision, "--", *WP2_SOURCES],
                   check=True)
    if digest(path / REGISTRY) != config["scenario_sha256"]:
        raise ValueError("The WP2 scenario registry differs from the selection lock")


def point_status(rows, minimum):
    """Apply the locked entry-conditioned ESS gate to a valid forecast group."""
    total, goal = [], []
    draw_ids = set()
    resolved = False
    for row in rows:
        draw_id, event = row["draw_id"], row["event"]
        weight = float(row["weight"])
        if (not draw_id.strip() or draw_id in draw_ids or event not in EVENTS
                or not isfinite(weight) or not 0 <= weight <= 1):
            raise ValueError("Malformed WP2 forecast group")
        draw_ids.add(draw_id)
        total.append(weight)
        if weight > 0 and event != "NUMERICAL_FAILURE":
            resolved = True
        if weight > 0 and event == "PLANE_GOAL":
            goal.append(weight)
    if not isclose(fsum(total), 1, abs_tol=1e-9, rel_tol=0):
        raise ValueError("WP2 forecast group weights do not sum to one")
    if not resolved:
        return None
    if goal:
        mass = fsum(goal)
        ess = 1 / fsum((weight / mass) ** 2 for weight in goal)
        if ess >= minimum or isclose(ess, minimum, rel_tol=1e-12):
            return "available"
    return "abstained"


def status_csv(path, predictions, cases, model_configs):
    def key(row):
        return tuple(row[name] for name in STATUS_KEYS)

    remaining = {(case["case_id"], model, case["scenario_id"])
                 for case in cases for model in model_configs}
    with (predictions.open(encoding="utf-8", newline="") as source,
          path.open("x", encoding="utf-8", newline="") as output):
        writer = csv.writer(output)
        writer.writerow((*STATUS_KEYS, "point_status"))
        for group, draws in groupby(csv.DictReader(source), key):
            if group not in remaining:
                raise ValueError(f"Unexpected or noncontiguous WP2 forecast group: {group}")
            remaining.remove(group)
            status = point_status(draws, model_configs[group[1]]["minimum_conditional_ess"])
            if status is not None:
                writer.writerow((*group, status))
        if remaining:
            raise ValueError(f"Missing {len(remaining)} WP2 forecast groups")


def run_wp2(wp2, wp1, arguments):
    # Run unmodified WP2 code in a child so it sees only the supplied public inputs.
    subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()), "_forecast",
                    str(wp2), str(wp1), *arguments], cwd=wp2, check=True)


def wp2_main(wp2, wp1, arguments):
    sys.path[:0] = [str(wp2), str(wp1)]
    from inference import forecast

    if sys.version_info < (3, 14):
        forecast.ProcessPoolExecutor = BufferedExecutor
    sys.argv = ["inference.forecast", *arguments]
    forecast.main()


def blind_cases(path, freeze):
    entry = freeze["splits"]["blind"]
    if digest(path) != entry["public_cases_sha256"]:
        raise ValueError("Only the hash-verified public blind cases may be used")
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != PUBLIC_COLUMNS:
            raise ValueError("Unexpected public blind case columns")
        rows = list(reader)
    if (len(rows) != entry["n_cases"]
            or any(row["split"] != "blind" or row["stratum"] != "withheld" for row in rows)):
        raise ValueError("Unexpected public blind case split or membership")
    return rows


def supplied_case(wp2, scenario_id):
    spec = read_json(wp2 / "spec" / "case.json")
    row = dict(case_id=spec["case_id"], split="public", stratum="supplied", scenario_id=scenario_id)
    for index, observation in enumerate(spec["observations"], 1):
        row[f"t{index}_s"] = observation["t_s"]
        for axis in "xyz":
            row[f"{axis}{index}_m"] = observation[f"{axis}_m"]
    return [row]


def trace_fan(wp2, wp1, settings, model, case_id, scenario, draws, seed, count=80, trace_seed=506):
    """Use the pinned sampler and replay a weighted selection with WP1 traces."""
    sys.path[:0] = [str(wp2), str(wp1)]
    from inference import forecast as wp2_forecast
    from physics import load_case, solve

    case = load_case(wp2 / "spec" / "case.json")
    case = replace(case, wind=tuple(settings.get("wind_m_s", case.wind)))
    case_seed = int.from_bytes(hashlib.sha256(f"{seed}:{case_id}:{scenario}".encode()).digest()[:8],
                               "big")
    original_predict = wp2_forecast.predict
    last_parameters = None

    def capture(model_id, flight_case, parameters):
        nonlocal last_parameters
        last_parameters = parameters
        return original_predict(model_id, flight_case, parameters)

    wp2_forecast.predict = capture
    try:
        forecasts = [(i, w, event, last_parameters) for i, w, event in
                     wp2_forecast.forecast(case, model, settings, draws, case_seed)
                     if w > 0 and event.event != "NUMERICAL_FAILURE"]
    finally:
        wp2_forecast.predict = original_predict

    mass = fsum(weight for _, weight, _, _ in forecasts)
    start = Random(trace_seed).random()
    cumulative, index = 0.0, 0
    selected = []
    seen = set()
    for sample in range(count if forecasts else 0):
        target = (start + sample) * mass / count
        while index < len(forecasts) - 1 and cumulative + forecasts[index][1] < target:
            cumulative += forecasts[index][1]
            index += 1
        draw_id, weight, event, parameters = forecasts[index]
        if draw_id in seen:
            continue
        seen.add(draw_id)
        flight = solve(model, case, parameters, include_trace=True)
        if flight.event != event or not all(flight.observation_valid):
            raise ValueError("Trace replay differs from the WP2 first-event forecast")
        selected.append({"draw_id": draw_id, "weight": weight, "event": asdict(event),
                         "trace": [asdict(point) for point in flight.trace]})

    baselines = []
    for baseline in ("B0", "B1", "B2"):
        flight = solve(baseline, case, include_trace=True)
        baselines.append({"model_id": baseline, "event": asdict(flight.event),
                          "trace": [asdict(point) for point in flight.trace]})
    return {"model_id": model, "case_id": case_id, "scenario_id": scenario,
            "forecast_seed": seed, "trace_seed": trace_seed, "requested_traces": count,
            "method": "systematic sampling of resolved weighted draws, repeated draw IDs omitted",
            "fan": selected, "baselines": baselines}


def prepare(args):
    config = read_json(args.selection_config)
    check_wp2(args.wp2, config)
    models = {model: dict(config["models"][model]) for model in args.models}
    if len(models) != len(args.models):
        raise ValueError("Model IDs must be distinct")
    scenarios = {settings["scenario_id"] for settings in models.values()}
    if len(scenarios) != 1:
        raise ValueError("The WP2 bridge requires a common forecast scenario")
    scenario = scenarios.pop()
    blind = args.mode == "blind"
    if blind:
        freeze = read_json(args.freeze)
        if freeze["run_id"] != config["input_run_id"] or len(models) != 2:
            raise ValueError("Expected the locked WP3 run ID and two blind models")
        cases = blind_cases(args.cases, freeze)
        budgets = {model["draw_budget"] for model in models.values()}
        if len(budgets) != 1:
            raise ValueError("The selected WP2 models have different frozen draw budgets")
        draws = budgets.pop()
    else:
        cases = supplied_case(args.wp2, scenario)
        draws = args.draws
        for model in models.values():
            model["draw_budget"] = draws
    if min(draws, args.workers) < 1 or args.output.exists():
        raise ValueError("Expected a positive budget and worker count, and a fresh output path")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=args.output.parent) as temp:
        stage = Path(temp) / "forecast"
        if blind:
            cases_path = args.cases
        else:
            cases_path = Path(temp) / "cases.csv"
            with cases_path.open("x", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=PUBLIC_COLUMNS)
                writer.writeheader()
                writer.writerows(cases)
        switches = ["--models", *models, "--draws", str(draws), "--seed", str(args.seed),
                    "--workers", str(args.workers)]
        run_wp2(args.wp2, args.wp1, [str(cases_path), str(args.wp2 / REGISTRY), str(stage), *switches])
        diagnostics = read_json(stage / "diagnostics.json")
        if (diagnostics["cases_sha256"] != digest(cases_path)
                or diagnostics["scenario_sha256"] != config["scenario_sha256"]
                or diagnostics["seed"] != args.seed):
            raise ValueError("WP2 diagnostics disagree with the requested forecast inputs")
        if not blind:
            (stage / "cases.csv").write_bytes(cases_path.read_bytes())
        status_csv(stage / "point-status.csv", stage / "predictions.csv", cases, models)
        config.update(models=models, split=args.mode, seed=args.seed,
                      input_sha256=diagnostics["cases_sha256"],
                      predictions_sha256=digest(stage / "predictions.csv"),
                      point_status_sha256=digest(stage / "point-status.csv"),
                      point_status_rule="available when positive goal mass has conditional ESS at least the locked minimum",
                      python_version=sys.version.split()[0], workers=args.workers,
                      reproduce=subprocess.list2cmdline([sys.executable, "-B", *sys.argv]))
        write_json(stage / "forecast.json", config)
        if not blind and args.trace_model:
            if args.trace_model not in models:
                raise ValueError("Trace model must be in the public forecast model list")
            settings = read_json(args.wp2 / REGISTRY)[scenario]
            write_json(stage / "traces.json", trace_fan(
                args.wp2, args.wp1, settings, args.trace_model, cases[0]["case_id"], scenario,
                draws, args.seed,
            ))
        stage.rename(args.output)


def main():
    if len(sys.argv) >= 4 and sys.argv[1] == "_forecast":
        wp2_main(Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4:])
        return
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="mode", required=True)
    for mode in ("blind", "public"):
        command = commands.add_parser(mode)
        command.add_argument("--wp2", type=Path, required=True, help="WP2 Git checkout")
        command.add_argument("--wp1", type=Path, required=True, help="parent of the WP1 physics package")
        command.add_argument("--selection-config", type=Path, required=True)
        command.add_argument("--output", type=Path, required=True)
        command.add_argument("--models", nargs="+", required=True)
        command.add_argument("--seed", type=int, required=True)
        command.add_argument("--workers", type=int, default=12)
        if mode == "blind":
            command.add_argument("--cases", type=Path, required=True)
            command.add_argument("--freeze", type=Path, required=True)
        else:
            command.add_argument("--draws", type=int, required=True)
            command.add_argument("--trace-model")
    args = parser.parse_args()
    for name in ("wp2", "wp1", "selection_config", "output", "cases", "freeze"):
        if hasattr(args, name):
            setattr(args, name, getattr(args, name).resolve())
    try:
        prepare(args)
    except (OSError, ValueError, KeyError, csv.Error, subprocess.CalledProcessError) as error:
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    main()
