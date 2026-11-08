"""Gravity and relative-air aerodynamic acceleration for M1, M2 and M3."""

from bisect import bisect_right
from collections.abc import Mapping
from functools import lru_cache
import json
import math
from numbers import Real
from pathlib import Path


DEFAULT_VISCOSITY_PA_S = 1.81e-5
REGISTERED_CURVES = ("goff2026_trionda_b", "goff2026_jabulani_b")


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{label} must be a finite real number")
    try:
        value = float(value)
    except OverflowError as exc:
        raise ValueError(f"{label} must be a finite real number") from exc
    if not math.isfinite(value):
        raise ValueError(f"{label} must be a finite real number")
    return value


def _vector(value, label):
    if isinstance(value, (str, bytes, Mapping)):
        raise ValueError(f"{label} must contain three coordinates")
    try:
        x, y, z = value
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must contain three coordinates") from exc
    return _number(x, label), _number(y, label), _number(z, label)


def _required(values, key):
    try:
        return values[key]
    except KeyError as exc:
        raise ValueError(f"missing required aerodynamic parameter {key}") from exc


def _option(parameters, config, key, default):
    if key in parameters:
        return parameters[key]
    if isinstance(config, Mapping):
        return config.get(key, default)
    return getattr(config, key, default)


def _curve_knots(definition):
    if not isinstance(definition, Mapping):
        raise ValueError("curve must be a registered ID or a mapping with reynolds and cd")
    axes = []
    for key in ("reynolds", "cd"):
        values = _required(definition, key)
        if isinstance(values, (str, bytes, Mapping)):
            raise ValueError(f"curve {key} must be a sequence of numbers")
        try:
            axes.append(tuple(_number(value, f"curve {key}") for value in values))
        except TypeError as exc:
            raise ValueError(f"curve {key} must be a sequence of numbers") from exc
    reynolds, drag = axes
    if len(reynolds) != len(drag) or len(reynolds) < 2:
        raise ValueError("curve needs two or more paired Reynolds and Cd knots")
    if reynolds[0] < 0 or any(right <= left for left, right in zip(reynolds, reynolds[1:])):
        raise ValueError("curve Reynolds knots must be nonnegative and strictly increasing")
    if min(drag) <= 0:
        raise ValueError("reference curve Cd must be strictly positive")
    return reynolds, drag


@lru_cache(maxsize=len(REGISTERED_CURVES))
def _registered_curve(curve_id):
    if curve_id not in REGISTERED_CURVES:
        raise ValueError(f"unknown drag curve ID {curve_id!r}")
    path = Path(__file__).with_name("curves") / f"{curve_id}.json"
    try:
        with path.open(encoding="utf-8") as source:
            return _curve_knots(json.load(source))
    except OSError as exc:
        raise ValueError(f"registered drag curve {curve_id!r} could not be read") from exc


def _reference_cd(reynolds, knots, drag, policy):
    if reynolds < knots[0] or reynolds > knots[-1]:
        if policy == "error":
            raise ValueError(f"Reynolds number {reynolds:.6g} is outside [{knots[0]:.6g}, {knots[-1]:.6g}]")
        if reynolds < knots[0]:
            return drag[0], "clamped_low"
        return drag[-1], "clamped_high"
    if reynolds == knots[-1]:
        return drag[-1], "in_domain"
    index = bisect_right(knots, reynolds) - 1
    fraction = (reynolds - knots[index]) / (knots[index + 1] - knots[index])
    return drag[index] + fraction * (drag[index + 1] - drag[index]), "in_domain"


