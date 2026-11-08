import math
import unittest

from validation.generate_cases import CASE_PATH, PROTOCOL_PATH, read_json, simulate


class TruthSolverTests(unittest.TestCase):
    def setUp(self):
        self.case = read_json(CASE_PATH)
        self.solver = read_json(PROTOCOL_PATH)["solver"]

    def test_ballistic_plane_and_ground(self):
        gravity = self.case["nominal_assumptions"]["gravity_m_s2"]
        radius = self.case["nominal_assumptions"]["radius_m"]

        def rhs(_time, state):
            return (*state[3:], 0, 0, -gravity)

        frames, event = simulate(self.case, self.solver, rhs, (30, 4, 5), 0.004)
        crossing = 11 / 30
        self.assertEqual(event[0], "PLANE_GOAL")
        self.assertAlmostEqual(event[1], crossing, places=8)
        self.assertAlmostEqual(event[2], 4 * crossing, places=7)
        self.assertAlmostEqual(event[3], radius + 5 * crossing - gravity * crossing ** 2 / 2, places=7)
        self.assertAlmostEqual(frames[1][2], radius + 0.5 - gravity * 0.1 ** 2 / 2, places=10)

        _, ground = simulate(self.case, self.solver, rhs, (20, 0, 2), 0.004)
        self.assertEqual(ground[0], "GROUND_FIRST")
        self.assertAlmostEqual(ground[1], 4 / gravity, places=8)
        self.assertEqual(ground[2:5], ("", "", ""))

    def test_turf_priority_at_crossing(self):
        gravity = self.case["nominal_assumptions"]["gravity_m_s2"]
        crossing = 11 / 30

        def rhs(_time, state):
            return (*state[3:], 0, 0, -gravity)

        for difference in (0, 0.5e-6, 2e-6):
            with self.subTest(ground_delay_s=difference):
                vz = gravity * (crossing + difference) / 2
                _, event = simulate(self.case, self.solver, rhs, (30, 0, vz), 0.004)
                expected = "GROUND_FIRST" if difference < 1e-6 else "PLANE_GOAL"
                self.assertEqual(event[0], expected)

    def test_quadratic_drag_plane(self):
        drag = 0.018
        speed = 35

        def rhs(_time, state):
            vx, vy, vz = state[3:]
            return (vx, vy, vz, -drag * vx ** 2, 0, 0)

        self.case["initial"]["z_m"] = 1
        _, event = simulate(self.case, self.solver, rhs, (speed, 0, 0), 0.004)
        self.assertEqual(event[0], "PLANE_GOAL")
        self.assertAlmostEqual(event[1], math.expm1(drag * 11) / (drag * speed), places=7)
