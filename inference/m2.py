"""Importance sampling for public M1–M3 refits."""

import argparse
from bisect import bisect_right
from collections import Counter
import csv
from dataclasses import asdict, replace
import hashlib
import json
from math import exp, fsum, isfinite, sqrt
from pathlib import Path
from random import Random

from physics import SolverConfig, load_case, solve
from .baseline import CASE_PATH, ballistic_fit, predict
from .likelihood import gaussian_log_likelihood, rounded_log_likelihood


def aerodynamics(rng, model, lower, drag_mean, transverse_sigma):
    cd = rng.gauss(drag_mean, 0.14)
    while not lower < cd < 0.55:
        cd = rng.gauss(drag_mean, 0.14)
    if model == "M1":
        return {"cd": cd}
    cy, cz = rng.gauss(0, transverse_sigma), rng.gauss(0, transverse_sigma)
    while cy * cy + cz * cz >= 0.55**2:
        cy, cz = rng.gauss(0, transverse_sigma), rng.gauss(0, transverse_sigma)
    return {"cd": cd, "cy": cy, "cz": cz}


def sample(case, sigma, budget, seed, model, curve, width, drag_mean, transverse_sigma):
    rng = Random(seed)
    initial, time_scale = ballistic_fit(case)
    config = SolverConfig(horizon_s=case.times[-1])
    proposal_sigma = 1.25 * sqrt(sigma**2 + width**2 / 12) / time_scale
    lower = 0.08
    if curve:
        from physics import aerodynamics as wp1_aero

        if curve not in wp1_aero.REGISTERED_CURVES:
            raise ValueError(f"Unknown registered M3 curve: {curve}")
        path = Path(wp1_aero.__file__).with_name("curves") / f"{curve}.json"
        knots = json.loads(path.read_text(encoding="utf-8"))
        reference_re = case.density * 2 * case.radius * 30 / 1.81e-5
        reynolds, drag = knots["reynolds"], knots["cd"]
        if not reynolds[0] <= reference_re <= reynolds[-1]:
            raise ValueError("Reference speed lies outside the experimental curve.")
        i = min(bisect_right(reynolds, reference_re) - 1, len(reynolds) - 2)
        fraction = (reference_re - reynolds[i]) / (reynolds[i + 1] - reynolds[i])
        reference_cd = drag[i] + fraction * (drag[i + 1] - drag[i])
        lower = max(lower, reference_cd - min(drag))
        if lower >= 0.55:
            raise ValueError("No admissible drag anchor in the reference prior.")
    draws = []
    rejected = {"velocity_prior": 0, "observation_domain": 0, "zero_likelihood": 0}
    for draw_id in range(budget):
        parameters = aerodynamics(rng, model, lower, drag_mean, transverse_sigma)
        if curve:
            parameters.update(cd_anchor=parameters.pop("cd"), curve=curve, reference_speed_m_s=30)
        center = initial
        for _ in range(3):
            result = solve(model, case, dict(parameters, v0=center), config)
            if result.observations is None or any(p is None for p in result.observations):
                break
            center = tuple(
                center[k] + fsum(t * (q[k] - mu[k])
                                for t, q, mu in zip(case.times, case.observations, result.observations))
                / time_scale**2 for k in range(3)
            )
        velocity = tuple(rng.gauss(v, proposal_sigma) for v in center)
        vx, vy, vz = velocity
        if not (8 < vx < 48 and -20 < vy < 20 and 0 < vz < 20):
            rejected["velocity_prior"] += 1
            continue
        parameters["v0"] = velocity
        result = solve(model, case, parameters, config)
        if result.event.event == "NUMERICAL_FAILURE":
            raise RuntimeError(f"Likelihood solver failure for proposal {draw_id}: {result.event.reason}")
        if not all(result.observation_valid):
            rejected["observation_domain"] += 1
            continue
        # The aerodynamic prior cancels its proposal density. The velocity
        # prior density is constant inside support and cancels in normalization.
        log_weight = (rounded_log_likelihood(case.observations, result.observations, width, sigma)
                      if width else gaussian_log_likelihood(case.observations, result.observations, sigma))
        if not isfinite(log_weight):
            rejected["zero_likelihood"] += 1
            continue
        log_weight += 0.5 * fsum(((v - m) / proposal_sigma)**2 for v, m in zip(velocity, center))
        draws.append((draw_id, log_weight, parameters))
    return draws, rejected, lower


