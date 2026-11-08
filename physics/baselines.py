"""Analytic time- and distance-domain baselines for Problem B."""

import math
from collections.abc import Mapping

from .contracts import (
    Case,
    EventResult,
    ForwardResult,
    SolverConfig,
    TracePoint,
    classify_plane,
)


def _vector(value, name):
    if isinstance(value, (str, bytes, Mapping)):
        raise ValueError(f"{name} must contain three finite coordinates")
    try:
        vector = tuple(float(component) for component in value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must contain three finite coordinates") from exc
    if len(vector) != 3 or not all(math.isfinite(component) for component in vector):
        raise ValueError(f"{name} must contain three finite coordinates")
    return vector


def _frame_centers(case, parameters):
    centers = parameters.get("frame_centers", case.observations)
    try:
        first, second = centers
    except (TypeError, ValueError) as exc:
        raise ValueError("frame_centers must contain exactly two points") from exc
    return _vector(first, "frame_centers[0]"), _vector(second, "frame_centers[1]")


def _directional_root(a, b, c, direction):
    """Solve a*s**2 + b*s + c = 0 for a strict crossing of the given sign."""
    if not all(math.isfinite(value) for value in (a, b, c)):
        raise ValueError("nonfinite polynomial coefficients")
    if a == 0.0:
        return -c / b if direction * b > 0.0 else None

    discriminant = b * b - (4.0 * a) * c
    if not math.isfinite(discriminant):
        scale = max(abs(a), abs(b), abs(c))
        return _directional_root(a / scale, b / scale, c / scale, direction)
    if discriminant <= 0.0:
        return None

    # The two roots have opposite derivative signs. Choose the requested
    # derivative and rationalize the numerator if it would subtract.
    signed_sqrt = direction * math.sqrt(discriminant)
    if direction * b > 0.0:
        return -c / (0.5 * b + 0.5 * signed_sqrt)
    return (-0.5 * b + 0.5 * signed_sqrt) / a


def _ground_root(a, b, height):
    if height < 0.0 or (height == 0.0 and (b < 0.0 or (b == 0.0 and a < 0.0))):
        return 0.0
    root = _directional_root(a, b, height, -1)
    return root if root is not None and 0.0 < root else math.inf


def _at_or_before(value, endpoint):
    return value <= endpoint or value - endpoint <= 4 * math.ulp(endpoint)


def _position(initial, velocity, acceleration, time):
    result = tuple(
        origin + time * (speed + 0.5 * time * rate)
        for origin, speed, rate in zip(initial, velocity, acceleration)
    )
    if not all(math.isfinite(coordinate) for coordinate in result):
        raise ValueError("baseline position is nonfinite")
    return result


def _time_parameters(model_id, case, parameters):
    first_time, second_time = case.times
    if not (math.isfinite(second_time) and 0.0 < first_time < second_time):
        raise ValueError("observation times must be finite, positive and increasing")
    if model_id == "B0":
        if parameters.keys() - {"v0"}:
            raise ValueError("B0 accepts only v0")
        gravity = (0.0, 0.0, -case.gravity)
        if "v0" in parameters:
            return _vector(parameters["v0"], "v0"), gravity
        denominator = first_time * first_time + second_time * second_time
        velocity = tuple(
            sum(
                time * (frame[axis] - origin - 0.5 * gravity[axis] * time * time)
                for time, frame in zip(case.times, case.observations)
            ) / denominator
            for axis, origin in enumerate(case.initial)
        )
        return _vector(velocity, "fitted v0"), gravity

    if "v0" in parameters or "a0" in parameters:
        if parameters.keys() != {"v0", "a0"}:
            raise ValueError("B1 requires both v0 and a0, or frame_centers alone")
        return _vector(parameters["v0"], "v0"), _vector(parameters["a0"], "a0")
    if parameters.keys() - {"frame_centers"}:
        raise ValueError("B1 accepts frame_centers or the v0 and a0 pair")
    first, second = _frame_centers(case, parameters)
    first_rate = tuple((coordinate - origin) / first_time for coordinate, origin in zip(first, case.initial))
    second_rate = tuple((coordinate - origin) / second_time for coordinate, origin in zip(second, case.initial))
    acceleration = tuple(2.0 * (rate2 - rate1) / (second_time - first_time) for rate1, rate2 in zip(first_rate, second_rate))
    velocity = tuple(rate - 0.5 * first_time * change for rate, change in zip(first_rate, acceleration))
    return _vector(velocity, "fitted v0"), _vector(acceleration, "fitted a0")


def _solve_time(model_id, case, parameters, config, include_trace):
    velocity, acceleration = _time_parameters(model_id, case, parameters)
    ground = _ground_root(0.5 * acceleration[2], velocity[2], case.initial[2] - case.radius)
    forward = _directional_root(0.5 * acceleration[0], velocity[0], case.initial[0] - case.goal_x, 1)
    plane = forward if forward is not None and 0.0 < forward <= config.horizon_s else math.inf

    if ground <= config.horizon_s and ground - plane <= config.tie_tolerance_s:
        endpoint = ground
        event = EventResult("GROUND_FIRST", t_s=ground)
    elif math.isfinite(plane):
        endpoint = plane
        _, y, z = _position(case.initial, velocity, acceleration, plane)
        event = classify_plane(case, plane, y, z)
    else:
        endpoint = config.horizon_s
        event = EventResult("NO_REACH", reason="no event within the time horizon")

    observations = tuple(_position(case.initial, velocity, acceleration, time) for time in case.times)
    valid = tuple(_at_or_before(time, endpoint) for time in case.times)
    trace = ()
    if include_trace:
        steps = math.ceil(endpoint / config.max_step_s)
        samples = {index * config.max_step_s for index in range(steps)}
        samples.update(time for time in case.times if time <= endpoint)
        samples.update((0.0, endpoint))
        trace = tuple(
            TracePoint(
                time,
                *_position(case.initial, velocity, acceleration, time),
                *(speed + time * rate for speed, rate in zip(velocity, acceleration)),
            )
            for time in sorted(samples)
        )
    return ForwardResult(observations, valid, event, trace)


def _spatial_polynomial(origin, first, second, s1, s2):
    first_slope = (first - origin) / s1
    quadratic = ((second - first) / (s2 - s1) - first_slope) / s2
    return quadratic, first_slope - s1 * quadratic


def _solve_spatial(case, parameters, config, include_trace):
    if parameters.keys() - {"frame_centers"}:
        raise ValueError("B2 accepts only frame_centers")
    first, second = _frame_centers(case, parameters)
    x0, y0, z0 = case.initial
    s1, s2 = first[0] - x0, second[0] - x0
    spacing_scale = max(abs(s1), abs(s2))
    if not (s1 > 8 * math.ulp(spacing_scale) and s2 - s1 > 8 * math.ulp(spacing_scale)):
        raise ValueError("B2 requires strictly increasing, distinct spatial knots")
    ay, by = _spatial_polynomial(y0, first[1], second[1], s1, s2)
    az, bz = _spatial_polynomial(z0, first[2], second[2], s1, s2)
    if not all(math.isfinite(value) for value in (ay, by, az, bz)):
        raise ValueError("B2 polynomial coefficients are nonfinite")

    # A supplied latent frame contributes its own x knot. B2 has no time law.
    def position(distance):
        result = x0 + distance, y0 + distance * (by + distance * ay), z0 + distance * (bz + distance * az)
        return _vector(result, "B2 position")

    plane = case.goal_x - x0
    ground = _ground_root(az, bz, z0 - case.radius)
    if plane <= 0.0:
        endpoint = 0.0
        event = EventResult("NO_REACH", reason="goal plane is not ahead in the spatial model")
    elif ground - plane <= config.spatial_tie_tolerance_m:
        endpoint = ground
        event = EventResult("GROUND_FIRST")
    else:
        endpoint = plane
        _, y, z = position(plane)
        event = classify_plane(case, None, y, z)

    trace = ()
    if include_trace:
        samples = {endpoint * index / 32 for index in range(33)}
        samples.update(distance for distance in (s1, s2) if distance <= endpoint)
        trace = tuple(TracePoint(None, *position(distance)) for distance in sorted(samples))
    valid = _at_or_before(s1, endpoint), _at_or_before(s2, endpoint)
    return ForwardResult((position(s1), position(s2)), valid, event, trace)


def solve_baseline(model_id, case: Case, parameters: Mapping, config: SolverConfig, include_trace: bool) -> ForwardResult:
    """Evaluate B0, B1 or B2 using the common first-event contract."""
    if model_id == "B2":
        return _solve_spatial(case, parameters, config, include_trace)
    if model_id in {"B0", "B1"}:
        return _solve_time(model_id, case, parameters, config, include_trace)
    raise ValueError(f"unsupported baseline model {model_id!r}")
