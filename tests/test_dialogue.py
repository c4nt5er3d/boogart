from __future__ import annotations

import unittest

from boogart.content.dialogue import parse_dialogue_markdown


class DialogueTests(unittest.TestCase):
    def test_baby_stage_uses_vocalizations(self) -> None:
        book = parse_dialogue_markdown(
            """
## vocalizations.first_launch.newborn
- mrrp.

## first_launch.cute
- you made room for me.
"""
        )

        self.assertEqual(book.choose_for_stage("first_launch", "newborn", tone="cute"), "mrrp.")

    def test_later_stage_uses_dialogue(self) -> None:
        book = parse_dialogue_markdown(
            """
## vocalizations.first_launch.newborn
- mrrp.

## first_launch.cute
- you made room for me.
"""
        )

        self.assertEqual(book.choose_for_stage("first_launch", "kitten", tone="cute"), "you made room for me.")

    def test_stage_specific_dialogue_can_be_selected(self) -> None:
        book = parse_dialogue_markdown(
            """
## dialogue.first_launch.kitten.cute
- small words.

## dialogue.first_launch.cat.cute
- bigger words.
"""
        )

        self.assertEqual(book.choose_for_stage("first_launch", "kitten", tone="cute"), "small words.")
        self.assertEqual(book.choose_for_stage("first_launch", "cat", tone="cute"), "bigger words.")


if __name__ == "__main__":
    unittest.main()
