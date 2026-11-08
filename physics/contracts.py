"""Shared inputs and first-event results for WP1 and WP2."""

from dataclasses import dataclass
import json
from pathlib import Path


Vector = tuple[float, float, float]
DEFAULT_CASE = Path(__file__).resolve().parents[1] / "spec" / "case.json"


@dataclass(frozen=True, slots=True)
class Case:
    initial: Vector
    times: tuple[float, float]
    observations: tuple[Vector, Vector]
    goal_x: float
    y_min: float
    y_max: float
    z_min: float
    z_max: float
    radius: float
    mass: float
    density: float
    wind: Vector
    gravity: float
    horizon_s: float = 2.0
    tie_tolerance_s: float = 1e-6
    spatial_tie_tolerance_m: float = 1e-6


@dataclass(frozen=True, slots=True)
class SolverConfig:
    max_step_s: float = 0.01
    horizon_s: float = 2.0
    tie_tolerance_s: float = 1e-6
    spatial_tie_tolerance_m: float = 1e-6
    root_tolerance_s: float = 1e-9


@dataclass(frozen=True, slots=True)
class EventResult:
    event: str
    t_s: float | None = None
    y_m: float | None = None
    z_m: float | None = None
    clearance_goal: bool | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class TracePoint:
    t_s: float | None
    x_m: float
    y_m: float
    z_m: float
    vx_m_s: float | None = None
    vy_m_s: float | None = None
    vz_m_s: float | None = None
    relative_speed_m_s: float | None = None
    reynolds: float | None = None
    drag_coefficient: float | None = None
    curve_domain: str | None = None


@dataclass(frozen=True, slots=True)
class ForwardResult:
    observations: tuple[Vector | None, Vector | None] | None
    observation_valid: tuple[bool, bool]
    event: EventResult
    trace: tuple[TracePoint, ...] = ()
    curve_domains: tuple[str, ...] = ()

    @property
    def curve_extrapolated(self):
        """Whether any evaluated curve argument required endpoint clamping."""
        return any(domain.startswith("clamped_") for domain in self.curve_domains)


def classify_plane(case, t_s, y_m, z_m):
    """Apply the strict center and one-radius clearance tests."""
    inside = case.y_min < y_m < case.y_max and case.z_min < z_m < case.z_max
    radius = case.radius
    clearance = (
        inside
        and case.y_min + radius < y_m < case.y_max - radius
        and radius < z_m < case.z_max - radius
    )
    return EventResult("PLANE_GOAL" if inside else "PLANE_WIDE", t_s, y_m, z_m, clearance)


def load_case(path=DEFAULT_CASE):
    """Read a spec/case.json-shaped file, keeping the case's declared units."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data["schema_version"] != 1 or data["initial"]["t_s"] != 0.0:
        raise ValueError("Expected schema version 1 and launch time zero.")
    points = [data["initial"], *data["observations"]]
    launch, first, second = [tuple(float(p[key]) for key in ("x_m", "y_m", "z_m")) for p in points]
    goal = data["goal"]
    settings = data["nominal_assumptions"]
    protocol = data["protocol_defaults"]
    return Case(
        initial=launch, times=tuple(float(row["t_s"]) for row in data["observations"]),
        observations=(first, second), goal_x=float(goal["x_m"]),
        y_min=float(goal["y_min_m"]), y_max=float(goal["y_max_m"]),
        z_min=float(goal["z_min_m"]), z_max=float(goal["z_max_m"]),
        radius=float(settings["radius_m"]), mass=float(settings["ball_mass_kg"]),
        density=float(settings["air_density_kg_m3"]), wind=tuple(map(float, settings["wind_m_s"])),
        gravity=float(settings["gravity_m_s2"]), horizon_s=float(protocol["horizon_s"]),
        tie_tolerance_s=float(protocol["event_tie_tolerance_s"]),
        spatial_tie_tolerance_m=float(protocol["spatial_event_tie_tolerance_m"]),
    )
