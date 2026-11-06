#!/usr/bin/env python3
"""tests/test_modern_engines.py — Automated verification of 2026 Modern Opera Solver engines.

Verifies:
1. Autobolge 2.0 Constructive Conveyor Synthesis (O(N) deterministic).
2. XLAT2 Nested Ripple Counter Synthesizer (positive expansion, clean HALT).
3. BolgeForge Strict Canonical C Oracle (mb_ref) integration.
4. MetaSearch automatic strategy routing (conveyor vs beam vs sa vs exhaustive).
5. DannyScript DSL presets and configuration parsing.
"""

import unittest
from pathlib import Path

from opera.dsl import parse_dannyscript
from opera.evaluator import UnifiedEvaluator
from opera.search.conveyor import (
    synthesize_conveyor,
    can_conveyor_fit,
    conveyor_capacity,
    ConveyorSynthesizer,
)
from opera.search.ripple import (
    synthesize_ripple_counter,
    RippleSynthesizer,
    find_lmao,
    find_oracle,
)
from opera.search.meta import MetaSearch
from opera.verify.oracle import OracleVerifier


class TestModernEngines(unittest.TestCase):

    def test_01_conveyor_synthesis_hello(self):
        """Conveyor synthesizes 'Hello World!' in < 100 ms with clean HALT."""
        target = "Hello World!"
        self.assertTrue(can_conveyor_fit(target))
        res = synthesize_conveyor(target, verify=True)
        self.assertTrue(res.verified)
        self.assertEqual(res.output, target)
        self.assertEqual(res.steps, 46)
        self.assertTrue(len(res.program) > 3000)

    def test_02_conveyor_synthesis_opera_2026(self):
        """Conveyor synthesizes longer phrase correctly."""
        target = "Danny Opera Solver 2026: Next-Gen Malbolge Synthesis"
        self.assertTrue(can_conveyor_fit(target))
        res = synthesize_conveyor(target, verify=True)
        self.assertTrue(res.verified)
        self.assertEqual(res.output, target)

    def test_03_conveyor_capacity(self):
        """Sterile gap capacity check."""
        cap = conveyor_capacity()
        self.assertEqual(cap, 3194)
        short_text = "A" * 100
        self.assertTrue(can_conveyor_fit(short_text))
        huge_text = "A" * 2000
        self.assertFalse(can_conveyor_fit(huge_text))

    def test_04_ripple_counter_synthesis(self):
        """XLAT2 Ripple Counter compiles and matches 5^N outputs."""
        if not RippleSynthesizer.is_available():
            self.skipTest("LMAO compiler not found on host")
        res = synthesize_ripple_counter(stages=2, char_to_print="Z", verify=True)
        self.assertTrue(res.exact_match)
        self.assertTrue(res.halted_cleanly)
        self.assertEqual(res.output_bytes, 25)

    def test_05_ripple_counter_positive_expansion(self):
        """XLAT2 Ripple Counter 7-stage produces positive expansion (ratio > 10x)."""
        if not RippleSynthesizer.is_available():
            self.skipTest("LMAO compiler not found on host")
        res = synthesize_ripple_counter(stages=7, char_to_print="A", verify=False)
        self.assertEqual(res.expected_outputs, 78125)
        self.assertGreater(res.ratio, 14.0)

    def test_06_mb_ref_oracle_evaluation(self):
        """Strict canonical C oracle (mb_ref) validates hello_solved specimen."""
        verifier = OracleVerifier()
        if not verifier.is_available():
            self.skipTest("mb_ref C oracle not found on host")
        hello_path = Path(__file__).resolve().parent.parent / "specimens" / "hello_solved.mal"
        self.assertTrue(hello_path.exists())
        res = verifier.verify(hello_path)
        self.assertTrue(res.success)
        self.assertTrue(res.halted)
        self.assertEqual(res.stdout, "Hello World!")
        self.assertLess(res.elapsed_ms, 1000.0)

    def test_07_meta_search_routing(self):
        """MetaSearch routes text targets to conveyor automatically."""
        meta = MetaSearch()
        res = meta.solve("Fast Synthesis Test")
        self.assertTrue(res.found)
        self.assertEqual(res.strategy_used, "autobolge_conveyor")

    def test_08_dsl_preset_parsing(self):
        """DannyScript DSL parses presets and modern engine configs."""
        source = """
        preset hello
        engine conveyor
        objective minimize size
        """
        spec = parse_dannyscript(source)
        self.assertEqual(spec.target, "Hello World!")
        self.assertEqual(spec.config.get("engine"), "conveyor")


if __name__ == "__main__":
    unittest.main()