def build_aerodynamics(model_id, case, parameters, config=None):
    """Return a velocity-to-force-law closure for an M1, M2 or M3 trial.

    Each call returns ``(acceleration_xyz, relative_speed, reynolds, cd, domain)``.
    Reynolds number and domain are supplied only for M3. M1 and M2 accept zero
    drag for verification. Missing transverse coefficients default to zero.
    M1 always sets them to zero. M3 takes a registered curve ID or an inline
    mapping with paired ``reynolds`` and ``cd`` knots. Options in parameters
    override config. At zero relative speed outside the curve domain the
    force vanishes, the anchor is returned as an unused coefficient, and the
    domain is ``zero_speed``. Under clamping, check the anchor reference speed
    against the source domain when selecting the scenario.
    """
    if model_id not in ("M1", "M2", "M3") or not isinstance(parameters, Mapping):
        raise ValueError("aerodynamics requires an M1–M3 model ID and parameter mapping")
    radius = _number(getattr(case, "radius", None), "ball radius")
    mass = _number(getattr(case, "mass", None), "ball mass")
    density = _number(getattr(case, "density", None), "air density")
    gravity = _number(getattr(case, "gravity", None), "gravity")
    wind_x, wind_y, wind_z = _vector(getattr(case, "wind", None), "wind")
    if radius <= 0 or mass <= 0 or density < 0 or gravity < 0:
        raise ValueError("ball radius and mass must be positive, and density and gravity nonnegative")
    beta = _number(0.5 * density * math.pi * radius * (radius / mass), "drag scale")
    cy = _number(parameters.get("cy", 0.0), "cy")
    cz = _number(parameters.get("cz", 0.0), "cz")
    if model_id == "M1":
        cy = cz = 0.0

    if model_id == "M3":
        anchor = _number(_required(parameters, "cd_anchor"), "cd_anchor")
        reference_speed = _number(_required(parameters, "reference_speed_m_s"), "reference_speed_m_s")
        viscosity = _number(_option(parameters, config, "dynamic_viscosity_pa_s", DEFAULT_VISCOSITY_PA_S),
                            "dynamic_viscosity_pa_s")
        policy = _option(parameters, config, "curve_policy", "error")
        if anchor <= 0 or reference_speed <= 0 or viscosity <= 0:
            raise ValueError("M3 anchor, reference speed and dynamic viscosity must be positive")
        if policy not in ("error", "clamp"):
            raise ValueError("curve_policy must be 'error' or 'clamp'")
        curve = _required(parameters, "curve")
        knots, drag = _registered_curve(curve) if isinstance(curve, str) else _curve_knots(curve)
        reynolds_per_speed = _number(density * (2 * radius / viscosity), "Reynolds scale")
        reference_re = _number(reynolds_per_speed * reference_speed, "reference Reynolds number")
        reference_cd, _ = _reference_cd(reference_re, knots, drag, policy)
        if anchor + (min(drag) - reference_cd) <= 0:
            raise ValueError("M3 anchor yields nonpositive drag over the curve domain")

        def drag_at(speed):
            reynolds = _number(reynolds_per_speed * speed, "Reynolds number")
            if speed == 0 and knots[0] > 0:
                return reynolds, anchor, "zero_speed"
            cd, domain = _reference_cd(reynolds, knots, drag, policy)
            return reynolds, _number(anchor + (cd - reference_cd), "anchored drag"), domain

    else:
        cd = _number(_required(parameters, "cd"), "cd")
        if cd < 0:
            raise ValueError("cd must be nonnegative")

        def drag_at(speed):
            return None, cd, None

    def aero(velocity):
        vx, vy, vz = _vector(velocity, "velocity")
        ux, uy, uz = vx - wind_x, vy - wind_y, vz - wind_z
        speed = _number(math.hypot(ux, uy, uz), "relative speed")
        reynolds, cd, domain = drag_at(speed)
        if speed == 0 or beta == 0:
            return (0.0, 0.0, -gravity), speed, reynolds, cd, domain
        factor = beta * speed
        acceleration = (
            factor * (-cd * ux - cz * uz - cy * uy),
            factor * (-cd * uy + cy * ux),
            factor * (-cd * uz + cz * ux) - gravity,
        )
        if not all(math.isfinite(component) for component in acceleration):
            raise ValueError("aerodynamic acceleration must be finite")
        return acceleration, speed, reynolds, cd, domain

    return aero
