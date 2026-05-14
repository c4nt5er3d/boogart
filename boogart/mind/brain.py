from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from boogart.core.growth import stage_for_created_at
from boogart.core.state import BoogartState
from boogart.mind.actions import DEFAULT_ACTIONS, BrainAction
from boogart.mind.context import BrainContext, BrainResult
from boogart.world.scanner import scan_folder


class UtilityBrain:
    def __init__(self, actions: tuple[BrainAction, ...] = DEFAULT_ACTIONS) -> None:
        self.actions = actions

    def tick(self, ctx: BrainContext) -> BrainResult:
        if ctx.state.lifecycle == "alive":
            ctx.state.stage = stage_for_created_at(ctx.state.birth_at, ctx.now).id

        scored = [(action.score(ctx), action) for action in self.actions]
        score, action = max(scored, key=lambda item: item[0])
        if score <= 0:
            return BrainResult("idle")
        result = action.run(ctx)
        ctx.state.updated_at = ctx.now.isoformat(timespec="seconds")
        return result


def tick_state(state: BoogartState, folder: Path, now: datetime | None = None, brain: UtilityBrain | None = None) -> BrainResult:
    current_time = now or datetime.now(timezone.utc)
    place, observations = scan_folder(folder, generated_files=state.generated_files)
    ctx = BrainContext(state=state, folder=folder, place=place, observations=observations, now=current_time)
    return (brain or UtilityBrain()).tick(ctx)
