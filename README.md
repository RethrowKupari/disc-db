# Disc → plastic dropdown database

Data for a two-step picker: choose a disc, then choose from the plastics that disc is made in.
`dropdown_db.json` is the file the app ships; everything else here exists to build it.

## Quick start

```bash
pip install -r requirements.txt
python build_dropdown_db.py
```

The build reads `sourcedata/` and the three config CSVs, then rewrites the four output files
next to the script. It runs from any folder on any OS, and with unchanged inputs it produces
byte-identical output, so `git diff` after a build shows exactly what your edit changed.

Options: `--src DIR` reads the source CSVs from elsewhere; `--out DIR` writes outputs (plus a
copy of the config) to another folder instead of the repo.

## How it works

The source data has no disc-level plastic list: it knows which plastics each **manufacturer**
makes, not which **molds** each plastic is run in. The build therefore starts from every
disc × plastic combination within a manufacturer and narrows it down in two steps:

1. **Disc-type rules** (`plastic_rules.csv`): each plastic is limited to the disc types it is
   actually made in, e.g. the Latitude 64 Zero line is putters only.
2. **Per-disc overrides** (`overrides.csv`): exceptions a type rule can't express, e.g. the
   Discmania DD3 has no Active Premium run.

Every pair with `source = rule` in `disc_plastics.csv` is therefore an inference, not a
verified fact. Treat it as a good default to correct, not as ground truth.

## Files

**Edit these** (then rebuild):

| File | Controls |
|---|---|
| `manufacturers.csv` | Which brands are included (`include` = `True`/`False`) |
| `plastic_rules.csv` | Per plastic: display name, category and `allowed_disc_types` (pipe-separated, or `all`) |
| `overrides.csv` | Per disc + plastic: `add` or `remove` |

**Never edit by hand:**

| File | What it is |
|---|---|
| `sourcedata/` | The two source CSVs. Fix data through the config files instead, so fixes survive a source refresh |
| `dropdown_db.json` | **Ship this.** Manufacturers, plastics and discs; each disc has a `plastic_ids` array |
| `discs.csv` | 621 discs with flight numbers |
| `plastics.csv` | 236 plastics |
| `disc_plastics.csv` | 8,579 disc ↔ plastic pairs, primary key `(disc_id, plastic_id)`. Handy in Excel or as a SQL table |

IDs are `<manufacturer-slug>__<name-slug>`, e.g. `latitude-64__royal`. The app may store
them, so keep them stable: rename a plastic's display name rather than changing its ID.

## Common fixes

| Problem | Fix in |
|---|---|
| A plastic shows on a disc type it isn't made for | `plastic_rules.csv`: narrow `allowed_disc_types` |
| A plastic is missing entirely | `plastic_rules.csv`: add a row with a new `plastic_id`; the build creates the plastic |
| A plastic has the wrong name | `plastic_rules.csv`: change `plastic_name`; the ID stays the same |
| One specific disc has a wrong or missing plastic | `overrides.csv`: add a `remove` or `add` row |
| A whole brand is missing or unwanted | `manufacturers.csv`: flip `include` |

Rebuild, then check `git diff` on the outputs before committing.

## Using the data

```js
const db = await fetch('dropdown_db.json').then(r => r.json());
const plasticById = Object.fromEntries(db.plastics.map(p => [p.id, p]));

discSelect.onchange = () => {
  const disc = db.discs.find(d => d.id === discSelect.value);
  plasticSelect.replaceChildren(...disc.plastic_ids.map(id => {
    const o = document.createElement('option');
    o.value = id;
    o.textContent = plasticById[id].name;
    return o;
  }));
};
```

Plastic `category` is currently one of `premium`, `baseline`, `midgrade`, `glow`, `specialty`,
`recycled` (enabling more brands can add `rubber`).

## Coverage and known gaps

- **15 brands included:** Innova, Discraft, Latitude 64, Dynamic Discs, Westside, Discmania,
  MVP, Axiom, Streamline, Prodigy, Kastaplast, Gateway, Infinite, Mint, Clash. 44 more are in
  the source and can be switched on in `manufacturers.csv`.
- **211 source discs have no manufacturer** (from the GitHub flight-number dataset, never
  matched to a PDGA record) and are skipped. Some belong to included brands, e.g. Athena
  (Discraft) and FD1 (Discmania). The build prints a warning with the count.
- **Source quirks handled by the build:** the category label `base` is read as `baseline`, and
  plastics whose name has no letters or digits (Gateway "$$$", a duplicate of Money) are
  dropped with a warning.
