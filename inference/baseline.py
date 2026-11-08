"""Generate public-case Gaussian baseline predictions using WP1."""

import argparse
import csv
from dataclasses import asdict
import json
from math import fsum, sqrt
from pathlib import Path
from random import Random

from physics import EventResult, load_case, solve
from .likelihood import gaussian_log_likelihood, rounded_log_likelihood


CASE_PATH = Path(__file__).resolve().parents[1] / "spec" / "case.json"
MODELS = ("B0", "B1", "B2")
SCENARIOS = ("gaussian-10mm", "rounding-10mm", "gaussian-10mm-rounded-10mm")


def ballistic_fit(case):
    sum_t2 = fsum(t * t for t in case.times)
    velocity = tuple(
        fsum(t * (point[axis] - case.initial[axis]
                  + (0.5 * case.gravity * t * t if axis == 2 else 0))
             for t, point in zip(case.times, case.observations)) / sum_t2
        for axis in range(3)
    )
    return velocity, sqrt(sum_t2)


def predict(model, case, parameters):
    result = solve(model, case, parameters)
    if result.event.event == "NUMERICAL_FAILURE" or all(result.observation_valid):
        return result.event
    return EventResult("NUMERICAL_FAILURE", reason="not_airborne_through_observations")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--draws", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--scenario", choices=SCENARIOS, default=SCENARIOS[0])
    args = parser.parse_args()
    if args.draws < 1:
        parser.error("--draws must be positive")

    data = json.loads(CASE_PATH.read_text(encoding="utf-8"))
    case = load_case(CASE_PATH)
    sigma = data["nominal_assumptions"]["gaussian_coordinate_sigma_m"]
    rounded = args.scenario != SCENARIOS[0]
    width = data["protocol_defaults"]["rounding_bin_width_m"] if rounded else 0.0
    if args.scenario == SCENARIOS[1]:
        sigma = 0.0
    models = MODELS[1:] if rounded else MODELS
    rng = Random(args.seed)
    velocity, time_scale = ballistic_fit(case)
    b1 = solve("B1", case)
    args.output.mkdir(parents=True, exist_ok=True)
    counts = {model: {} for model in models}
    fields = ["case_id", "model_id", "scenario_id", "draw_id", "weight",
              "event", "t_s", "y_m", "z_m", "clearance_goal", "reason"]
    with (args.output / "predictions.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for draw in range(args.draws):
            parameters = {}
            if not rounded:
                parameters["B0"] = {"v0": tuple(rng.gauss(v, sigma / time_scale) for v in velocity)}
            frames = tuple(tuple(
                rng.gauss(q + rng.uniform(-width / 2, width / 2), sigma)
                if rounded else rng.gauss(q, sigma)
                for q in point)
                           for point in case.observations)
            for model in models:
                event = predict(model, case, parameters.get(model, {"frame_centers": frames}))
                row = asdict(event)
                if event.clearance_goal is not None:
                    row["clearance_goal"] = int(event.clearance_goal)
                writer.writerow(dict(case_id=data["case_id"], model_id=model,
                                     scenario_id=args.scenario, draw_id=draw,
                                     weight=1 / args.draws, **row))
                tally = counts[model]
                tally[event.event] = tally.get(event.event, 0) + 1

    diagnostics = {
        "case_schema_version": data["schema_version"], "scenario_id": args.scenario,
        "sigma_m": sigma, "seed": args.seed, "draws_per_model": args.draws,
        "rounding_width_m": width,
        "model_interface_revision": "e25b682",
        "reference_prior": {model: "flat velocity" if model == "B0"
                            else "flat latent frame coordinates" for model in models},
        "event_counts": counts,
        "b1_point_event": asdict(b1.event),
    }
    if rounded:
        diagnostics["b1_point_log_likelihood"] = rounded_log_likelihood(
            case.observations, b1.observations, width, sigma
        )
    else:
        b0 = solve("B0", case, {"v0": velocity})
        diagnostics["b0_velocity_m_s"] = velocity
        diagnostics["b0_log_likelihood"] = gaussian_log_likelihood(
            case.observations, b0.observations, sigma
        )
    (args.output / "diagnostics.json").write_text(
        json.dumps(diagnostics, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
