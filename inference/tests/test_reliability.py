import math
import unittest
from dataclasses import replace
from unittest.mock import patch

import numpy as np
from physics import EventResult, load_case, solve
from inference.forecast import forecast_group
from inference.baseline import ballistic_fit
from inference.likelihood import (gaussian_log_likelihood,
                                  correlated_gaussian_log_likelihood,
                                  rounded_log_likelihood)
from inference.report import summarize, grid_region


class ReliabilityTests(unittest.TestCase):
    def test_analytic_reference(self):
        case = load_case()
        velocity, scale = ballistic_fit(case)
        self.assertAlmostEqual(velocity[0], 29.68)
        self.assertAlmostEqual(velocity[1], 8.68)
        self.assertAlmostEqual(scale**2, .0125)
        fit = solve('B1', case)
        np.testing.assert_allclose(fit.observations, case.observations, atol=1e-12)

    def test_likelihood_limits(self):
        q = ((0.,)*3,)*2
        sigma = .01
        factor = [[sigma if i == j else 0. for j in range(6)] for i in range(6)]
        p = ((.001, .002, .003), (-.001, -.002, -.003))
        self.assertAlmostEqual(gaussian_log_likelihood(q, p, sigma),
                               correlated_gaussian_log_likelihood(q, p, factor))
        self.assertEqual(rounded_log_likelihood(q, p, .01, 1e-6), 0)
        self.assertLess(rounded_log_likelihood(q, ((.006,)*3,)*2, .01, 1e-6), -100)
        self.assertTrue(math.isfinite(rounded_log_likelihood(q, ((1.,)*3,)*2, 1e-8, sigma)))

    def test_accounting_and_conditional_gate(self):
        def row(event, weight, plane=False):
            return dict(event=event, weight=str(weight), clearance_goal='0' if plane else '',
                        t_s='.4' if plane else '', y_m='4' if plane else '', z_m='2' if plane else '')
        rows = [row('PLANE_WIDE', .01, True) for _ in range(60)]
        rows += [row('NO_REACH', .3), row('NUMERICAL_FAILURE', .1)]
        result = summarize(rows, load_case())
        self.assertAlmostEqual(result['p_reach'], .6)
        self.assertEqual(result['p_goal_given_reach'], 0)
        self.assertEqual(result['probability_bounds']['p_goal'], [0, .1])
        self.assertNotIn('y_m', result['plane_intervals'])
        region = grid_region(np.array([[0., 0.], [.2, 0.]]), np.array([.5, .5]))
        self.assertEqual(len(region['regions'][0]['cells']), 2)

    def test_curve_rejection_does_not_abort_and_numerical_failure_does(self):
        case = load_case()
        settings = dict(sigma_m=.01, curve='goff2026_trionda_b')
        job = ('public', 'nominal', settings, case, 'M3', 40, 2026)
        for reason, should_fail in [('ValueError: Reynolds number 50 is outside [10, 40]', False),
                                    ('ArithmeticError: integrator defect', True)]:
            calls = 0
            def injected(model, case, parameters, config):
                nonlocal calls
                result = solve(model, case, parameters, config)
                calls += 1
                if calls == 4 or (should_fail and calls == 5):
                    return replace(result, event=EventResult('NUMERICAL_FAILURE', reason=reason))
                return result
            with patch('inference.m2.solve', side_effect=injected):
                _, rows, diagnostics = forecast_group(job)
            audit = diagnostics['sampling']
            if should_fail:
                self.assertEqual(diagnostics['p_failure'], 1)
                self.assertEqual(audit['likelihood_retries'], 1)
                self.assertEqual(audit['unresolved_likelihood_failures'], 1)
            else:
                self.assertEqual(audit['rejected']['curve_support'], 1)
                self.assertGreater(len(rows), 1)
                self.assertAlmostEqual(sum(w for _, w, _ in rows), 1)
