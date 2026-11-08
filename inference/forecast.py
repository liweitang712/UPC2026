"""Forecast a WP3 cases.csv using its separately supplied scenario registry."""

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import csv
from dataclasses import asdict, replace
import hashlib
import json
import platform
from math import fsum, isfinite, sqrt
from pathlib import Path
from random import Random

from physics import EventResult, SolverConfig, load_case, solve
from .baseline import ballistic_fit, predict
from .m2 import normalize, sample, SamplingFailure, require_finite_draws
from .likelihood import rounded_log_likelihood


FIELDS = ("case_id", "model_id", "scenario_id", "draw_id", "weight",
          "event", "t_s", "y_m", "z_m", "clearance_goal", "reason")


def forecast_group(job):
    case_id, scenario, settings, case, model, budget, run_seed = job
    digest = hashlib.sha256(f"{run_seed}:{case_id}:{scenario}".encode()).digest()
    seed = int.from_bytes(digest[:8], "big")
    key = dict(case_id=case_id, model_id=model, scenario_id=scenario)
    sampling = {}
    try:
        draws = list(forecast(case, model, settings, budget, seed, sampling))
    except RuntimeError as exc:
        if isinstance(exc, SamplingFailure):
            sampling.update(exc.diagnostics)
        draws = [(0, 1.0, EventResult("NUMERICAL_FAILURE", reason=str(exc)))]
    failures = Counter(event.reason for _, _, event in draws if event.event == "NUMERICAL_FAILURE")
    weights = [weight for _, weight, _ in draws]
    diagnostic = dict(**key, seed=seed, budget=budget, rows=len(draws),
                      ess=1/fsum(w*w for w in weights), max_weight=max(weights),
                      failure_reasons=dict(failures),
                      p_failure=fsum(w for _, w, event in draws if event.event == "NUMERICAL_FAILURE"),
                      sampling=sampling)
    return key, draws, diagnostic


