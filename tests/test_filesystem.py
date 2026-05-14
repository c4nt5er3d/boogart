from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from boogart.core.filesystem import FilePolicyError, FileSystemAdapter
from boogart.core.state import BoogartState


class FileSystemAdapterTests(unittest.TestCase):
    def test_delete_food_allows_only_food_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fs = FileSystemAdapter((root,))
            food = root / "fish.food"
            document = root / "notes.txt"
            food.write_text("", encoding="utf-8")
            document.write_text("", encoding="utf-8")

            fs.delete_food(food)

            self.assertFalse(food.exists())
            with self.assertRaises(FilePolicyError):
                fs.delete_food(document)
            self.assertTrue(document.exists())

    def test_write_owned_tracks_generated_files(self) -> None:
        state = BoogartState.new("jay")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fs = FileSystemAdapter((root,))
            path = root / "soft_purr.txt"

            fs.write_owned_text(state, path, "for you\n")

            self.assertTrue(path.exists())
            self.assertIn(str(path), state.generated_files)

    def test_refuses_write_outside_allowed_roots(self) -> None:
        state = BoogartState.new("jay")
        with tempfile.TemporaryDirectory() as allowed, tempfile.TemporaryDirectory() as denied:
            fs = FileSystemAdapter((Path(allowed),))

            with self.assertRaises(FilePolicyError):
                fs.write_owned_text(state, Path(denied) / "bad.txt", "no\n")

    def test_delete_owned_rejects_untracked_user_file(self) -> None:
        state = BoogartState.new("jay")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fs = FileSystemAdapter((root,))
            user_file = root / "project.txt"
            user_file.write_text("", encoding="utf-8")

            with self.assertRaises(FilePolicyError):
                fs.delete_owned(state, user_file)
            self.assertTrue(user_file.exists())


if __name__ == "__main__":
    unittest.main()
