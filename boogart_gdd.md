# Boogart GDD

## Pitch

Boogart is a cozy-horror desktop pet for PC. It lives as a PNG on the player's filesystem, eats `.food` offerings, wanders through safe user folders, leaves a sparse log, and becomes stranger when care is ignored.

The game should feel like a tiny thing sharing the machine, not like a dashboard. The player learns by watching files change.

## Player-Facing Files

- `boogart.png`: the live body.
- `boogart_dead.png`: the body after a real death.
- `log.txt`: sparse experience notes.
- `*.food`: player-made offerings that Boogart eats.
- occasional `.txt` notes and residue PNGs as rare traces.

Private engine state lives in the app data folder.

## First Session

The first Steam session must hook without punishing:

- Boogart appears on the Desktop.
- Boogart moves within a visible, shallow scope.
- The log changes.
- A `.food` interaction works.
- Hunger mood can escalate, but starvation death is blocked during the first two active hours.

## Care Loop

Hunger is a mood curve, not a simple punishment:

- `0-39`: calm, cute, exploratory.
- `40-69`: searching and food-aware.
- `70-89`: anxious, faster, subtly decayed.
- `90-99`: clear starvation warnings and `.food` hints.
- `100`: critical, active-time starvation timer starts.

Starvation death rules:

- first starvation death requires `72` active hours at hunger `100`
- later starvation deaths require `48` active hours at hunger `100`
- starvation deaths are capped to one per `7` active days
- feeding clears starvation progress

## Feeding

- `.food` lowers hunger by `55`.
- Old corpses lower hunger by `80` total across three bites.
- Bite one and bite two leave the corpse in place with bloodier body art and `corpse_bites` metadata.
- Bite three removes the corpse.
- Each corpse bite increases the live Boogart's bloody mouth/paw visual state up to `bloody3`.
- The most recent corpse is never immediately edible.
- Meals can produce rare comforting logs or residue.

## Body Interaction Rules

- Deleting the live body kills as `dead:deleted`.
- Starvation kills as `dead:starvation`.
- Moving the live body to Trash/Recycle is recoverable and alive.
- Archiving the live body as `boogart.zip`, `boogart.rar`, `boogart.7z`, `boogart.tar`, `boogart.tar.gz`, or `boogart.tgz` puts Boogart into `archived`.
- `archived` is a reversible containment state with muffled/folded terminal labels and sparse archive logs.
- Extracting a matching live PNG during the archive grace period recovers Boogart alive.
- If the archive remains sealed past the grace period, the missing body resolves as `dead:deleted`.
- Renaming is tolerated early and reacted to later.
- Copying is delayed and nondestructive.
- Identity mismatch is fatal only when the file is clearly another Boogart body.

## Metadata

Live bodies carry PNG `tEXt` metadata:

- `boogart_id`
- `generation`
- `birth_time`
- `stage`
- `lineage`
- `parent_id`
- `death_count`
- `copy_count`
- `boogart_artifact=body`
- `not_body=false`

Artifacts use `not_body=true` and must never be treated as the live creature.

Corpse PNGs use `boogart_artifact=corpse`, `not_body=true`, and `corpse_bites=0..2` while partially eaten. The live body keeps `stage` as the growth stage and uses `visual_state` plus `blood_level` for bloodied variants, so metadata recovery still sees it as the real body.

## Filesystem Boundaries

Boogart scans filenames only. It does not read file contents. Scans are shallow and bounded by depth and entry count. Generated files are capped:

- burrows: `1/day`, `48` total
- nest/residue artifacts: `120` total
- generated file manifest: `250` total

When caps are reached, Boogart should prefer logs, movement, or silence over creating more files.

Boogart does not inspect or unpack archive contents. Archive detection is based on nearby filenames only. Symlinks are ignored by scanners and rejected as live bodies so the game does not follow or rewrite linked targets. Metadata-stripped hash recovery is only allowed in safe locations such as the expected folder or Trash/Recycle, not arbitrary folders. Backward clock jumps pause active-time accounting instead of rewinding it.

## Live Terminal

`--live` renders a small status panel:

```text
BOOGART LIVE
age / mood / trust / hunger / wrongness
TODAY: recent events and logs
```

This is a dev and streamer-friendly view. The filesystem files remain the main game.

## Packaging

Steam build target is a single Windows executable produced by PyInstaller:

- entry: `boogart/__main__.py`
- spec: `packaging/Boogart.spec`
- output: `dist/Boogart.exe`
- bundled data: `boogart/rendering/assets/*.png`

The depot should not include source, tests, local sandbox state, caches, or generated player files.

## Release Gate

Release candidates must pass:

- unit test suite
- metadata smoke
- focused interaction matrix
- first-two-hours protection simulation
- 100-day no-feed soak under `15` starvation deaths and under `250` files
- 100-day fed-every-other-day soak with `0` starvation deaths