def forecast(case, model, settings, budget, seed, sampling=None):
    sampling = sampling if sampling is not None else {}
    sampling.update(attempted=0, finite_weights=0, rejected={})
    sigma = float(settings["sigma_m"])
    width = float(settings.get("rounding_width_m", 0))
    if not isfinite(sigma) or not isfinite(width) or min(sigma, width) < 0 or sigma + width == 0:
        raise ValueError("Invalid observation error scales.")
    if model in ("B0", "B1", "B2"):
        rng = Random(seed)
        v0, time_scale = ballistic_fit(case)
        if model == "B0" and width and sigma:
            scale = 1.25 * sqrt(sigma*sigma + width*width/12) / time_scale
            draws = []
            for index in range(budget):
                sampling["attempted"] += 1
                velocity = tuple(rng.gauss(v, scale) for v in v0)
                params = {"v0": velocity}
                fit = solve(model, case, params)
                if fit.observations is None:
                    raise RuntimeError(fit.event.reason)
                log_weight = rounded_log_likelihood(case.observations, fit.observations, width, sigma)
                log_weight += 0.5 * fsum(((v - m)/scale)**2 for v, m in zip(velocity, v0))
                if all(fit.observation_valid) and isfinite(log_weight):
                    draws.append((index, log_weight, params))
                    sampling["finite_weights"] += 1
                else:
                    reason = "observation_domain" if not all(fit.observation_valid) else "zero_likelihood"
                    sampling["rejected"][reason] = sampling["rejected"].get(reason, 0) + 1
            for (index, _, params), weight in zip(draws, normalize(draws)):
                yield index, weight, predict(model, case, params)
            return
        if model == "B0" and width:
            bounds = []
            for axis in range(3):
                centers = [(q[axis] - case.initial[axis]
                            + (0.5 * case.gravity * t*t if axis == 2 else 0), t)
                           for q, t in zip(case.observations, case.times)]
                lower = max((q - width/2) / t for q, t in centers)
                upper = min((q + width/2) / t for q, t in centers)
                if lower >= upper:
                    raise RuntimeError("No B0 velocity satisfies both rounding cells")
                bounds.append((lower, upper))
        for index in range(budget):
            sampling["attempted"] += 1
            sampling["finite_weights"] += 1
            if model == "B0":
                velocity = (tuple(rng.uniform(lo, hi) for lo, hi in bounds) if width
                            else tuple(rng.gauss(v, sigma / time_scale) for v in v0))
                params = {"v0": velocity}
            else:
                params = {"frame_centers": tuple(
                    tuple(rng.gauss(q + rng.uniform(-width / 2, width / 2), sigma)
                          for q in point) for point in case.observations)}
            yield index, 1 / budget, predict(model, case, params)
        return
    curve = settings.get("curve") if model == "M3" else None
    if model == "M3" and curve is None:
        raise RuntimeError("M3 curve missing from scenario registry")
    draws, _, _ = sample(case, sigma, budget, seed, model, curve, width,
                         settings.get("drag_mean", .27), settings.get("transverse_sigma", .22), sampling)
    require_finite_draws(draws, sampling)
    for (index, _, params), weight in zip(draws, normalize(draws)):
        yield index, weight, predict(model, case, params)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", type=Path)
    parser.add_argument("scenarios", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--models", nargs="+", choices=("B0", "B1", "B2", "M1", "M2", "M3"),
                        default=("B0", "B1", "B2", "M1", "M2", "M3"))
    parser.add_argument("--draws", type=int, default=4000)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    if args.draws < 1 or args.workers < 1 or len(set(args.models)) != len(args.models):
        parser.error("Require a positive budget and unique models.")
    registry = json.loads(args.scenarios.read_text(encoding="utf-8"))
    with args.cases.open(encoding="utf-8", newline="") as stream:
        cases = list(csv.DictReader(stream))
    ids = [row["case_id"] for row in cases]
    if not ids or len(set(ids)) != len(ids) or any(not key for key in ids):
        parser.error("Require nonempty unique case IDs.")
    base = load_case()
    inputs = []
    for row in cases:
        scenario = row["scenario_id"]
        settings = registry[scenario]
        unsupported = settings.keys() - {
            "sigma_m", "rounding_width_m", "curve", "drag_mean", "transverse_sigma", "wind_m_s"
        }
        if unsupported:
            parser.error(f"Unsupported settings in {scenario}: {sorted(unsupported)}")
        case = replace(base, times=tuple(float(row[f"t{i}_s"]) for i in (1, 2)),
                       observations=tuple(tuple(float(row[f"{axis}{i}_m"]) for axis in "xyz")
                                          for i in (1, 2)),
                       wind=tuple(settings.get("wind_m_s", base.wind)))
        if not 0 < case.times[0] < case.times[1] or not all(
            isfinite(q) for point in case.observations for q in point
        ) or not all(map(isfinite, case.times)):
            parser.error(f"Invalid observation times or coordinates for {row['case_id']}")
        inputs.append((row["case_id"], scenario, settings, case))
    if any((args.output / name).exists() for name in ("predictions.csv", "diagnostics.json")):
        parser.error("Choose an unused output directory; existing prediction artifacts are immutable.")
    args.output.mkdir(parents=True, exist_ok=True)
    diagnostics = []
    jobs = [(*row, model, args.draws, args.seed) for row in inputs for model in args.models]
    with ProcessPoolExecutor(args.workers) as pool, (args.output / "predictions.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        # Submit bounded batches on every supported Python version (3.10+).
        results = (result for start in range(0, len(jobs), 2 * args.workers)
                   for result in pool.map(forecast_group, jobs[start:start + 2 * args.workers]))
        for key, draws, diagnostic in results:
            diagnostics.append(diagnostic)
            for draw_id, weight, event in draws:
                record = asdict(event)
                if event.clearance_goal is not None:
                    record["clearance_goal"] = int(event.clearance_goal)
                writer.writerow(dict(**key, draw_id=draw_id, weight=weight, **record))
    manifest = dict(cases_sha256=hashlib.sha256(args.cases.read_bytes()).hexdigest(),
                    scenario_sha256=hashlib.sha256(args.scenarios.read_bytes()).hexdigest(),
                    seed=args.seed, diagnostics=diagnostics, python=platform.python_version(),
                    inference_version="wp2-revision-2-exploratory", models=args.models,
                    draw_budget=args.draws, solver_config=asdict(SolverConfig()),
                    source_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in Path(__file__).parent.glob('*.py')})
    (args.output / "diagnostics.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
