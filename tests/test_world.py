from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from boogart.world.classifiers import classify_path
from boogart.world.scanner import scan_folder


class WorldTests(unittest.TestCase):
    def test_classifier_tags_symbolic_filenames(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            names = [
                "fish.food",
                "slipperyfloor.hazard",
                "shiny_string.gift",
                "dead_boogart.png",
                "resume_final_FINAL.docx",
                "birthday_photo.jpg",
                "shortcut.lnk",
            ]
            for name in names:
                (folder / name).write_text("", encoding="utf-8")

            by_name = {name: classify_path(folder / name) for name in names}

            self.assertTrue(by_name["fish.food"].edible)
            self.assertTrue(by_name["slipperyfloor.hazard"].hazard)
            self.assertIn("gift", by_name["shiny_string.gift"].tags)
            self.assertTrue(by_name["dead_boogart.png"].corpse)
            self.assertIn("repeated_final", by_name["resume_final_FINAL.docx"].tags)
            self.assertIn("picture", by_name["birthday_photo.jpg"].tags)
            self.assertIn("personalish", by_name["birthday_photo.jpg"].tags)
            self.assertIn("shortcut", by_name["shortcut.lnk"].tags)

    def test_empty_folder_profile_feels_like_empty_room(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            place, observations = scan_folder(Path(tmp))

            self.assertEqual(observations, [])
            self.assertIn("empty_room", place.tags)


if __name__ == "__main__":
    unittest.main()
