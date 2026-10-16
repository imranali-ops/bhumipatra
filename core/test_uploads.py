import unittest

from core.uploads import (
    MAX_BYTES, UploadRejected, detect_kind, safe_display_name, sha256_hex, validate_upload,
)

PDF = b"%PDF-1.4\n" + b"0" * 200
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 200
JPG = b"\xff\xd8\xff\xe0" + b"0" * 200


class UploadTests(unittest.TestCase):
    def test_valid_types(self):
        self.assertEqual(validate_upload(PDF), "pdf")
        self.assertEqual(validate_upload(PNG), "png")
        self.assertEqual(validate_upload(JPG), "jpeg")

    def test_disguised_files_rejected(self):
        for bad in (b"MZ" + b"0" * 200,                       # Windows executable
                    b"<html><script>alert(1)</script></html>" + b" " * 100,
                    b"#!/bin/sh\nrm -rf /\n" + b" " * 100,
                    b"PK\x03\x04" + b"0" * 200,                 # zip / office file
                    b"GIF89a" + b"0" * 200):
            with self.assertRaises(UploadRejected):
                validate_upload(bad)

    def test_size_limits(self):
        with self.assertRaises(UploadRejected):
            validate_upload(b"")
        with self.assertRaises(UploadRejected):
            validate_upload(b"%PDF-")
        with self.assertRaises(UploadRejected):
            validate_upload(b"%PDF-" + b"0" * MAX_BYTES)
        self.assertEqual(validate_upload(b"%PDF-" + b"0" * (MAX_BYTES - 5)), "pdf")

    def test_detect_kind_needs_magic_at_start(self):
        self.assertIsNone(detect_kind(b"xx%PDF-"))

    def test_display_name_cannot_traverse_or_inject(self):
        self.assertEqual(safe_display_name("../../etc/passwd"), "passwd")
        self.assertEqual(safe_display_name("C:\\Users\\x\\deed.pdf"), "deed.pdf")
        self.assertEqual(safe_display_name("a\x00b<script>.pdf"), "abscript.pdf")
        self.assertEqual(safe_display_name("..."), "document")
        self.assertEqual(safe_display_name(""), "document")
        self.assertEqual(safe_display_name("দলিল নমুনা.pdf"), "দলিল নমুনা.pdf")
        self.assertEqual(len(safe_display_name("a" * 500)), 120)
        self.assertNotIn("\n", safe_display_name("line1\nline2.pdf"))

    def test_sha256(self):
        self.assertEqual(sha256_hex(b"abc"),
                         "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")


if __name__ == "__main__":
    unittest.main()
