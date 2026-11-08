"""Public WP1 forward interface. Uses only the Python standard library."""

from collections.abc import Mapping
from dataclasses import replace
from math import isfinite

from .contracts import Case, EventResult, ForwardResult, SolverConfig, TracePoint, load_case

__all__ = ["Case", "EventResult", "ForwardResult", "SolverConfig", "TracePoint", "load_case", "solve"]


def _check_inputs(case, config, parameters):
    vectors = (case.initial, case.wind, *case.observations)
    if len(case.observations) != 2 or any(len(v) != 3 or not all(map(isfinite, v)) for v in vectors):
        raise ValueError("Expected finite three-dimensional positions and wind.")
    if len(case.times) != 2 or not all(map(isfinite, case.times)) or not 0 < case.times[0] < case.times[1]:
        raise ValueError("Expected two distinct, positive observation times in ascending order.")
    values = (case.goal_x, case.y_min, case.y_max, case.z_min, case.z_max,
              case.radius, case.mass, case.density, case.gravity)
    if not all(map(isfinite, values)) or not case.y_min < case.y_max or not case.z_min < case.z_max:
        raise ValueError("Expected finite geometry with ordered goal bounds.")
    if case.radius <= 0 or case.mass <= 0 or case.density < 0 or case.gravity < 0:
        raise ValueError("Expected positive radius/mass and nonnegative density/gravity.")
    settings = (config.max_step_s, config.horizon_s, config.tie_tolerance_s,
                config.spatial_tie_tolerance_m, config.root_tolerance_s)
    if (
        not all(map(isfinite, settings))
        or not 0 < config.root_tolerance_s <= config.max_step_s
        or config.horizon_s <= 0 or config.tie_tolerance_s < 0 or config.spatial_tie_tolerance_m < 0
    ):
        raise ValueError("Invalid integration step, horizon or event tolerance.")
    if not isinstance(parameters, Mapping):
        raise ValueError("parameters must be a mapping.")


def solve(model_id, case, parameters=None, config=None, *, include_trace=False):
    """Evaluate the two model positions and the first physical event."""
    parameters = {} if parameters is None else parameters
    curve_domains = set()
    try:
        if config is None:
            config = SolverConfig(
                horizon_s=case.horizon_s,
                tie_tolerance_s=case.tie_tolerance_s,
                spatial_tie_tolerance_m=case.spatial_tie_tolerance_m,
            )
        _check_inputs(case, config, parameters)
        if model_id in ("B0", "B1", "B2"):
            from .baselines import solve_baseline

            return solve_baseline(model_id, case, parameters, config, include_trace)
        if model_id in ("M1", "M2", "M3"):
            from .aerodynamics import build_aerodynamics
            from .integration import solve_flight

            velocity = tuple(float(value) for value in parameters["v0"])
            if len(velocity) != 3 or not all(map(isfinite, velocity)):
                raise ValueError("v0 must be a finite three-component velocity.")
            aero = build_aerodynamics(model_id, case, parameters, config)
            def tracked_aero(velocity):
                result = aero(velocity)
                if result[4] is not None:
                    curve_domains.add(result[4])
                return result

            # Include anchor-domain evaluations as well as integration stages.
            curve_domains.update(aero.curve_domains)
            result = solve_flight(case, config, velocity, tracked_aero, include_trace)
            return replace(result, curve_domains=tuple(sorted(curve_domains)))
        raise ValueError(f"Unknown model ID: {model_id!r}.")
    except (ValueError, TypeError, KeyError, ArithmeticError) as error:
        reason = f"{type(error).__name__}: {error}"
        return ForwardResult(None, (False, False), EventResult("NUMERICAL_FAILURE", reason=reason),
                             curve_domains=tuple(sorted(curve_domains)))
