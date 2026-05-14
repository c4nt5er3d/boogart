# Boogart

Boogart is a small desktop companion prototype.

Phase 0 includes:

- Fake terminal setup UI with Tkinter
- Name input
- Windows-friendly path abstraction
- Placeholder `boogart.png` rendering
- `boogart_log.txt` writing

Run locally:

```bash
python3.11 -m boogart
```

Dialogue lives in `read.md`. Use headings in the form:

```md
## trigger.tone
- line here.
```

For baby-stage sounds, use:

```md
## vocalizations.trigger.stage
- mrrp.
```

Example triggers include `first_launch`, `food_found`, and `dead_boogart_found`.
Growth stages are `newborn`, `baby_kitten`, `kitten`, `young_cat`, `cat`,
`first_shift`, `changed`, and `final`.

Architecture notes:

- `boogart/world` scans shallow filenames and classifies symbolic tags without
  reading file contents.
- `boogart/mind` runs a tiny utility brain where actions score themselves and
  the highest valid action runs.
- `boogart/core/lifecycle.py` owns death, corpse rot, and delayed rebirth.
- `boogart/runtime.py` runs the heartbeat that loads state, ticks the brain,
  renders Boogart in its current folder, appends the log, and saves state.
- Boogart-owned files are tracked in state so cleanup can remove only files the
  game generated.
