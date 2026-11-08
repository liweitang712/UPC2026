import unittest

from validation.assess_models import ForecastScore, assess, paired_comparison, score_bundle


def draw(draw_id, weight, event, clearance="", y="", z=""):
    return dict(draw_id=draw_id, weight=weight, event=event, clearance_goal=clearance, y_m=y, z_m=z)


def protocol():
    return {
        "models": ["B0", "B1", "B2", "M1", "M2", "M3"],
        "core_strata": ["matched", "wind"],
        "minimum_counts": {"selection": 1, "blind": 1},
        "decision": {
            "bootstrap_seed": 42, "bootstrap_replicates": 20, "blind_ci_level": 0.95,
            "minimum_brier_gain": 0.01, "maximum_entirely_invalid_fraction": 0.01,
            "maximum_core_brier_degradation": 0.02, "selection_bootstrap_se_multiplier": 1,
            "coverage_level": 0.95, "maximum_undercoverage": 0.05,
            "minimum_conditional_effective_draws": 1, "joint_region_grid_m": 0.1,
        },
    }


class ModelAssessmentTest(unittest.TestCase):
    def test_unresolved_mass_is_kept_for_all_event_losses(self):
        truth = draw("truth", 1, "PLANE_GOAL", "1", "0.01", "1.01")
        draws = [draw("a", 0.5, "PLANE_GOAL", "1", "0.01", "1.01"),
                 draw("b", 0.25, "PLANE_WIDE", "0", "6.01", "1.01"),
                 draw("c", 0.25, "NUMERICAL_FAILURE")]
        score = score_bundle(draws, truth, protocol()["decision"])
        self.assertEqual(score.losses, (0.25, 0.0625, 0.25, 0.0625))
        self.assertTrue(score.failed)
        self.assertFalse(score.entirely_invalid)
        self.assertTrue(score.coverage_95)
        self.assertEqual(score_bundle(draws[:1], truth, protocol()["decision"]), ForecastScore())
        self.assertEqual(score_bundle([draw("a", 1, "PLANE_WIDE", "1", "6", "1")],
                                      truth, protocol()["decision"]), ForecastScore())

    def test_strata_receive_equal_weight_and_challenge_is_separate(self):
        groups = {"matched": [("a", "PLANE_GOAL")],
                  "wind": [("b", "PLANE_GOAL"), ("c", "PLANE_GOAL")],
                  "challenge": [("d", "PLANE_GOAL")]}
        cfg = protocol()
        scores = {(key, "B0"): ForecastScore((0.0,) * 4, False, False, True)
                  for key in ("a", "b", "c", "d")}
        scores["a", "B1"] = ForecastScore((0.6,) * 4, False, False, True)
        scores["b", "B1"] = scores["c", "B1"] = ForecastScore((0.2,) * 4, False, False, True)
        scores["d", "B1"] = ForecastScore((1.0,) * 4, False, False, True)
        row = paired_comparison("B0", "B1", groups, scores, cfg["core_strata"], cfg["decision"])
        self.assertAlmostEqual(row["gain"], 0.4)
        self.assertAlmostEqual(row["interval_lo"], 0.4)
        self.assertEqual(row["stratum_gains"]["challenge"]["gain"], 1.0)

    def test_selects_last_accepted_candidate_and_checks_blind_confirmation(self):
        groups = {"matched": [("a", "PLANE_GOAL")], "wind": [("b", "PLANE_GOAL")]}
        cfg = protocol()
        losses = {"B0": 0.22, "B1": 0.20, "B2": 0.21, "M1": 0.14, "M2": 0.10, "M3": 0.03}
        scores = {(key, model): ForecastScore((loss,) * 4, False, False, model != "M3")
                  for key in ("a", "b") for model, loss in losses.items()}
        report = assess(groups, scores, cfg["models"], cfg, "selection")
        self.assertEqual((report["selected_model"], report["comparator_model"]), ("M2", "M1"))
        self.assertFalse(report["comparisons"][-1]["checks"]["coverage_95"])
        blind = assess(groups, scores, ("M2", "M1"), cfg, "blind", ("M2", "M1"))
        self.assertTrue(blind["confirmed"])
        self.assertEqual(blind["recommended_model"], "M2")

    def test_rejects_small_stratum_and_preserves_baseline(self):
        groups = {"matched": [("a", "PLANE_GOAL")], "wind": [("b", "PLANE_GOAL")]}
        cfg = protocol()
        cfg["minimum_counts"]["selection"] = 2
        scores = {(key, model): ForecastScore(((0.25 if model.startswith("B") else 0.1),) * 4,
                                              False, False, True)
                  for key in ("a", "b") for model in cfg["models"]}
        report = assess(groups, scores, cfg["models"], cfg, "selection")
        self.assertEqual((report["selected_model"], report["comparator_model"]), ("B0", "B1"))
        self.assertTrue(all(not row["checks"]["minimum_core_counts"] for row in report["comparisons"]))


if __name__ == "__main__":
    unittest.main()
