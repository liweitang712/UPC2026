"""Fixed-step RK4 flight integration and direction-aware first events."""

from math import isfinite, sqrt

from .contracts import EventResult, ForwardResult, TracePoint, classify_plane


def rk4(state, step, acceleration):
    """Advance the coupled position and velocity in SI units."""
    def derivative(values):
        velocity = values[3:]
        return velocity + acceleration(velocity)[0]

    k1 = derivative(state)
    k2 = derivative(tuple(value + step * slope / 2 for value, slope in zip(state, k1)))
    k3 = derivative(tuple(value + step * slope / 2 for value, slope in zip(state, k2)))
    k4 = derivative(tuple(value + step * slope for value, slope in zip(state, k3)))
    result = tuple(
        value + step * (first + 2 * second + 2 * third + fourth) / 6
        for value, first, second, third, fourth in zip(state, k1, k2, k3, k4)
    )
    if not all(map(isfinite, result)):
        raise ValueError("Integration produced a nonfinite state.")
    return result


def cubic(left, right, v_left, v_right, step, level=0.0):
    """Cubic Hermite coefficients in normalized step time."""
    displacement = right - left
    return (
        step * (v_left + v_right) - 2 * displacement,
        3 * displacement - step * (2 * v_left + v_right),
        step * v_left,
        left - level,
    )


def value(coefficients, fraction):
    a, b, c, d = coefficients
    return ((a * fraction + b) * fraction + c) * fraction + d


def slope(coefficients, fraction):
    a, b, c, _ = coefficients
    return (3 * a * fraction + 2 * b) * fraction + c


def turning_points(coefficients):
    a, b, c, _ = coefficients
    a, b = 3 * a, 2 * b
    if a == 0:
        roots = (-c / b,) if b else ()
    else:
        discriminant = b * b - 4 * a * c
        if discriminant < 0:
            return []
        radical = sqrt(discriminant)
        q = -(b + (radical if b >= 0 else -radical)) / 2
        roots = (q / a, c / q) if q else (0.0,)
    return sorted({root for root in roots if 0 < root < 1})


def directed_root(left, right, axis, level, direction, step, config):
    coefficients = cubic(left[axis], right[axis], left[axis + 3], right[axis + 3], step, level)
    cuts = [0.0, *turning_points(coefficients), 1.0]
    for start, end in zip(cuts, cuts[1:]):
        lo = direction * (left[axis] - level if start == 0 else value(coefficients, start))
        hi = direction * (right[axis] - level if end == 1 else value(coefficients, end))
        if lo > 0 or hi < 0 or lo == hi:
            continue
        if lo == 0:
            root = start
        elif hi == 0:
            root = end
        else:
            while (end - start) * step > config.root_tolerance_s:
                middle = (start + end) / 2
                if direction * value(coefficients, middle) < 0:
                    start = middle
                else:
                    end = middle
            root = (start + end) / 2
        # An extremum at the boundary is a touch, not a directed crossing.
        if direction * slope(coefficients, root) / step > 1e-10:
            return root * step
    return None


def interpolate(left, right, step, delta):
    fraction = delta / step
    polynomials = [
        cubic(left[axis], right[axis], left[axis + 3], right[axis + 3], step)
        for axis in range(3)
    ]
    return tuple(value(p, fraction) for p in polynomials) + tuple(slope(p, fraction) / step for p in polynomials)


def first_in_step(case, config, acceleration, time, step, left, right):
    plane = directed_root(left, right, 0, case.goal_x, 1, step, config)
    ground = directed_root(left, right, 2, case.radius, -1, step, config)
    if plane is not None and ground is None:
        # A plane root near the step boundary can tie a ground root in the next step.
        extra = min(time + plane + config.tie_tolerance_s, config.horizon_s) - (time + step)
        if extra > 0:
            future = rk4(right, extra, acceleration)
            later = directed_root(right, future, 2, case.radius, -1, extra, config)
            if later is not None:
                contact = interpolate(right, future, extra, later)
                return EventResult("GROUND_FIRST", time + step + later), contact
    if ground is not None and (plane is None or ground <= plane + config.tie_tolerance_s):
        contact = interpolate(left, right, step, ground)
        return EventResult("GROUND_FIRST", time + ground), contact
    if plane is not None:
        crossing = interpolate(left, right, step, plane)
        return classify_plane(case, time + plane, crossing[1], crossing[2]), crossing
    return None


def trace_point(time, state, acceleration):
    _, speed, reynolds, coefficient, domain = acceleration(state[3:])
    return TracePoint(time, *state, speed, reynolds, coefficient, domain)


def solve_flight(case, config, initial_velocity, acceleration, include_trace):
    time = 0.0
    state = case.initial + initial_velocity
    trace = [trace_point(time, state, acceleration)] if include_trace else []
    event = None
    if state[2] < case.radius or (
        state[2] == case.radius
        and (state[5] < 0 or (state[5] == 0 and acceleration(initial_velocity)[0][2] < 0))
    ):
        event = EventResult("GROUND_FIRST", 0.0, reason="initial_ground_contact")

    observations = [None, None]
    valid = [False, False]
    checkpoints = sorted(set((*case.times, config.horizon_s)))
    for target in checkpoints:
        if target > config.horizon_s and event is None:
            event = EventResult("NO_REACH", reason="horizon")
        while time < target:
            next_time = min(time + config.max_step_s, target)
            if next_time <= time:
                raise ValueError("Step size cannot advance the clock.")
            step = next_time - time
            try:
                updated = rk4(state, step, acceleration)
            except (ValueError, ArithmeticError):
                if event is not None:
                    # Mathematical continuation past a terminal event is optional.
                    return ForwardResult(tuple(observations), tuple(valid), event, tuple(trace))
                raise
            if event is None:
                terminal = first_in_step(case, config, acceleration, time, step, state, updated)
                if terminal is not None:
                    event, event_state = terminal
                    if include_trace:
                        if event.t_s > next_time:
                            trace.append(trace_point(next_time, updated, acceleration))
                        trace.append(trace_point(event.t_s, event_state, acceleration))
                elif include_trace:
                    trace.append(trace_point(next_time, updated, acceleration))
            time, state = next_time, updated
            if event is not None and time > case.times[-1]:
                return ForwardResult(tuple(observations), tuple(valid), event, tuple(trace))
        if target in case.times:
            index = case.times.index(target)
            observations[index] = state[:3]
            valid[index] = target <= config.horizon_s and (
                event is None or (event.t_s is not None and target <= event.t_s + config.root_tolerance_s)
            )
        if event is not None and target >= case.times[-1]:
            break

    if event is None:
        event = EventResult("NO_REACH", reason="horizon")
    return ForwardResult(tuple(observations), tuple(valid), event, tuple(trace))
