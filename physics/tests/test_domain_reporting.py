"""Domain diagnostics must survive the no-trace inference interface."""
import unittest
from physics import load_case, solve


class DomainReportingTests(unittest.TestCase):
    def test_clamping_without_trace_and_anchor_clamping(self):
        common = dict(v0=(45, 0, 5), cd_anchor=.31,
                      reference_speed_m_s=30, curve='goff2026_trionda_b',
                      curve_policy='clamp')
        for parameters in (common, {**common, 'v0': (30, 0, 5),
                                     'reference_speed_m_s': 45}):
            result = solve('M3', load_case(), parameters)
            traced = solve('M3', load_case(), parameters, include_trace=True)
            self.assertEqual(result.trace, ())
            self.assertTrue(result.curve_extrapolated)
            self.assertIn('clamped_high', result.curve_domains)
            self.assertEqual(result.event, traced.event)
            self.assertTrue(traced.curve_extrapolated)

    def test_nominal_and_noncurve_models_are_not_extrapolated(self):
        parameters = dict(v0=(30, 8, 6), cd_anchor=.31,
                          reference_speed_m_s=30, curve='goff2026_trionda_b')
        result = solve('M3', load_case(), parameters)
        self.assertEqual(result.curve_domains, ('in_domain',))
        self.assertFalse(result.curve_extrapolated)
        self.assertFalse(solve('B1', load_case()).curve_extrapolated)
        self.assertEqual(solve('M3', load_case(), {**parameters, 'v0': (45, 0, 5)}).event.event,
                         'NUMERICAL_FAILURE')
