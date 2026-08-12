import tempfile
import unittest
from pathlib import Path


class SourceFileStoreTests(unittest.TestCase):
    def test_create_preserves_original_bytes_and_metadata(self):
        from core.source_file_store import SourceFileStore

        with tempfile.TemporaryDirectory() as tmp:
            store = SourceFileStore(Path(tmp))
            content = b"%PDF-1.4\nsource-page-marker\n%%EOF"

            record = store.create("Candidate Resume.PDF", content, "application/pdf")

            self.assertRegex(record["source_file_id"], r"^rf_[a-f0-9]{32}$")
            self.assertEqual(record["file_name"], "Candidate Resume.PDF")
            self.assertEqual(record["suffix"], ".pdf")
            self.assertEqual(record["mime_type"], "application/pdf")
            self.assertEqual(record["byte_count"], len(content))
            self.assertEqual(store.path_for(record["source_file_id"]).read_bytes(), content)
            self.assertEqual(store.load(record["source_file_id"])["content_hash"], record["content_hash"])

    def test_same_content_is_deduplicated_without_changing_bytes(self):
        from core.source_file_store import SourceFileStore

        with tempfile.TemporaryDirectory() as tmp:
            store = SourceFileStore(Path(tmp))
            first = store.create("resume.pdf", b"same-pdf", "application/pdf")
            second = store.create("renamed.pdf", b"same-pdf", "application/pdf")

            self.assertEqual(first["source_file_id"], second["source_file_id"])
            self.assertEqual(store.path_for(first["source_file_id"]).read_bytes(), b"same-pdf")

    def test_rejects_unsupported_source_format(self):
        from core.source_file_store import SourceFileStore

        with tempfile.TemporaryDirectory() as tmp:
            store = SourceFileStore(Path(tmp))
            with self.assertRaisesRegex(ValueError, "Unsupported source file format"):
                store.create("resume.exe", b"not-a-resume")

    def test_rejects_invalid_source_file_id(self):
        from core.source_file_store import SourceFileStore

        with tempfile.TemporaryDirectory() as tmp:
            store = SourceFileStore(Path(tmp))
            with self.assertRaisesRegex(ValueError, "Invalid source_file_id"):
                store.load("../../resume")


if __name__ == "__main__":
    unittest.main()
