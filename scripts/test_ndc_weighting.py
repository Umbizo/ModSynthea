#!/usr/bin/env python3
"""P(a Part D fill lands in Rick's sheet) must be materially above uniform."""
import json, os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tools_ta_coverage as T
import tools_weight_ndc_map as W

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXP = os.path.join(ROOT, 'src', 'main', 'resources', 'export')
MED = json.load(open(os.path.join(EXP, 'medication_code_map.json')))


def in_sheet_mass_ratio(rxcui, target_ndc):
    entries = MED.get(str(rxcui)) or []
    if not entries:
        return None
    total = sum(float(e.get('weight', 1.0)) for e in entries)
    if total == 0:
        return 0.0
    inside = sum(float(e.get('weight', 1.0)) for e in entries if str(e['code']) in target_ndc)
    return inside / total


class TestNDCWeighting(unittest.TestCase):
    def test_tiered_mass_matches_in_sheet_count(self):
        """Regression guard for the tiering ruling (a deviation from the
        brief's flat FAVOURED_MASS=0.90): for every RxCUI the tool actually
        reweights, derive the expected favoured mass from that RxCUI's own
        in-sheet NDC count (>=10 -> 0.90, 3-9 -> 0.75, 1-2 -> 0.50) and
        assert the map's actual in-sheet weight mass matches it. Nothing
        here is hardcoded to a specific RxCUI or tier, so it covers all
        three tiers and keeps working if the set of reweighted drugs
        changes.
        """
        by_ta = W.rxcuis_by_ta()
        targets = {}
        for ta, cuis in by_ta.items():
            for c in cuis:
                targets.setdefault(c, set()).update(T.TA_CONFIG[ta]['target_ndc'])

        exercised = {0.90: 0, 0.75: 0, 0.50: 0}
        for rxcui, wanted in targets.items():
            entries = MED.get(rxcui)
            if not entries:
                continue
            inside = [e for e in entries if str(e['code']) in wanted]
            outside = [e for e in entries if str(e['code']) not in wanted]
            if not inside or not outside:
                continue  # nothing to favour, or nothing to demote -- tool skips these too
            expected_mass = W.favoured_mass(len(inside), len(entries))
            actual = in_sheet_mass_ratio(rxcui, wanted)
            self.assertAlmostEqual(
                actual, expected_mass, delta=0.01,
                msg=f'RxCUI {rxcui}: {len(inside)} in-sheet NDCs should carry mass '
                    f'{expected_mass:.2f}, actual is {actual:.3f}')
            raw_tier = (0.90 if len(inside) >= 10 else
                        0.75 if len(inside) >= 3 else 0.50)
            exercised[raw_tier] += 1

        # The test must actually exercise all three tiers, not just the one
        # that happens to match the brief's original flat value.
        self.assertGreater(exercised[0.90], 0, 'no RxCUI exercised the 0.90 tier')
        self.assertGreater(exercised[0.75], 0, 'no RxCUI exercised the 0.75 tier')
        self.assertGreater(exercised[0.50], 0, 'no RxCUI exercised the 0.50 tier')

    def test_reweighting_never_moves_below_uniform_baseline(self):
        """A reweighted RxCUI must never end up LESS likely to land in the
        codesheet than it was under the original uniform draw
        (n_inside / n_total). Guards against a tier that, for a small
        total NDC count, sits below the RxCUI's pre-existing baseline and
        makes the reweighting counterproductive."""
        by_ta = W.rxcuis_by_ta()
        targets = {}
        for ta, cuis in by_ta.items():
            for c in cuis:
                targets.setdefault(c, set()).update(T.TA_CONFIG[ta]['target_ndc'])

        checked = 0
        for rxcui, wanted in targets.items():
            entries = MED.get(rxcui)
            if not entries:
                continue
            inside = [e for e in entries if str(e['code']) in wanted]
            outside = [e for e in entries if str(e['code']) not in wanted]
            if not inside or not outside:
                continue  # nothing to favour, or nothing to demote -- tool skips these too
            uniform = len(inside) / len(entries)
            actual = in_sheet_mass_ratio(rxcui, wanted)
            self.assertGreaterEqual(
                actual, uniform - 1e-9,
                msg=f'RxCUI {rxcui}: reweighting dropped P(hit) to {actual:.3f}, '
                    f'below the uniform baseline of {uniform:.3f}')
            checked += 1
        self.assertGreater(checked, 0, 'no reweighted RxCUI was checked')

    def test_weights_never_zero_out_a_whole_drug(self):
        for rxcui, entries in MED.items():
            total = sum(float(e.get('weight', 1.0)) for e in entries)
            self.assertGreater(total, 0.0, f'RxCUI {rxcui} has zero total weight')

    def test_no_ndc_is_dropped(self):
        """Reweighting must not delete alternatives -- only re-rank them."""
        counts = json.load(open(os.path.join(ROOT, 'scripts', 'ndc_counts_baseline.json')))
        for rxcui, n in counts.items():
            self.assertEqual(len(MED.get(rxcui, [])), n,
                             f'RxCUI {rxcui} lost NDC entries')


if __name__ == '__main__':
    unittest.main()
