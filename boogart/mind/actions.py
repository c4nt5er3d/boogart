from __future__ import annotations

import random
from datetime import timedelta
from pathlib import Path

from boogart.core.lifecycle import (
    DeathCause,
    can_rebirth,
    first_death_cause,
    kill_boogart,
    rebirth,
    refresh_corpse_rot,
    track_generated_file,
)
from boogart.mind.context import BrainContext, BrainResult
from boogart.world.hazards import create_daily_hazard


class BrainAction:
    id = "action"

    def score(self, ctx: BrainContext) -> int:
        raise NotImplementedError

    def run(self, ctx: BrainContext) -> BrainResult:
        raise NotImplementedError


class RebirthAction(BrainAction):
    id = "rebirth"

    def score(self, ctx: BrainContext) -> int:
        return 10_000 if can_rebirth(ctx.state, ctx.now) else 0

    def run(self, ctx: BrainContext) -> BrainResult:
        old_incarnation = ctx.state.incarnation_id
        rebirth(ctx.state, ctx.now)
        return BrainResult(self.id, f"reborn after {old_incarnation}")


class DieAction(BrainAction):
    id = "die"

    def score(self, ctx: BrainContext) -> int:
        if ctx.state.lifecycle != "alive":
            return 0
        return 9_000 if first_death_cause(ctx.state, ctx.place, ctx.observations, ctx.now) else 0

    def run(self, ctx: BrainContext) -> BrainResult:
        cause = first_death_cause(ctx.state, ctx.place, ctx.observations, ctx.now) or DeathCause("unknown", "something ended")
        path = kill_boogart(ctx.state, ctx.folder, cause, ctx.now)
        return BrainResult(self.id, f"death:{cause.id}", path)


class EatCorpseAction(BrainAction):
    id = "eat_corpse"

    def score(self, ctx: BrainContext) -> int:
        if ctx.state.lifecycle != "alive":
            return 0
        if ctx.state.hunger < 95:
            return 0
        if ctx.place.food_count:
            return 0
        if ctx.state.corruption < 40 and ctx.state.stage not in {"changed", "final"}:
            return 0
        return 800 if self._available_corpse(ctx) else 0

    def run(self, ctx: BrainContext) -> BrainResult:
        corpse = self._available_corpse(ctx)
        if not corpse:
            return BrainResult(self.id, "no corpse")

        corpse_path = Path(str(corpse["corpse_path"]))
        stain_path = corpse_path.with_name("stain_boogart.png")
        if corpse_path.exists():
            corpse_path.replace(stain_path)
            track_generated_file(ctx.state, stain_path)

        corpse["eaten"] = True
        ctx.state.corruption = min(100, ctx.state.corruption + 25)
        ctx.state.memory["ate_dead_boogart"] = True
        ctx.state.global_memory["ate_corpse"] = True
        return BrainResult(self.id, "corpse eaten", stain_path)

    def _available_corpse(self, ctx: BrainContext) -> dict[str, object] | None:
        for corpse in ctx.state.corpse_records:
            if not corpse.get("eaten") and corpse.get("folder_path") == str(ctx.folder):
                return corpse
        return None


class EatFoodAction(BrainAction):
    id = "eat_food"

    def score(self, ctx: BrainContext) -> int:
        if ctx.state.lifecycle != "alive":
            return 0
        return 500 + ctx.state.hunger if any(item.edible for item in ctx.observations) else 0

    def run(self, ctx: BrainContext) -> BrainResult:
        foods = sorted((item for item in ctx.observations if item.edible), key=lambda item: food_score(item.name), reverse=True)
        if not foods:
            return BrainResult(self.id, "no food")

        food = foods[0]
        if food.path.exists():
            food.path.unlink()
        ctx.state.hunger = max(0, ctx.state.hunger - 45)
        ctx.state.affection += 1
        ctx.state.memory["last_food_eaten"] = food.name
        return BrainResult(self.id, f"ate {food.name}", food.path)