def normalize(draws):
    if not draws:
        raise RuntimeError("No proposals with finite posterior weight.")
    peak = max(log_weight for _, log_weight, _ in draws)
    weights = [exp(log_weight - peak) for _, log_weight, _ in draws]
    total = fsum(weights)
    return [w / total for w in weights]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--draws", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--model", choices=("M1", "M2", "M3"), default="M2")
    parser.add_argument("--curve", choices=("goff2026_trionda_b", "goff2026_jabulani_b"))
    parser.add_argument("--sigma-mm", type=float, default=10)
    parser.add_argument("--rounded", action="store_true")
    parser.add_argument("--wind-y", type=float, default=0)
    parser.add_argument("--drag-mean", type=float, default=0.27)
    parser.add_argument("--transverse-sigma", type=float, default=0.22)
    parser.add_argument("--scenario", default="gaussian-10mm")
    parser.add_argument("--wp1-revision", default="02b67b2")
    args = parser.parse_args()
    if (args.draws < 1 or not isfinite(args.sigma_mm) or args.sigma_mm < 0
            or (args.sigma_mm == 0 and not args.rounded)
            or not isfinite(args.transverse_sigma) or args.transverse_sigma <= 0):
        parser.error("Require a positive budget and valid observation and prior scales")
    if (args.model == "M3") != bool(args.curve):
        parser.error("Specify a curve exactly when using M3")
    raw = CASE_PATH.read_bytes()
    data = json.loads(raw)
    case = load_case(CASE_PATH)
    case = replace(case, wind=(case.wind[0], args.wind_y, case.wind[2]))
    sigma = args.sigma_mm / 1000
    width = data["protocol_defaults"]["rounding_bin_width_m"] if args.rounded else 0
    draws, rejected, lower = sample(case, sigma, args.draws, args.seed, args.model,
                                    args.curve, width, args.drag_mean, args.transverse_sigma)
    weights = normalize(draws)

    args.output.mkdir(parents=True, exist_ok=True)
    rows = []
    fields = ["case_id", "model_id", "scenario_id", "draw_id", "weight",
              "event", "t_s", "y_m", "z_m", "clearance_goal", "reason"]
    with (args.output / "predictions.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for (draw_id, _, parameters), weight in zip(draws, weights):
            event = predict(args.model, case, parameters)
            rows.append((event, weight))
            row = asdict(event)
            if event.clearance_goal is not None:
                row["clearance_goal"] = int(event.clearance_goal)
            writer.writerow(dict(case_id=data["case_id"], model_id=args.model,
                                 scenario_id=args.scenario, draw_id=draw_id,
                                 weight=weight, **row))
    planes = sorted((e.t_s, w) for e, w in rows if e.event.startswith("PLANE_"))
    reach = fsum(w for _, w in planes)
    cumulative = 0.0
    median_time = None
    for time, weight in planes:
        cumulative += weight
        if cumulative >= reach / 2:
            median_time = time
            break
    diagnostics = {
        "wp1_revision": args.wp1_revision, "case_sha256": hashlib.sha256(raw).hexdigest(),
        "model_id": args.model, "scenario_id": args.scenario, "sigma_m": sigma,
        "rounding_width_m": width, "curve": args.curve, "wind_m_s": case.wind,
        "drag_mean": args.drag_mean, "drag_support": [lower, 0.55],
        "transverse_sigma": args.transverse_sigma if args.model != "M1" else None,
        "seed": args.seed, "attempted": args.draws, "finite_weights": len(draws),
        "rejected": rejected, "ess": 1 / fsum(w * w for w in weights),
        "max_weight": max(weights), "p_reach": reach,
        "solver_config": asdict(SolverConfig()),
        "failure_reasons": dict(Counter(e.reason for e, _ in rows if e.event == "NUMERICAL_FAILURE")),
        "p_goal": fsum(w for e, w in rows if e.event == "PLANE_GOAL"),
        "p_clearance_goal": fsum(w for e, w in rows if e.clearance_goal),
        "p_failure": fsum(w for e, w in rows if e.event == "NUMERICAL_FAILURE"),
        "median_time_given_reach_s": median_time,
    }
    (args.output / "diagnostics.json").write_text(
        json.dumps(diagnostics, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(diagnostics, indent=2))


if __name__ == "__main__":
    main()
