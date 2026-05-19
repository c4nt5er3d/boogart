# Boogart

Boogart is a cozy-horror desktop pet that lives in your files. The visible game is tiny on purpose:

- `boogart.png` is the body.
- `log.txt` is what he experiences.
- `.food` files are offerings.
- private state lives in the app data directory, not beside the player files.

The Steam promise is: a tiny desktop pet that wanders, eats offerings, leaves traces, and gets stranger when ignored.

## Current Feature Set

- First launch installs Boogart on the Desktop with a setup terminal.
- Heartbeats run quietly in the background and update movement, hunger, logs, notes, and body rendering.
- `--live` shows a compact terminal panel with age, mood, trust, hunger, wrongness, and recent events.
- Boogart scans filenames only. He does not read file contents.
- Movement is shallow, bounded, and biased toward Desktop/Downloads early so the first session stays legible.
- Hunger uses a five-stage mood curve. Starvation death is active-time based, protected for the first two hours, and capped by cooldown.
- Feeding with `.food` lowers hunger by `55`, clears starvation progress, and can leave small residue artifacts.
- Old corpses can be eaten for a larger hunger reduction, but the most recent body is protected from immediate corpse eating.
- Deleting the live body kills as `dead:deleted`; starvation kills as `dead:starvation`.
- Trash/Recycle Bin recovery treats a moved body as recoverable and alive.
- Copy reactions are delayed, nondestructive, and based on body metadata.
- Generated file churn is capped so long-running players do not get hundreds of artifacts.
- Cleanup removes generated files, private state, lock files, debug logs, and the hidden tether.

## Metadata Contract

Every live Boogart PNG carries `tEXt` metadata:

- `boogart_id`
- `generation`
- `birth_time`
- `stage`
- `lineage`
- `parent_id`
- `death_count`
- `copy_count`
- `boogart_artifact`
- `not_body`

Body detection only accepts metadata marked as a real body. Residue, nest artifacts, and dead bodies are marked so they cannot be mistaken for the live creature during recovery or copy reactions.

## Run Locally

```bash
python3 -m boogart
```

Run one heartbeat:

```bash
python3 -m boogart --once --name jay
```

Run a fast finite simulation:

```bash
python3 -m boogart --simulate 48 --step-minutes 15 --name jay
```

Run a live accelerated loop:

```bash
python3 -m boogart --dev-fast --live --name jay
```

Run safely inside a sandbox folder:

```bash
python3 -m boogart --sandbox /tmp/boogart-sandbox --dev-fast --live --name jay
```

Clean up generated files and private state:

```bash
boogart-cleanup --yes
```

## Steam / Single Exe Build

The Windows build uses PyInstaller and bundles `boogart/rendering/assets/*.png` through `packaging/Boogart.spec`.

From Windows PowerShell:

```powershell
.\scripts\build_windows.ps1 -Clean
```

Manual equivalent:

```powershell
py -3.11 -m pip install --upgrade pip
py -3.11 -m pip install -e .
py -3.11 -m pip install pyinstaller
py -3.11 -m unittest discover -s tests
py -3.11 -m PyInstaller packaging/Boogart.spec --clean --noconfirm
```

The executable is written to:

```text
dist/Boogart.exe
```

Steam depot candidate:

- `dist/Boogart.exe`
- no source tree, tests, sandbox files, cache files, or local state

## Release

For public Windows downloads, use the GitHub Release workflow. Maintainers can publish by pushing a version tag:

```bash
git tag v0.1.4
git push origin v0.1.4
```

The release workflow uploads:

- `Boogart.exe`
- `Boogart-windows.zip`

## Verification

Before packaging or release:

```bash
pytest -q
PYTHONPYCACHEPREFIX=/private/tmp/boogart_pycache python3 -m compileall -q boogart tests
git diff --check
```

Recent readiness sims:

- focused interaction matrix: food, copy reaction, Trash recovery, full deletion, respawn, latest corpse preservation, starvation death, live panel
- blank 100-day soak: `14` starvation deaths, final alive, `191` files total
- fed-every-other-day 100-day soak: `0` starvation deaths
