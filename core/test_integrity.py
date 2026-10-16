import copy
import unittest

from core.integrity import (
    GENESIS_HASH, TransferRejected, append_entry, canonical_bytes,
    check_transfer, compute_hash, make_entry, verify_chain,
)


def build(owners):
    chain = []
    for o in owners:
        chain.append(append_entry(chain, {"owner_id": o, "name": "কাল্পনিক " + o}))
    return chain


class ChainTests(unittest.TestCase):
    def test_valid_chain(self):
        self.assertTrue(verify_chain(build(["A", "B", "C"])).ok)

    def test_empty_chain_is_valid(self):
        self.assertTrue(verify_chain([]).ok)

    def test_payload_tamper_detected(self):
        c = build(["A", "B", "C"])
        c[1]["payload"]["owner_id"] = "EVIL"
        r = verify_chain(c)
        self.assertFalse(r.ok)
        self.assertEqual(r.broken_at, 1)

    def test_tamper_and_rehash_breaks_next_link(self):
        c = build(["A", "B", "C"])
        c[1]["payload"]["owner_id"] = "EVIL"
        c[1]["hash"] = compute_hash(1, c[1]["prev_hash"], c[1]["payload"])
        r = verify_chain(c)
        self.assertFalse(r.ok)
        self.assertEqual(r.broken_at, 2)

    def test_delete_middle_detected(self):
        c = build(["A", "B", "C"])
        del c[1]
        self.assertFalse(verify_chain(c).ok)

    def test_reorder_detected(self):
        c = build(["A", "B", "C"])
        c[1], c[2] = c[2], c[1]
        self.assertFalse(verify_chain(c).ok)

    def test_truncation_needs_expected_head(self):
        c = build(["A", "B", "C"])
        head = c[-1]["hash"]
        self.assertTrue(verify_chain(c[:2]).ok)  # chain alone cannot see it
        self.assertFalse(verify_chain(c[:2], expected_head=head).ok)
        self.assertTrue(verify_chain(c, expected_head=head).ok)

    def test_first_entry_must_link_to_genesis(self):
        c = build(["A"])
        c[0]["prev_hash"] = "1" * 64
        self.assertFalse(verify_chain(c).ok)

    def test_malformed_inputs_never_crash(self):
        for bad in ([{}], [None], [{"seq": 0}], [{"seq": 0, "prev_hash": 1,
                    "hash": 2, "payload": {}}]):
            self.assertFalse(verify_chain(bad).ok)

    def test_uppercase_or_short_hash_rejected(self):
        c = build(["A"])
        c[0]["hash"] = c[0]["hash"].upper()
        self.assertFalse(verify_chain(c).ok)

    def test_key_order_does_not_matter(self):
        a = canonical_bytes({"x": 1, "y": 2})
        b = canonical_bytes({"y": 2, "x": 1})
        self.assertEqual(a, b)

    def test_bengali_payload_roundtrip(self):
        e = make_entry(0, GENESIS_HASH, {"name": "মো. ইমরান আলী"})
        self.assertTrue(verify_chain([e]).ok)

    def test_floats_rejected(self):
        with self.assertRaises(TypeError):
            compute_hash(0, GENESIS_HASH, {"area": 33.5})

    def test_entry_does_not_alias_caller_payload(self):
        p = {"owner_id": "A"}
        e = make_entry(0, GENESIS_HASH, p)
        p["owner_id"] = "EVIL"
        self.assertTrue(verify_chain([e]).ok)


class TransferTests(unittest.TestCase):
    def test_valid_transfer(self):
        c = build(["A"])
        self.assertEqual(check_transfer(c, "A", c[-1]["hash"]), c[-1]["hash"])

    def test_wrong_seller_rejected(self):
        c = build(["A"])
        with self.assertRaises(TransferRejected):
            check_transfer(c, "B", c[-1]["hash"])

    def test_double_sale_rejected(self):
        c = build(["A"])
        head_seen_by_both = c[-1]["hash"]
        # first buyer wins
        check_transfer(c, "A", head_seen_by_both)
        c.append(append_entry(c, {"owner_id": "B"}))
        # second sale from the same stale view must fail
        with self.assertRaises(TransferRejected):
            check_transfer(c, "A", head_seen_by_both)

    def test_tampered_chain_blocks_transfer(self):
        c = build(["A", "B"])
        c[0]["payload"]["owner_id"] = "EVIL"
        with self.assertRaises(TransferRejected):
            check_transfer(c, "B", c[-1]["hash"])

    def test_empty_chain_and_bad_head_rejected(self):
        with self.assertRaises(TransferRejected):
            check_transfer([], "A", "0" * 64)
        with self.assertRaises(TransferRejected):
            check_transfer(build(["A"]), "A", "not-a-hash")


if __name__ == "__main__":
    unittest.main()
