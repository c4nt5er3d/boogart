# Boogart

Boogart is a cozy-horror desktop pet that lives in your files. The visible game is tiny on purpose:

- `boogart.png` is the body.
- `log.txt` is what he experiences.
- `.food` files are offerings.
- private state lives in the app data directory, not beside the player files.

The Steam promise is: a tiny file-pet that lives in your folders, accepts offerings, wanders when you are not looking, and slowly proves it understands more about your machine than it should.

## Current Feature Set

- First launch installs Boogart on the Desktop with a setup terminal.
- The default run shows the PySide6 Pet Monitor: body preview, current folder, cozy mood, hunger/trust meters, recent events, `Pet`, `Call`, `Open Folder`, `Pause`, and `Quit`.
- `--background` keeps the old quiet daemon behavior for players who do not want a window.
- Heartbeats update movement, hunger, logs, notes, and growth-stage body rendering.
- `--live` shows a compact terminal panel with age, mood, place, trust, hunger, and recent events.
- Boogart scans filenames only. He does not read file contents.
- Movement is shallow, bounded, and biased toward Desktop/Downloads early so the first session stays legible.
- The first visible folder move is scheduled in the first-session hook window, normally `8-20` active minutes after launch.
- Hunger uses a five-stage mood curve. Starvation death is active-time based, protected for the first two hours, and capped by cooldown.
- Feeding with `.food` lowers hunger by `55`, clears starvation progress, and can leave small residue artifacts.
- The first feeding stays fast for demo clarity; later offerings can occasionally be watched for hours before Boogart eats them.
- Old corpses can be eaten for a larger hunger reduction, but the most recent body is protected from immediate corpse eating.
- Deleting the live body kills as `dead:deleted`; starvation kills as `dead:starvation`.
- Trash/Recycle Bin recovery treats a moved body as recoverable and alive.
- If the body disappears beside `boogart.zip`, `boogart.rar`, `boogart.7z`, `boogart.tar`, `boogart.tar.gz`, or `boogart.tgz`, Boogart enters `archived` instead of dying immediately.
- Extracting a matching `boogart.png` during the archive grace period recovers him alive.
- Copy reactions are delayed, nondestructive, and based on body metadata.
- Symlinks are ignored so Boogart never follows or rewrites linked targets.
- Backward clock jumps do not rewind or inflate active-time hunger/starvation accounting.
- Generated file churn is capped so long-running players do not get hundreds of artifacts.
- A one-time stray artifact can appear beside Boogart as `second_body.png`; it carries matching identity metadata but is marked `not_body=true`, so it cannot be mistaken for the live creature.
- Once per save, Boogart can make one safe unusual move into a deeper allowed folder and leave a longer log line.
- The live `boogart.png` is intentionally simple: it changes by age/growth stage, not idle animation. Care feedback lives in the Pet Monitor and filesystem rituals.
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

Live body metadata stays stable between growth-stage changes. Corpse and artifact files may carry extra metadata such as `visual_state`, `artifact_kind`, or `corpse_bites`. Body detection only accepts metadata marked as a real body, so residue, nest artifacts, stray files, and dead bodies cannot be mistaken for the live creature during recovery or copy reactions.

## Sprite Asset Contract

Boogart works with placeholder fallbacks, but Steam art should provide these transparent PNGs in `boogart/rendering/assets/`:

Living bodies:

- `kitten.png`
- `cat.png`
- `shifting.png`
- `wrong.png`
- `corrupt.png`
- `final.png`

Living pose variants and bloody living variants are no longer required. The Pet Monitor provides moment-to-moment feedback while the live PNG stays readable as a stable filesystem body.

Dead bodies:

- `kitten_dead.png`
- `cat_dead.png`
- `shifting_dead.png`
- `wrong_dead.png`
- `corrupt_dead.png`
- `final_dead.png`
- `husk.png`

Bitten dead bodies:

- `kitten_dead_bite1.png`, `kitten_dead_bite2.png`, `kitten_dead_bite3.png`
- `cat_dead_bite1.png`, `cat_dead_bite2.png`, `cat_dead_bite3.png`
- `shifting_dead_bite1.png`, `shifting_dead_bite2.png`, `shifting_dead_bite3.png`
- `wrong_dead_bite1.png`, `wrong_dead_bite2.png`, `wrong_dead_bite3.png`
- `corrupt_dead_bite1.png`, `corrupt_dead_bite2.png`, `corrupt_dead_bite3.png`
- `final_dead_bite1.png`, `final_dead_bite2.png`, `final_dead_bite3.png`
- `husk_bite1.png`, `husk_bite2.png`, `husk_bite3.png`

Residue:

- `bone.png`
- optional future variants: `crumbs.png`, `dust.png`

All body sprites should share the same canvas size and alignment. Recommended source size is `512x512`; `256x256` is acceptable. Do not add identity metadata to source art files; Boogart writes runtime metadata when it renders the player-facing PNG.

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

Run without the watch window:

```bash
python3 -m boogart --background --name jay
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
git tag v0.1.6
git push origin v0.1.6
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
- first-session hook coverage: static live PNG, first visible movement schedule, delayed food, one-time stray artifact, safe unusual movement, pet monitor actions
