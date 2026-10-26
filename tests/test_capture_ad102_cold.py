#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Tests for tools/capture_ad102_cold.py against a real 4090 log excerpt.

The fixture is the sanitised kernel log in docs/evidence/rtx4090/registers.txt:
cold preflight, post-unlock and post-driver snapshots of one physical card.
"""
import importlib.util
import os
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(REPO, "tools", "capture_ad102_cold.py")
FIXTURE = os.path.join(REPO, "docs", "evidence", "rtx4090", "registers.txt")

spec = importlib.util.spec_from_file_location("capture_ad102_cold", TOOL)
cap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cap)


def load_fixture():
    with open(FIXTURE) as f:
        return f.read()


class ParseSnapshots(unittest.TestCase):
    def setUp(self):
        self.log = load_fixture()
        self.snaps = cap.parse_snapshots(self.log)

    def test_four_snapshots(self):
        """Two driver=none and two driver=nvidia samples in the excerpt."""
        self.assertEqual(len(self.snaps), 4)
        self.assertEqual([s["driver"] for s in self.snaps],
                         ["none", "none", "nvidia", "nvidia"])

    def test_cold_snapshot_values(self):
        cold = cap.select_cold_snapshot(self.snaps)
        self.assertEqual(cold["summary"]["wpr2_up"], 0)
        self.assertEqual(cold["registers"][0x00823804]["value"], 0xFFFFFF8F)
        self.assertEqual(cold["registers"][0x0082381C]["value"], 0x44023025)
        self.assertEqual(cold["registers"][0x00823820]["value"], 0x00000007)
        self.assertEqual(cold["registers"][0x001FA824]["value"], 0x1FFFFE00)
        self.assertEqual(cold["command"], 0x3)

    def test_unlocked_snapshot_is_not_selected(self):
        cold = cap.select_cold_snapshot(self.snaps)
        self.assertIsNot(cold, self.snaps[1])
        self.assertEqual(self.snaps[1]["registers"][0x0082381C]["value"],
                         0x88888888)

    def test_names_with_spaces_parse(self):
        cold = self.snaps[0]
        self.assertEqual(cold["registers"][0x00823818]["name"],
                         "FEAT_READOUT_1 (SS effective)")


class Verdict(unittest.TestCase):
    def setUp(self):
        self.log = load_fixture()
        self.snaps = cap.parse_snapshots(self.log)
        self.prom = cap.parse_prom(self.log)

    def test_cold_block_is_cold(self):
        state, reasons = cap.verdict(self.snaps[0], self.prom)
        self.assertEqual(state, "cold")
        self.assertEqual(reasons, [])

    def test_driver_snapshot_is_warm(self):
        state, reasons = cap.verdict(self.snaps[-1], self.prom)
        self.assertEqual(state, "warm")
        self.assertTrue(any("bound" in r for r in reasons))
        self.assertTrue(any("WPR2" in r for r in reasons))

    def test_unlocked_snapshot_is_warm(self):
        state, reasons = cap.verdict(self.snaps[1], self.prom)
        self.assertEqual(state, "warm")
        self.assertTrue(any("SS0" in r for r in reasons))
        self.assertTrue(any("FEAT_OVR_PLM" in r for r in reasons))

    def test_chip_mismatch_is_reported(self):
        snap = {"driver": "none", "command": 3, "summary": {},
                "registers": {0x000000: {"name": "PMC", "value": 0x194000A1},
                              0x00823804: {"name": "PLM", "value": 0xFFFFFF8F},
                              0x0082381C: {"name": "SS0", "value": 0x44023025},
                              0x00823820: {"name": "SS1", "value": 0x7}}}
        state, reasons = cap.verdict(snap, {})
        self.assertEqual(state, "cold")
        self.assertTrue(any("chip id" in r for r in reasons))


class Reference(unittest.TestCase):
    def test_published_values_match_fixture(self):
        snaps = cap.parse_snapshots(load_fixture())
        rows = cap.compare_reference(snaps[0])
        wrong = [r for r in rows if r["match"] is False]
        self.assertEqual(wrong, [], "fixture disagrees with AD102_COLD_REF")
        matched = [r for r in rows if r["match"]]
        self.assertEqual(len(matched), 9)


class Output(unittest.TestCase):
    def setUp(self):
        self.log = load_fixture()
        self.snap = cap.select_cold_snapshot(cap.parse_snapshots(self.log))
        self.prom = cap.parse_prom(self.log)
        self.meta = {"captured_at": "2026-10-26T00:00:00+0000", "bdf": "0000:01:00.0",
                     "host": "test", "driver": None, "identity": {}, "prom": {},
                     "verdict": "cold", "resource0": None}

    def test_profile_has_captured_words(self):
        text = cap.emit_profile(self.meta, self.snap, self.prom)
        self.assertIn("#define PROFILE_PCI_DEVICE    0x0000  /* TODO */", text)
        self.assertIn("PROFILE_FEAT_SS0_COLD            0x44023025u", text)
        self.assertIn("PROFILE_FEAT_SS1_COLD            0x00000007u", text)
        self.assertIn("PROFILE_FEAT_PLM_COLD            0xffffff8fu", text)
        self.assertIn("PROFILE_PROM_HASH", text)
        self.assertIn("#endif", text)

    def test_profile_marks_unsampled_words(self):
        text = cap.emit_profile(self.meta, self.snap, self.prom)
        self.assertIn("PROFILE_GFW_PLM                  0x00000000u  /* not sampled */",
                      text)
        self.assertNotIn("/* TODO */  /* not sampled */", text)

    def test_admission_table_shape(self):
        text = cap.emit_admission_table(self.snap)
        lines = text.splitlines()
        table = [ln for ln in lines if ln.startswith("static const UINT32 offsets")]
        values = [ln for ln in lines if ln.startswith("static const UINT32 values")]
        self.assertEqual(len(table), 1)
        self.assertEqual(len(values), 1)
        self.assertEqual(table[0].count(","), len(cap.ADMISSION_OFFSETS) - 1)
        self.assertIn("0x4cb8f", values[0])
        self.assertIn("0x1ffffe00", values[0])


class RomParsing(unittest.TestCase):
    def test_prom_block_absent_in_excerpt(self):
        prom = cap.parse_prom(load_fixture())
        self.assertEqual(prom, {})

    def test_fwsec_line_parses(self):
        line = ("gpu_peek: SUCCESS: FWSEC-FRTS parsed from PROM! ucode_id=9 "
                "engine_mask=0x400 img_off=0x45488 img_size=0x10300 "
                "imem=0xf500 dmem=0xd80 sig_count=2 sig_versions=0x3\n")
        prom = cap.parse_prom(line)
        self.assertEqual(prom["fwsec"]["ucode_id"], 9)
        self.assertEqual(prom["fwsec"]["image_off"], 0x45488)
        self.assertEqual(prom["fwsec"]["dmem_size"], 0xD80)


if __name__ == "__main__":
    unittest.main()
