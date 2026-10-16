import base64
import os
import unittest

from core.signing import (
    load_private_key, public_key_of, sign_checkpoint, verify_checkpoint,
)

H = "a" * 64


class SigningTests(unittest.TestCase):
    def setUp(self):
        self.key = load_private_key(base64.b64encode(os.urandom(32)).decode())
        self.pub = public_key_of(self.key)

    def test_roundtrip(self):
        sig = sign_checkpoint(self.key, "p1", 3, H)
        self.assertTrue(verify_checkpoint(self.pub, "p1", 3, H, sig))

    def test_any_changed_field_fails(self):
        sig = sign_checkpoint(self.key, "p1", 3, H)
        self.assertFalse(verify_checkpoint(self.pub, "p2", 3, H, sig))
        self.assertFalse(verify_checkpoint(self.pub, "p1", 4, H, sig))
        self.assertFalse(verify_checkpoint(self.pub, "p1", 3, "b" * 64, sig))

    def test_other_key_fails(self):
        other = load_private_key(base64.b64encode(os.urandom(32)).decode())
        sig = sign_checkpoint(other, "p1", 3, H)
        self.assertFalse(verify_checkpoint(self.pub, "p1", 3, H, sig))

    def test_garbage_signature_does_not_crash(self):
        for bad in ("", "zz", "00" * 10, "00" * 64, None):
            self.assertFalse(verify_checkpoint(self.pub, "p1", 3, H, bad))

    def test_bad_key_rejected(self):
        for bad in ("not base64!!", base64.b64encode(b"short").decode()):
            with self.assertRaises(ValueError):
                load_private_key(bad)

    def test_bad_inputs_rejected(self):
        with self.assertRaises(ValueError):
            sign_checkpoint(self.key, "p1", -1, H)
        with self.assertRaises(ValueError):
            sign_checkpoint(self.key, "p1", 1, "short")


if __name__ == "__main__":
    unittest.main()
