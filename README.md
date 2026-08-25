# Disc → plastic dropdown database

## The one thing you need to know

Neither source file contains a disc-level plastic list. `disc_golf_manufacturer_plastics_v2.csv`
is **manufacturer → plastic**, with no link back to individual molds. So the DD3/Active
exclusion you asked for cannot be derived from the data — it has to be encoded.

This build encodes it in two layers:

1. **`plastic_rules.csv`** — each plastic is restricted to the disc types it's actually run in
   (Latitude Zero line → putters only, Innova Blizzard → drivers only, Discmania D-Line Flex →
   putters only, etc.). This removes ~70% of the wrong combinations with 235 rows of config
   instead of 8,500 rows of hand-checking.
2. **`overrides.csv`** — per-disc exceptions the type rule can't catch. One seeded example:
   DD3 minus Active Premium.

Everything below `rule` in the `source` column of `disc_plastics.csv` is inference, not
sourced fact. Treat it as a starting point to correct, not as verified data.

## Files

| File | Role |
|---|---|
| `dropdown_db.json` | Ship this. Discs each carry a `plastic_ids` array. |
| `discs.csv` | 621 discs, 15 manufacturers, with flight numbers |
| `plastics.csv` | 235 plastics |
| `disc_plastics.csv` | 8,523 disc↔plastic pairs — the dropdown-2 source, readable in Excel |
| `manufacturers.csv` | **editable** — `include` column toggles brands |
| `plastic_rules.csv` | **editable** — `allowed_disc_types`, pipe-separated, or `all` |
| `overrides.csv` | **editable** — `add` / `remove` per disc+plastic |
| `build_dropdown_db.py` | Re-run after editing any of the three configs |

## Manufacturers included

Innova, Discraft, Latitude 64, Dynamic Discs, Westside, Discmania, MVP, Axiom, Streamline,
Prodigy, Kastaplast, Gateway, Infinite, Mint, Clash.

Excluded but present in the source (flip `include` to `True` to add): Millennium, DGA, Legacy,
Viking, Yikun, Vibram, Daredevil, Lone Star, Thought Space Athletics, and ~40 others.

## Wiring the dropdowns

```js
const db = await fetch('dropdown_db.json').then(r => r.json());
const plasticById = Object.fromEntries(db.plastics.map(p => [p.id, p]));

// dropdown 1
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

If you'd rather query it, `disc_plastics.csv` loads straight into a table with
`(disc_id, plastic_id)` as the primary key.

## Rebuild

```bash
pip install pandas
python3 build_dropdown_db.py    # reads the 3 config CSVs + the 2 source CSVs
```
