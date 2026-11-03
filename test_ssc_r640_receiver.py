"""Offline R640 firmware auditing tests; proprietary image is gitignored."""
from __future__ import annotations
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FW = ROOT / "vendor-local/buds-fw/R640XXU0AZD2.bin"

spec = importlib.util.spec_from_file_location(
    "audit_r640_receiver", ROOT / "scripts/audit-r640-receiver.py"
)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


@unittest.skipUnless(FW.is_file(), "Original R640 firmware not installed locally")
class ReceiverAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = FW.read_bytes()
        cls.audit = module.inspect(cls.source)

    def test_provenance(self):
        self.assertEqual(self.audit["device"], "Samsung Galaxy Buds4 Pro (SM-R640)")
        self.assertEqual(self.audit["firmware_sha256"], module.SHA256)
        self.assertEqual(self.audit["firmware_config_vendor_id"], "0x00000075")
        self.assertEqual(self.audit["firmware_config_codec_id"], "0x0103")

    def test_uhq_decoding_branch_set(self):
        modes={x["info_byte"]:x for x in self.audit["modes"]}
        self.assertEqual(
            sorted(k for k,v in modes.items() if v["accepted_by_uhq_preparser"]),
            ["0xe0","0xe3","0xe6"]
        )
        self.assertEqual(modes["0xe0"]["minimum_accepted_bytes_in_initial_validator"],330)
        self.assertEqual(modes["0xe3"]["minimum_accepted_bytes_in_initial_validator"],660)
        self.assertEqual(modes["0xe6"]["minimum_accepted_bytes_in_initial_validator"],174)
        self.assertEqual(modes["0xe4"]["minimum_accepted_bytes_in_initial_validator"],484)
        self.assertFalse(modes["0xe4"]["handled_by_uhq_sequence_preparser"])
        self.assertTrue(self.audit["e4_passes_generic_initial_validator"])
        self.assertFalse(self.audit["preparser_caller_tests_return_value"])
        self.assertEqual(self.audit["observed_ssc_packet_queue_max_bytes"], 800)
        self.assertFalse(self.audit["e4_can_fit_unfragmented_in_observed_queue"])
        self.assertEqual(self.audit["dsp_e4_acceptance"], "not_verified")

    def test_rejects_unknown_firmware(self):
        with self.assertRaises(ValueError):
            module.inspect(b"not a Samsung firmware")
        tampered=bytearray(self.source)
        tampered[0x8d996]^=1
        with self.assertRaises(ValueError):
            module.inspect(bytes(tampered))



if __name__ == "__main__":
    unittest.main()
