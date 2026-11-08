"""Black-box acceptance tests for the Problem B forward solver."""

from dataclasses import replace
import math
import unittest

from physics import SolverConfig, load_case, solve


PLANE_GOAL = "PLANE_GOAL"
PLANE_WIDE = "PLANE_WIDE"
GROUND_FIRST = "GROUND_FIRST"
NO_REACH = "NO_REACH"
NUMERICAL_FAILURE = "NUMERICAL_FAILURE"
POSITION_TOLERANCE = 0.001
TIME_TOLERANCE = 0.0001


class ForwardAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.case = load_case()

    def assert_point_close(self, actual, expected, tolerance=POSITION_TOLERANCE):
        self.assertIsNotNone(actual)
        for coordinate, reference in zip(actual, expected, strict=True):
            self.assertAlmostEqual(coordinate, reference, delta=tolerance)

    def assert_same_event(self, actual, expected, position_tol=POSITION_TOLERANCE,
                          time_tol=TIME_TOLERANCE):
        self.assertEqual(actual.event, expected.event)
        self.assertEqual(actual.clearance_goal, expected.clearance_goal)
        for field, tolerance in (("t_s", time_tol), ("y_m", position_tol), ("z_m", position_tol)):
            reference = getattr(expected, field)
            if reference is None:
                self.assertIsNone(getattr(actual, field))
            else:
                self.assertAlmostEqual(getattr(actual, field), reference, delta=tolerance)

    def test_b1_official_case_matches_independent_quadratic(self):
        result = solve("B1", self.case, include_trace=True)
        crossing_time = 22.0 / (30.4 + math.sqrt(30.4**2 - 32.0 * 11.0))
        y = 9.4 * crossing_time - 8.0 * crossing_time**2
        z = 0.11 + 6.9 * crossing_time - 6.0 * crossing_time**2

        self.assertEqual(result.observation_valid, (True, True))
        for actual, expected in zip(result.observations, self.case.observations, strict=True):
            self.assert_point_close(actual, expected, 1e-9)
        self.assertEqual(result.event.event, PLANE_GOAL)
        self.assertAlmostEqual(result.event.t_s, crossing_time, delta=1e-8)
        self.assert_point_close((result.event.y_m, result.event.z_m), (y, z), 1e-8)
        self.assertEqual(result.event.clearance_goal, True)
        self.assertAlmostEqual(result.trace[0].t_s, 0.0, delta=1e-12)
        for time in self.case.times:
            self.assertTrue(any(abs(point.t_s - time) < 1e-12 for point in result.trace))
        self.assertAlmostEqual(result.trace[-1].t_s, result.event.t_s, delta=1e-8)
        self.assertAlmostEqual(result.trace[-1].x_m, self.case.goal_x, delta=1e-8)

    def test_b0_fits_gravity_corrected_positions_from_both_frames(self):
        result = solve("B0", self.case)
        denominator = sum(t * t for t in self.case.times)
        velocity = tuple(
            sum(t * (obs[axis] - self.case.initial[axis] +
                     (0.5 * self.case.gravity * t * t if axis == 2 else 0.0))
                for t, obs in zip(self.case.times, self.case.observations, strict=True)) / denominator
            for axis in range(3)
        )
        expected = solve("B0", self.case, {"v0": velocity})
        self.assert_same_event(result.event, expected.event, 1e-10, 1e-10)
        for actual, reference in zip(result.observations, expected.observations, strict=True):
            self.assert_point_close(actual, reference, 1e-10)

    def test_zero_aerodynamics_matches_analytic_vacuum(self):
        velocity = (28.0, 2.5, 5.0)
        vacuum = solve("B0", self.case, {"v0": velocity})
        integrated = solve("M2", self.case, {"v0": velocity, "cd": 0.0, "cy": 0.0, "cz": 0.0})
        t_cross = self.case.goal_x / velocity[0]
        expected_cross = (velocity[1] * t_cross,
                          self.case.radius + velocity[2] * t_cross - 0.5 * self.case.gravity * t_cross**2)

        self.assertEqual(vacuum.event.event, PLANE_GOAL)
        self.assertAlmostEqual(vacuum.event.t_s, t_cross, delta=1e-9)
        self.assert_point_close((vacuum.event.y_m, vacuum.event.z_m), expected_cross, 1e-9)
        self.assert_same_event(integrated.event, vacuum.event, 1e-7, 1e-8)
        for actual, expected in zip(integrated.observations, vacuum.observations, strict=True):
            self.assert_point_close(actual, expected, 1e-8)

    def test_m1_matches_one_dimensional_drag_solution(self):
        case = replace(self.case, initial=(0.6, 0.2, 1.2), gravity=0.0)
        speed, drag = 30.0, 0.27
        k = case.density * math.pi * case.radius**2 * drag / (2 * case.mass)
        result = solve("M1", case, {"v0": (speed, 0.0, 0.0), "cd": drag}, include_trace=True)
        crossing_time = math.expm1(k * (case.goal_x - case.initial[0])) / (k * speed)

        self.assertEqual(result.event.event, PLANE_GOAL)
        self.assertAlmostEqual(result.event.t_s, crossing_time, delta=1e-7)
        self.assert_point_close((result.event.y_m, result.event.z_m), case.initial[1:], 1e-8)
        for t, point in zip(case.times, result.observations, strict=True):
            x = case.initial[0] + math.log1p(k * speed * t) / k
            self.assert_point_close(point, (x, *case.initial[1:]), 1e-7)
        self.assertAlmostEqual(result.trace[-1].vx_m_s, speed / (1 + k * speed * crossing_time), delta=1e-6)

    def test_strict_center_and_clearance_boundaries(self):
        case = replace(self.case, goal_x=1.0)
        delta = 0.0001
        for y, z, event, clearance in (
            (0.0, 1.0, PLANE_GOAL, True),
            (case.y_min, 1.0, PLANE_WIDE, False),
            (case.y_max, 1.0, PLANE_WIDE, False),
            (0.0, case.z_max, PLANE_WIDE, False),
            (case.y_max - delta, 1.0, PLANE_GOAL, False),
            (0.0, case.z_max + delta, PLANE_WIDE, False),
            (case.y_min + case.radius, 1.0, PLANE_GOAL, False),
            (case.y_max - case.radius, 1.0, PLANE_GOAL, False),
            (0.0, case.z_max - case.radius, PLANE_GOAL, False),
            (case.y_max - case.radius - delta, 1.0, PLANE_GOAL, True),
            (0.0, case.z_max - case.radius - delta, PLANE_GOAL, True),
        ):
            with self.subTest(y=y, z=z):
                fixture = replace(case, initial=(0.0, y, z))
                result = solve("B1", fixture, {"v0": (4.0, 0.0, 0.0), "a0": (0.0, 0.0, 0.0)})
                self.assertEqual(result.event.event, event)
                self.assertEqual(result.event.clearance_goal, clearance)
                self.assert_point_close((result.event.y_m, result.event.z_m), (y, z), 1e-10)

    def test_competing_ground_and_plane_events_in_same_step(self):
        ground_time = 0.24
        case = replace(self.case, gravity=10.0)
        config = SolverConfig(max_step_s=0.2, tie_tolerance_s=1e-6)
        parameters = {"v0": (10.0, 0.0, 1.2), "cd": 0.0}
        for plane_offset, event in ((-0.01, PLANE_GOAL), (-0.5e-6, GROUND_FIRST),
                                    (0.0, GROUND_FIRST), (0.01, GROUND_FIRST)):
            with self.subTest(plane_offset=plane_offset):
                fixture = replace(case, goal_x=10.0 * (ground_time + plane_offset))
                result = solve("M1", fixture, parameters, config)
                self.assertEqual(result.event.event, event)
                expected_time = ground_time + plane_offset if event == PLANE_GOAL else ground_time
                self.assertAlmostEqual(result.event.t_s, expected_time, delta=2e-8)
                if event == GROUND_FIRST:
                    self.assertIsNone(result.event.y_m)
                    self.assertIsNone(result.event.z_m)
                    self.assertIsNone(result.event.clearance_goal)

    def test_ground_departure_and_observation_validity(self):
        case = replace(self.case, gravity=10.0)
        departing = solve("B0", case, {"v0": (10.0, 0.0, 0.4)})
        penetrating = solve("B0", case, {"v0": (10.0, 0.0, -0.4)})

        self.assertEqual(departing.event.event, GROUND_FIRST)
        self.assertAlmostEqual(departing.event.t_s, 0.08, delta=1e-9)
        self.assertEqual(departing.observation_valid, (True, False))
        self.assertEqual(penetrating.event.event, GROUND_FIRST)
        self.assertEqual(penetrating.event.t_s, 0.0)
        self.assertEqual(penetrating.observation_valid, (False, False))

    def test_backward_and_tangent_plane_encounters_do_not_cross(self):
        case = replace(self.case, initial=(0.0, 0.0, 0.8), goal_x=0.25)
        tangent = solve("B1", case, {"v0": (1.0, 0.0, 0.0), "a0": (-2.0, 0.0, 0.0)})
        reverse_case = replace(case, initial=(0.75, 0.0, 0.8))
        reverse = solve("B1", reverse_case, {"v0": (-1.0, 0.0, 0.0), "a0": (0.0, 0.0, 0.0)})
        forward_case = replace(case, goal_x=0.75)
        forward = solve("B1", forward_case, {"v0": (4.0, 0.0, 0.0), "a0": (-8.0, 0.0, 0.0)})

        self.assertEqual(tangent.event.event, NO_REACH)
        self.assertEqual(reverse.event.event, NO_REACH)
        self.assertEqual(forward.event.event, PLANE_GOAL)
        self.assertAlmostEqual(forward.event.t_s, 0.25, delta=1e-9)

    def test_horizon_and_unsupported_input_are_distinct(self):
        case = replace(self.case, initial=(0.0, 0.0, 0.8), gravity=0.0)
        horizon = solve("M1", case, {"v0": (1.0, 0.0, 0.0), "cd": 0.0}, SolverConfig(horizon_s=0.2))
        nonfinite = solve("M1", case, {"v0": (math.nan, 0.0, 0.0), "cd": 0.0})
        invalid_time = solve("B0", replace(case, times=(0.1, 0.05)), {"v0": (30.0, 0.0, 1.0)})

        self.assertEqual(horizon.event.event, NO_REACH)
        for result in (nonfinite, invalid_time):
            self.assertEqual(result.event.event, NUMERICAL_FAILURE)
            self.assertTrue(result.event.reason)
            self.assertIsNone(result.event.y_m)
            self.assertIsNone(result.event.z_m)

    def test_b2_spatial_crossing_without_time(self):
        initial = (0.0, 0.0, 0.8)

        def point(x):
            return x, 0.1 * x + 0.005 * x**2, 0.8 + 0.08 * x - 0.002 * x**2

        frames = (point(1.5), point(2.96))
        case = replace(self.case, initial=initial, observations=frames)
        result = solve("B2", case)
        invalid = solve("B2", case, {"frame_centers": (frames[0], point(1.5))})

        self.assertEqual(result.event.event, PLANE_GOAL)
        self.assertIsNone(result.event.t_s)
        self.assert_point_close((result.event.y_m, result.event.z_m), point(case.goal_x)[1:], 1e-8)
        self.assertEqual(invalid.event.event, NUMERICAL_FAILURE)
        self.assertTrue(invalid.event.reason)

    def test_b2_uses_spatial_tie_tolerance(self):
        ground_x = 0.25
        radius = self.case.radius
        initial = (0.0, 0.0, radius + ground_x)
        frames = ((0.05, 0.0, radius + ground_x - 0.05), (0.1, 0.0, radius + ground_x - 0.1))
        case = replace(self.case, initial=initial, observations=frames)
        config = SolverConfig(spatial_tie_tolerance_m=1e-6)

        for plane_offset, event in ((-1e-4, PLANE_GOAL), (-0.5e-6, GROUND_FIRST),
                                    (0.0, GROUND_FIRST), (1e-4, GROUND_FIRST)):
            with self.subTest(plane_offset=plane_offset):
                result = solve("B2", replace(case, goal_x=ground_x + plane_offset), config=config)
                self.assertEqual(result.event.event, event)
                self.assertIsNone(result.event.t_s)

    def test_zero_transverse_force_reduces_m2_to_m1(self):
        parameters = {"v0": (30.3, 5.5, 6.8), "cd": 0.27}
        drag_only = solve("M1", self.case, parameters)
        zero_transverse = solve("M2", self.case, {**parameters, "cy": 0.0, "cz": 0.0})

        self.assert_same_event(zero_transverse.event, drag_only.event, 1e-9, 1e-9)
        for actual, expected in zip(zero_transverse.observations, drag_only.observations, strict=True):
            self.assert_point_close(actual, expected, 1e-9)

    def test_transverse_force_sign_and_no_air_relative_work(self):
        case = replace(self.case, initial=(0.0, 0.0, 0.8), gravity=0.0)
        velocity = (30.0, 0.0, 0.0)
        result = solve("M2", case, {"v0": velocity, "cd": 0.0, "cy": 0.1, "cz": 0.12},
                       include_trace=True)

        self.assertEqual(result.event.event, PLANE_GOAL)
        self.assertGreater(result.event.y_m, 0.0)
        self.assertGreater(result.event.z_m, case.initial[2])
        final = result.trace[-1]
        self.assertAlmostEqual(math.hypot(final.vx_m_s, final.vy_m_s, final.vz_m_s), velocity[0], delta=1e-6)

    def test_m3_flat_reference_curve_reduces_to_m2_and_reports_reynolds(self):
        common = {"v0": (30.3, 5.5, 6.8), "cy": -0.12, "cz": 0.04}
        drag = 0.29
        viscosity = 1.8e-5
        constant = solve("M2", self.case, {**common, "cd": drag})
        curve = {"reynolds": (100_000.0, 1_000_000.0), "cd": (0.4, 0.4)}
        anchored = solve("M3", self.case, {**common, "cd_anchor": drag, "curve": curve,
                                           "reference_speed_m_s": 30.0, "dynamic_viscosity_pa_s": viscosity},
                         include_trace=True)

        self.assert_same_event(anchored.event, constant.event, 1e-9, 1e-9)
        for actual, expected in zip(anchored.observations, constant.observations, strict=True):
            self.assert_point_close(actual, expected, 1e-9)
        self.assertTrue(anchored.trace)
        for point in anchored.trace:
            self.assertEqual(point.curve_domain, "in_domain")
            self.assertAlmostEqual(point.drag_coefficient, drag, delta=1e-12)
            relative_speed = math.hypot(point.vx_m_s, point.vy_m_s, point.vz_m_s)
            self.assertAlmostEqual(point.relative_speed_m_s, relative_speed, delta=1e-10)
            reynolds = self.case.density * (2.0 * self.case.radius) * relative_speed / viscosity
            self.assertAlmostEqual(point.reynolds, reynolds, delta=1e-6)

    def test_m2_observations_and_crossing_converge(self):
        parameters = {"v0": (30.3, 9.2, 6.8), "cd": 0.27, "cy": -0.18, "cz": 0.05}
        coarse = solve("M2", self.case, parameters, SolverConfig(max_step_s=0.025))
        fine = solve("M2", self.case, parameters, SolverConfig(max_step_s=0.005))

        self.assertIn(fine.event.event, (PLANE_GOAL, PLANE_WIDE))
        self.assertEqual(coarse.observation_valid, (True, True))
        self.assert_same_event(coarse.event, fine.event)
        for actual, expected in zip(coarse.observations, fine.observations, strict=True):
            self.assert_point_close(actual, expected)

    def test_drag_only_time_domain_matches_independent_spatial_reference(self):
        velocity = (30.0, 4.0, 7.0)
        drag = 0.27
        result = solve("M1", self.case, {"v0": velocity, "cd": drag})
        t, y, z = spatial_drag_reference(self.case, velocity, drag)

        self.assertEqual(result.event.event, PLANE_GOAL)
        self.assertAlmostEqual(result.event.t_s, t, delta=TIME_TOLERANCE)
        self.assert_point_close((result.event.y_m, result.event.z_m), (y, z))


