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
