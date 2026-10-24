import math
import unittest

from dota_analysis import stats_utils as s


class TestWilson(unittest.TestCase):
    def test_half(self):
        lo, hi = s.wilson_ci(50, 100)
        self.assertAlmostEqual(lo, 0.4038, places=3)
        self.assertAlmostEqual(hi, 0.5962, places=3)

    def test_zero(self):
        lo, hi = s.wilson_ci(0, 10)
        self.assertEqual(lo, 0.0)
        self.assertGreater(hi, 0.0)

    def test_full(self):
        lo, hi = s.wilson_ci(10, 10)
        self.assertEqual(hi, 1.0)
        self.assertLess(lo, 1.0)

    def test_fpc_narrows(self):
        lo, hi = s.wilson_ci(50, 100)
        lo2, hi2 = s.wilson_ci_fpc(50, 100, population=1000)
        self.assertLess(hi2 - lo2, hi - lo)


class TestDesign(unittest.TestCase):
    def test_clustered(self):
        vals = [1, 1, 1, 0, 0, 0, 1, 1, 1, 0, 0, 0]
        clusters = ["a", "a", "a", "b", "b", "b", "c", "c", "c", "d", "d", "d"]
        d = s.design_effect(vals, clusters)
        self.assertGreater(d.deff, 1.5)
        self.assertGreaterEqual(d.icc, 0.0)

    def test_independent(self):
        vals = [1, 0, 1, 0, 1, 0, 1, 0]
        clusters = [str(i) for i in range(8)]
        d = s.design_effect(vals, clusters)
        self.assertAlmostEqual(d.deff, 1.0, places=6)


class TestAgreement(unittest.TestCase):
    def test_perfect(self):
        a = [1, 0, 1, 0, 1]
        self.assertAlmostEqual(s.cohen_kappa(a, a), 1.0)

    def test_chance(self):
        k = s.cohen_kappa([0, 1, 0, 1], [0, 0, 1, 1])
        self.assertAlmostEqual(k, 0.0, places=6)

    def test_sens_spec(self):
        m = s.sens_spec([1, 1, 0, 0], [1, 0, 0, 1])
        self.assertEqual(m["tp"], 1)
        self.assertEqual(m["tn"], 1)
        self.assertEqual(m["fp"], 1)
        self.assertEqual(m["fn"], 1)
        self.assertAlmostEqual(m["sensitivity"], 0.5)


class TestTrend(unittest.TestCase):
    def test_increasing(self):
        mk = s.mann_kendall(list(range(1, 13)))
        self.assertLess(mk["p"], 0.05)
        self.assertGreater(mk["z"], 0)

    def test_flat(self):
        mk = s.mann_kendall([5] * 8)
        self.assertEqual(mk["s"], 0)

    def test_ols(self):
        x = list(range(10))
        y = [2 * v + 1 for v in x]
        r = s.ols_slope(x, y)
        self.assertAlmostEqual(r["slope"], 2.0, places=4)
        self.assertAlmostEqual(r["p"], 0.0, places=3)


class TestRates(unittest.TestCase):
    def test_ratio(self):
        r = s.rate_ratio(20, 100, 10, 100)
        self.assertAlmostEqual(r["rr"], 2.0, places=3)
        self.assertLess(r["p"], 0.1)

    def test_rogan_gladen(self):
        self.assertAlmostEqual(s.rogan_gladen(0.5, 1.0, 1.0), 0.5)
        self.assertAlmostEqual(s.rogan_gladen(0.5, 0.8, 0.9), (0.5 + 0.9 - 1) / 0.7)


if __name__ == "__main__":
    unittest.main()
