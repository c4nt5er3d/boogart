from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from boogart.core.state import BoogartState
from boogart.mind.context import BrainResult
from boogart.mind.messages import MessageDirector


class MessageDirectorTests(unittest.TestCase):
    def test_vocalize_has_cooldown(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        state = BoogartState.new("jay")
        director = MessageDirector()

        first = director.decisions(state, BrainResult("vocalize", "mrrp"), [], now)
        second = director.decisions(state, BrainResult("vocalize", "mrrp"), [], now + timedelta(minutes=1))

        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])

    def test_event_actions_bypass_cooldown(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        state = BoogartState.new("jay")
        director = MessageDirector()

        first = director.decisions(state, BrainResult("eat_food", "ate fish.food"), [], now)
        second = director.decisions(state, BrainResult("eat_food", "ate milk.food"), [], now + timedelta(seconds=5))

        self.assertEqual(first[0].tier, 3)
        self.assertEqual(second[0].text, "ate milk.food")

    def test_watcher_comments_cool_down(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        state = BoogartState.new("jay")
        director = MessageDirector()

        first = director.decisions(state, BrainResult("idle"), ["this room changed."], now)
        second = director.decisions(state, BrainResult("idle"), ["this room changed."], now + timedelta(minutes=1))

        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])

    def test_quiet_hour_comment_is_major_tier(self) -> None:
        now = datetime(2026, 1, 1, 3, tzinfo=timezone.utc)
        state = BoogartState.new("jay")

        decisions = MessageDirector().decisions(state, BrainResult("idle"), ["i was awake during the quiet hour."], now)

        self.assertEqual(decisions[0].tier, 4)


if __name__ == "__main__":
    unittest.main()