class AvoidHazardAction(BrainAction):
    id = "avoid_hazard"

    def score(self, ctx: BrainContext) -> int:
        if ctx.state.lifecycle != "alive":
            return 0
        return 300 + ctx.place.hazard_count if ctx.place.hazard_count else 0

    def run(self, ctx: BrainContext) -> BrainResult:
        ctx.state.memory["saw_hazard_at"] = str(ctx.folder)
        ctx.state.neglect += 1
        return BrainResult(self.id, "unsafe here")


class SeedDailyHazardAction(BrainAction):
    id = "seed_daily_hazard"

    def score(self, ctx: BrainContext) -> int:
        if ctx.state.lifecycle != "alive":
            return 0
        today = ctx.now.date().isoformat()
        if ctx.state.memory.get("last_hazard_day") == today:
            return 0
        if ctx.state.stage in {"newborn", "baby_kitten"}:
            return 0
        return 180

    def run(self, ctx: BrainContext) -> BrainResult:
        path = create_daily_hazard(ctx.folder, ctx.now.date(), ctx.state.run_id)
        track_generated_file(ctx.state, path)
        ctx.state.memory["last_hazard_day"] = ctx.now.date().isoformat()
        return BrainResult(self.id, f"hazard:{path.name}", path)


class ReactToCorpseAction(BrainAction):
    id = "react_to_corpse"

    def score(self, ctx: BrainContext) -> int:
        if ctx.state.lifecycle != "alive":
            return 0
        return 250 if ctx.place.corpse_count else 0

    def run(self, ctx: BrainContext) -> BrainResult:
        refresh_corpse_rot(ctx.state, ctx.now)
        for corpse in ctx.state.corpse_records:
            if corpse.get("folder_path") == str(ctx.folder) and not corpse.get("eaten"):
                corpse["seen"] = True
                ctx.state.memory["saw_dead_boogart"] = True
                return BrainResult(self.id, f"corpse:{corpse.get('rot_stage')}")
        return BrainResult(self.id, "corpse seen")


class GiveGiftAction(BrainAction):
    id = "give_gift"
    gift_names = ("soft_purr.txt", "shiny_string.gift", "small_thank_you.txt", "nap_place.txt")

    def score(self, ctx: BrainContext) -> int:
        if ctx.state.lifecycle != "alive":
            return 0
        if ctx.state.stage in {"newborn", "baby_kitten"}:
            return 0
        last_gift = ctx.state.memory.get("last_gift_at")
        if last_gift and ctx.now - _parse_datetime(str(last_gift)) < timedelta(hours=12):
            return 0
        return 120 + ctx.state.affection * 5

    def run(self, ctx: BrainContext) -> BrainResult:
        rng = random.Random(f"{ctx.state.incarnation_id}:{ctx.now.date().isoformat()}:gift")
        name = rng.choice(self.gift_names)
        path = ctx.folder / name
        if not path.exists():
            path.write_text("for you\n", encoding="utf-8")
        track_generated_file(ctx.state, path)
        ctx.state.memory["last_gift_at"] = ctx.now.isoformat(timespec="seconds")
        return BrainResult(self.id, f"gift:{name}", path)


class VocalizeAction(BrainAction):
    id = "vocalize"

    def score(self, ctx: BrainContext) -> int:
        return 10 if ctx.state.lifecycle == "alive" else 0

    def run(self, ctx: BrainContext) -> BrainResult:
        return BrainResult(self.id, "mrrp")


DEFAULT_ACTIONS: tuple[BrainAction, ...] = (
    RebirthAction(),
    DieAction(),
    EatCorpseAction(),
    EatFoodAction(),
    AvoidHazardAction(),
    ReactToCorpseAction(),
    GiveGiftAction(),
    SeedDailyHazardAction(),
    VocalizeAction(),
)


def food_score(name: str) -> int:
    lowered = name.lower()
    score = 10
    if any(word in lowered for word in ("fish", "milk", "chicken", "treat")):
        score += 20
    if any(word in lowered for word in ("battery", "glass", "wire", "dead_boogart")):
        score -= 30
    if "nothing" in lowered:
        score -= 10
    return score


def _parse_datetime(value: str):
    from boogart.core.growth import parse_timestamp

    return parse_timestamp(value)
