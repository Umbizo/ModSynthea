#!/usr/bin/env python3
"""Offline checks on the coverage harness. No generation required."""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tools_ta_coverage as T

class TestRegistry(unittest.TestCase):
    def test_every_ta_selects_at_least_one_dx_code(self):
        for key, cfg in T.TA_CONFIG.items():
            self.assertTrue(cfg['dx_codes'], f'{key} selected zero ICD-10-CM codes')

    def test_module_stems_resolve_to_real_files(self):
        missing = {}
        for key, cfg in T.TA_CONFIG.items():
            for stem in (cfg.get('module_stems') or []):
                if not T.module_exists(stem):
                    missing.setdefault(key, []).append(stem)
        self.assertEqual(missing, {}, f'stems naming no module: {missing}')

    def test_prefix_matching_is_parent_directional(self):
        # sheet carries I48; a claim carrying the billable leaf I4811 must match
        self.assertTrue(T.prefix_hit({'I4811'}, {'I48'}, [3]))
        # and the reverse must NOT match: a claim I48 does not satisfy a sheet leaf I4811
        self.assertFalse(T.prefix_hit({'I48'}, {'I4811'}, [5]))

    def test_covid_dx_codes_survive_icd_shape_filter(self):
        # U07.1 is a valid ICD-10-CM code; a shape filter excluding U would zero COVID
        self.assertTrue(T.TA_CONFIG['COVID']['dx_codes'])

if __name__ == '__main__':
    unittest.main()
