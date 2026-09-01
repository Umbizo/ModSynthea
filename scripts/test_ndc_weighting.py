#!/usr/bin/env python3
"""P(a Part D fill lands in Rick's sheet) must be materially above uniform."""
import json, os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tools_ta_coverage as T

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXP = os.path.join(ROOT, 'src', 'main', 'resources', 'export')
MED = json.load(open(os.path.join(EXP, 'medication_code_map.json')))


def hit_probability(rxcui, target_ndc):
    entries = MED.get(str(rxcui)) or []
    if not entries:
        return None
    total = sum(float(e.get('weight', 1.0)) for e in entries)
    if total == 0:
        return 0.0
    inside = sum(float(e.get('weight', 1.0)) for e in entries if str(e['code']) in target_ndc)
    return inside / total


class TestNDCWeighting(unittest.TestCase):
    # (rxcui, TA key) pairs where the TA sheet does carry NDC rows
    CASES = [('313988', 'HF'), ('314076', 'HF'), ('312615', 'HF')]

    def test_weighted_draw_favours_ricks_ndcs(self):
        for rxcui, ta in self.CASES:
            target = T.TA_CONFIG[ta]['target_ndc']
            p = hit_probability(rxcui, target)
            if p is None:
                continue
            overlap = [e for e in MED[rxcui] if str(e['code']) in target]
            if not overlap:
                continue  # no Rick NDC exists for this drug; nothing to weight toward
            self.assertGreaterEqual(p, 0.80,
                                    f'RxCUI {rxcui} ({ta}): P(hit) is {p:.3f}, expected >= 0.80')

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
