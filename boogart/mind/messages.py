from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from boogart.core.growth import parse_timestamp
from boogart.core.state import BoogartState
from boogart.mind.context import BrainResult


EVENT_ACTIONS = {
    "avoid_hazard",
    "die",
    "eat_corpse",
    "eat_food",
    "give_gift",
    "react_to_corpse",
    "rebirth",
    "seed_daily_hazard",
}


@dataclass(frozen=True)
class MessageDecision:
    text: str
    channel: str = "log"
    tier: int = 1
    prefix: str = "boogart"


class MessageDirector:
    def decisions(self, state: BoogartState, result: BrainResult, watcher_comments: list[str], now: datetime) -> list[MessageDecision]:
        decisions: list[MessageDecision] = []
        action_decision = self.action_decision(state, result, now)
        if action_decision:
            decisions.append(action_decision)

        for comment in watcher_comments:
            decision = self.watcher_decision(state, comment, now)
            if decision:
                decisions.append(decision)

        return decisions

    def action_decision(self, state: BoogartState, result: BrainResult, now: datetime) -> MessageDecision | None:
        text = result.message or result.action_id
        if result.action_id == "idle" or not text:
            return None
        if result.action_id == "vocalize":
            if not self.allowed(state, "vocalize", text, now, timedelta(minutes=8)):
                return None
            return MessageDecision(text=text, tier=1, prefix=self.prefix_for(state))

        if result.action_id in EVENT_ACTIONS:
            self.remember_line(state, text, now)
            return MessageDecision(text=text, tier=3, prefix=self.prefix_for(state))

        if not self.allowed(state, f"action:{result.action_id}", text, now, timedelta(minutes=5)):
            return None
        return MessageDecision(text=text, tier=1, prefix=self.prefix_for(state))

    def watcher_decision(self, state: BoogartState, comment: str, now: datetime) -> MessageDecision | None:
        if "quiet hour" in comment:
            self.remember_line(state, comment, now)
            return MessageDecision(text=comment, tier=4, prefix=self.prefix_for(state))
        if not self.allowed(state, "watcher", comment, now, timedelta(minutes=10)):
            return None
        return MessageDecision(text=comment, tier=1, prefix=self.prefix_for(state))

    def allowed(self, state: BoogartState, key: str, text: str, now: datetime, cooldown: timedelta) -> bool:
        cooldowns = message_cooldowns(state)
        previous = cooldowns.get(key)
        if previous and now - parse_timestamp(str(previous)) < cooldown:
            return False
        if any(item.get("text") == text for item in recent_messages(state) if isinstance(item, dict)):
            return False
        cooldowns[key] = now.isoformat(timespec="seconds")
        self.remember_line(state, text, now)
        return True

    def remember_line(self, state: BoogartState, text: str, now: datetime) -> None:
        recent = recent_messages(state)
        recent.append({"text": text, "at": now.isoformat(timespec="seconds")})
        del recent[:-20]

    def prefix_for(self, state: BoogartState) -> str:
        if state.corruption >= 60:
            return "SYSTEM COMPROMISE"
        if state.corruption >= 25:
            return "signal"
        return "boogart"


def message_cooldowns(state: BoogartState) -> dict[str, object]:
    raw = state.memory.setdefault("message_cooldowns", {})
    if not isinstance(raw, dict):
        raw = {}
        state.memory["message_cooldowns"] = raw
    return raw


def recent_messages(state: BoogartState) -> list[dict[str, object]]:
    raw = state.memory.setdefault("recent_messages", [])
    if not isinstance(raw, list):
        raw = []
        state.memory["recent_messages"] = raw
    return raw
