# Boogart

Boogart is a small desktop companion that lives on the file system. The game is intentionally tiny on the surface:

- `boogart.png` is the body.
- `log.txt` is what he experiences.
- `state.json` is private engine state in the app data directory.

Everything else exists to keep those files current without turning the experience into a dashboard.

## Current Mechanics

- First launch shows the plain setup terminal from the GDD.
- Boogart starts on the Desktop as `boogart.png`.
- The log starts with one simple `mrrp.` line.
- Heartbeats run quietly and only log up to three entries per day.
- Boogart eats `.food` files found in a shallow, bounded Desktop/Downloads scan.
- Movement uses jittered intervals and sometimes intentionally does nothing.
- He may drop at most one `hey*.txt` file per day.
- If `boogart.png` is deleted, `boogart_dead.png` is left behind.
- After 48 hours dead, a missing corpse is replaced by `boogart_husk.png`.
- Copy reactions are delayed and create `too many.txt` beside detected copies.
- PNG files include hidden text metadata for identity, lineage, generation, birth time, stage, copy count, and death count.

## Boundaries

Boogart scans filenames only. He does not read file contents, modify unrelated files, open browsers, play jumpscares, or surface internal stats. The scanner is capped by depth and entry count, and common cloud-sync/system-heavy folders are avoided.

## Run Locally

```bash
python3 -m boogart
```

Run one heartbeat without opening the setup terminal:

```bash
python3 -m boogart --once --name jay
```

Run a fast local playtest. This creates Boogart if needed, speeds up timers, runs a finite number of heartbeats, prints a short summary, and exits:

```bash
python3 -m boogart --simulate 48 --step-minutes 15 --name jay
```

For a live accelerated loop:

```bash
python3 -m boogart --dev-fast --name jay
```

Clean up generated files and private state:

```bash
boogart-cleanup --yes
```

## Tests

```bash
pytest -q
```