def spatial_drag_reference(case, velocity, drag):
    """Independent reduction with x as the integration variable in still air."""
    beta = case.density * math.pi * case.radius**2 / (2.0 * case.mass)
    lateral_slope = velocity[1] / velocity[0]

    def derivative(state):
        vx, vertical_slope, _, _ = state
        speed = vx * math.sqrt(1.0 + lateral_slope**2 + vertical_slope**2)
        return -beta * drag * speed, -case.gravity / vx**2, vertical_slope, 1.0 / vx

    def shift(state, slope, step):
        return tuple(value + step * rate for value, rate in zip(state, slope, strict=True))

    state = (velocity[0], velocity[2] / velocity[0], case.initial[2], 0.0)
    span = case.goal_x - case.initial[0]
    count = 1024
    step = span / count
    for _ in range(count):
        first = derivative(state)
        second = derivative(shift(state, first, step / 2.0))
        third = derivative(shift(state, second, step / 2.0))
        fourth = derivative(shift(state, third, step))
        mean_slope = tuple((a + 2.0 * b + 2.0 * c + d) / 6.0
                           for a, b, c, d in zip(first, second, third, fourth, strict=True))
        state = shift(state, mean_slope, step)
    _, _, z, time = state
    return time, case.initial[1] + lateral_slope * span, z


if __name__ == "__main__":
    unittest.main()
