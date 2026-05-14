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

Build a first Windows executable from Windows:

```powershell
.\scripts\build_windows.ps1 -Clean
```

The executable will be written to `dist\Boogart.exe`. GitHub Actions also
builds and uploads a `Boogart-windows` artifact on pushes to `main`.

Clean up Boogart-generated files and local state:

```powershell
boogart-cleanup --yes
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
- `boogart/world/watcher.py` stores shallow snapshots of Boogart's current
  folder only; it does not deep-map home folders or write to the clipboard.
- `wander_scope` controls how far Boogart may look: `desktop`, `marked`
  folders containing `.boog`, or bounded `home_rooms` such as Desktop,
  Documents, Downloads, Pictures, Music, and Videos.
- Tree scans are capped at depth 2, 100 files per folder, and 1000 total
  observations.
- Boogart-owned files are tracked in state so cleanup can remove only files the
  game generated.
