from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

from boogart.core.growth import STAGE_IDS, VOCALIZATION_ONLY_STAGES


@dataclass(frozen=True)
class DialogueLine:
    kind: str
    trigger: str
    tone: str
    stage: str | None
    text: str


class DialogueBook:
    def __init__(self, lines: list[DialogueLine]) -> None:
        self.lines = lines

    def for_trigger(
        self,
        trigger: str,
        tone: str | None = None,
        kind: str | None = None,
        stage: str | None = None,
    ) -> list[DialogueLine]:
        return [
            line
            for line in self.lines
            if line.trigger == trigger
            and (tone is None or line.tone == tone)
            and (kind is None or line.kind == kind)
            and (stage is None or line.stage is None or line.stage == stage)
        ]

    def choose(
        self,
        trigger: str,
        tone: str | None = None,
        seed: str | None = None,
        kind: str | None = None,
        stage: str | None = None,
    ) -> str:
        matches = self.for_trigger(trigger, tone=tone, kind=kind, stage=stage)
        if not matches:
            return ""

        rng = random.Random(seed)
        return rng.choice(matches).text

    def choose_for_stage(
        self,
        trigger: str,
        stage: str,
        tone: str | None = None,
        seed: str | None = None,
    ) -> str:
        if stage in VOCALIZATION_ONLY_STAGES:
            return self.choose(trigger, seed=seed, kind="vocalizations", stage=stage)

        return (
            self.choose(trigger, tone=tone, seed=seed, kind="dialogue", stage=stage)
            or self.choose(trigger, tone=tone, seed=seed, stage=stage)
        )


def default_dialogue_path() -> Path:
    return Path(__file__).resolve().parents[2] / "read.md"


def load_dialogue(path: Path | None = None) -> DialogueBook:
    source = path or default_dialogue_path()
    if not source.exists():
        return DialogueBook([])

    return parse_dialogue_markdown(source.read_text(encoding="utf-8"))


def parse_dialogue_markdown(markdown: str) -> DialogueBook:
    lines: list[DialogueLine] = []
    kind = ""
    trigger = ""
    tone = ""
    stage: str | None = None

    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            kind, trigger, tone, stage = parse_heading(line[3:].strip())
            continue

        if line.startswith("- ") and trigger and tone:
            text = line[2:].strip()
            if text:
                lines.append(DialogueLine(kind=kind, trigger=trigger, tone=tone, stage=stage, text=text))

    return DialogueBook(lines)


def parse_heading(heading: str) -> tuple[str, str, str, str | None]:
    parts = [normalize_key(part) for part in heading.split(".") if part.strip()]
    if not parts:
        return "dialogue", "", "default", None

    kind = "dialogue"
    if parts[0] in {"dialogue", "vocalizations"}:
        kind = parts.pop(0)

    if not parts:
        return kind, "", "default", None

    trigger = parts.pop(0)
    tone = "default"
    stage = None

    for part in parts:
        if part in STAGE_IDS:
            stage = part
        else:
            tone = part

    return kind, trigger, tone, stage


def normalize_key(value: str) -> str:
    return value.strip().lower().replace(" ", "_").replace("-", "_")
