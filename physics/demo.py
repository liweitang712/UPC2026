"""Export deterministic public-case traces and numerical checks for WP2/F1."""

import argparse
import csv
from dataclasses import asdict, fields, replace
import json
from pathlib import Path

from . import SolverConfig, TracePoint, load_case, solve
from .aerodynamics import REGISTERED_CURVES
from .contracts import DEFAULT_CASE


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "physics" / "examples" / "public_case"
LEGACY_FIT = ROOT / "reference" / "penalty" / "penalty_results.json"


def demo_models():
    legacy = json.loads(LEGACY_FIT.read_text(encoding="utf-8"))
    vx, vy, vz, cd, cy, cz = legacy["scenarios"]["0.010"]["local_fit_vx_vy_vz_cd_cy_cz"]
    velocity = (vx, vy, vz)
    for model_id in ("B0", "B1", "B2"):
        yield model_id, "point_observations", {}
    yield "M1", "fixed_legacy_parameters", {"v0": velocity, "cd": cd}
    yield "M2", "fixed_legacy_parameters", {"v0": velocity, "cd": cd, "cy": cy, "cz": cz}
    for curve in REGISTERED_CURVES:
        yield "M3", curve, {
            "v0": velocity, "cd_anchor": cd, "cy": cy, "cz": cz,
            "reference_speed_m_s": 30.0, "curve": curve, "curve_policy": "error",
        }


def export(output):
    case = load_case()
    tolerances = json.loads(DEFAULT_CASE.read_text(encoding="utf-8"))["protocol_defaults"]
    config = SolverConfig(
        horizon_s=case.horizon_s, tie_tolerance_s=case.tie_tolerance_s,
        spatial_tie_tolerance_m=case.spatial_tie_tolerance_m,
    )
    finer = replace(config, max_step_s=config.max_step_s / 2)
    output.mkdir(parents=True, exist_ok=True)
    summary = {
        "case_id": "upc2026-b",
        "purpose": "Deterministic WP1 interface and F1 data. No posterior or blind scoring.",
        "parameter_source": "reference/penalty/penalty_results.json, scenarios.0.010.local_fit_vx_vy_vz_cd_cy_cz",
        "observed_frames": [{"t_s": t, "xyz_m": xyz} for t, xyz in zip(case.times, case.observations)],
        "solver": asdict(config),
        "refinement_max_step_s": finer.max_step_s,
        "results": [],
    }
    columns = ["model_id", "scenario_id", *[field.name for field in fields(TracePoint)]]
    with (output / "traces.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        for model_id, scenario_id, parameters in demo_models():
            result = solve(model_id, case, parameters, config, include_trace=True)
            refined = solve(model_id, case, parameters, finer)
            event = result.event
            if event.event == "NUMERICAL_FAILURE" or refined.event.event != event.event:
                raise RuntimeError(f"{model_id}/{scenario_id}: {event.reason or 'event changed on refinement'}")
            for point in result.trace:
                writer.writerow({"model_id": model_id, "scenario_id": scenario_id, **asdict(point)})
            row = {
                "model_id": model_id, "scenario_id": scenario_id, "parameters": parameters,
                "modeled_frames_m": result.observations, "observation_valid": result.observation_valid,
                "event": asdict(event),
            }
            if event.y_m is not None:
                difference = [
                    abs(event.y_m - refined.event.y_m), abs(event.z_m - refined.event.z_m),
                ]
                if max(difference) > tolerances["event_position_convergence_target_m"]:
                    raise RuntimeError(f"{model_id}/{scenario_id}: crossing position failed refinement")
                row["refinement_plane_delta_m"] = difference
            if event.t_s is not None:
                difference = abs(event.t_s - refined.event.t_s)
                if difference > tolerances["event_time_convergence_target_s"]:
                    raise RuntimeError(f"{model_id}/{scenario_id}: event time failed refinement")
                row["refinement_time_delta_s"] = difference
            reynolds = [p.reynolds for p in result.trace if p.reynolds is not None]
            if reynolds:
                row["sampled_reynolds_range"] = [min(reynolds), max(reynolds)]
                row["curve_domains"] = sorted({p.curve_domain for p in result.trace})
            summary["results"].append(row)
            print(f"{model_id:2} {scenario_id:25} {event.event:12} {event.t_s} {event.y_m} {event.z_m}")
    (output / "events.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    export(parser.parse_args().output)
