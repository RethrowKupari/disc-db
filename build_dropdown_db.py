#!/usr/bin/env python3
"""
Builds a two-dropdown database (disc -> plastics) from the two source CSVs.

Usage (from anywhere; paths are relative to this file):
    pip install -r requirements.txt
    python build_dropdown_db.py [--src DIR] [--out DIR]

Inputs  (source data in sourcedata/, never modified):
    disc_golf_discs_flight_numbers_v2_powergrip_checked.csv
    disc_golf_manufacturer_plastics_v2_powergrip_checked.csv

Config  (hand-editable, next to this file, re-run after editing):
    manufacturers.csv   - which brands are included
    plastic_rules.csv   - which disc types each plastic is allowed on
    overrides.csv       - per-disc add/remove exceptions

Outputs (written next to this file by default):
    discs.csv, plastics.csv, disc_plastics.csv, dropdown_db.json
"""
import argparse
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent

ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
ap.add_argument("--src", type=Path, default=ROOT / "sourcedata",
                help="folder with the two source CSVs (default: sourcedata/)")
ap.add_argument("--out", type=Path, default=ROOT,
                help="folder to write outputs to (default: repo folder)")
args = ap.parse_args()

SRC = args.src
CFG = ROOT
OUT = args.out
OUT.mkdir(parents=True, exist_ok=True)

DISCS_SRC = SRC / "disc_golf_discs_flight_numbers_v2_powergrip_checked.csv"
PLASTICS_SRC = SRC / "disc_golf_manufacturer_plastics_v2_powergrip_checked.csv"
for f in (DISCS_SRC, PLASTICS_SRC):
    if not f.is_file():
        raise SystemExit(f"missing source file: {f}")

DISC_TYPES = ["Distance Driver", "Control Driver", "Mid Range", "Putt & Approach"]

# Same tier spelled differently in the source; keep the category list clean.
CATEGORY_ALIASES = {"base": "baseline"}


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8")


def write_csv(df: pd.DataFrame, path: Path) -> None:
    # explicit LF + UTF-8 so Windows and Linux builds produce identical files.
    # pandas 1.5 renamed line_terminator -> lineterminator; support both.
    try:
        df.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")
    except TypeError:
        df.to_csv(path, index=False, encoding="utf-8", line_terminator="\n")


def slug(s: str) -> str:
    # '+' is meaningful in disc names (TeeBird vs TeeBird+), so keep it
    s = str(s).lower().replace("+", " plus ")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


# ---------------------------------------------------------------- load source
discs = read_csv(DISCS_SRC)
plastics = read_csv(PLASTICS_SRC)
plastics["plastic_category"] = plastics["plastic_category"].replace(CATEGORY_ALIASES)

no_mfr = discs["manufacturer"].isna().sum()
if no_mfr:
    print(f"  ! {no_mfr} source discs have no manufacturer and are skipped")

mfrs = read_csv(CFG / "manufacturers.csv")
included = set(mfrs.loc[mfrs["include"] == True, "manufacturer"])  # noqa: E712

discs = discs[discs["manufacturer"].isin(included)].copy()
plastics = plastics[plastics["manufacturer"].isin(included)].copy()

# ---------------------------------------------------------------- ids
discs["manufacturer_slug"] = discs["manufacturer"].map(slug)
discs["disc_id"] = discs["manufacturer_slug"] + "__" + discs["disc_name"].map(slug)

# A blank plastic_slug would give an id like "gateway__" (or NaN). Derive it
# from the name; if the name has no letters/digits either (Gateway "$$$",
# which is just the Money blend, already listed), drop the plastic loudly.
plastics["plastic_slug"] = [
    s if isinstance(s, str) and s.strip() else slug(n)
    for s, n in zip(plastics["plastic_slug"], plastics["plastic_name"])
]
unsluggable = plastics["plastic_slug"] == ""
for r in plastics[unsluggable].itertuples():
    print(f"  ! dropped plastic with no usable id: {r.manufacturer} / {r.plastic_name!r}")
plastics = plastics[~unsluggable].copy()

plastics["plastic_id"] = (
    plastics["manufacturer_slug"] + "__" + plastics["plastic_slug"]
)

# ---------------------------------------------------------------- rules
rules = read_csv(CFG / "plastic_rules.csv")

# plastic_rules.csv names win over the source. This renames a plastic but
# keeps its id stable (e.g. latitude-64__royal is displayed as "Royal Grand").
rule_names = dict(zip(rules["plastic_id"], rules["plastic_name"]))
for i, r in plastics.iterrows():
    new = rule_names.get(r["plastic_id"])
    if isinstance(new, str) and new != r["plastic_name"]:
        print(f"renamed {r['plastic_id']}: {r['plastic_name']!r} -> {new!r}")
        plastics.at[i, "plastic_name"] = new

# Plastics that exist in plastic_rules.csv but are missing from the source
# file (e.g. Latitude 64 Royal Grand / Royal Clear) are added here, so the
# fix survives every rebuild without touching the source data.
known_names = set(zip(plastics["manufacturer"], plastics["plastic_name"]))
missing = rules[
    ~rules["plastic_id"].isin(set(plastics["plastic_id"]))
    & rules["manufacturer"].isin(included)
    & ~pd.Series(
        list(zip(rules["manufacturer"], rules["plastic_name"])), index=rules.index
    ).isin(known_names)
]
if not missing.empty:
    ids = missing["plastic_id"].str.split("__", n=1, expand=True)
    extra = pd.DataFrame(
        {
            "manufacturer": missing["manufacturer"].values,
            "manufacturer_slug": ids[0].values,
            "plastic_name": missing["plastic_name"].values,
            "plastic_slug": ids[1].values,
            "plastic_category": missing["plastic_category"].replace(CATEGORY_ALIASES).values,
            "plastic_id": missing["plastic_id"].values,
        }
    )
    plastics = pd.concat([plastics, extra], ignore_index=True)
    print(f"added from plastic_rules.csv: {sorted(extra['plastic_id'])}")

assert discs["disc_id"].is_unique, "duplicate disc_id"
assert plastics["plastic_id"].is_unique, "duplicate plastic_id"

rules = rules[rules["plastic_id"].isin(set(plastics["plastic_id"]))]
allowed_types = dict(zip(rules["plastic_id"], rules["allowed_disc_types"]))


def types_for(plastic_id: str) -> list:
    raw = allowed_types.get(plastic_id, "all")
    if pd.isna(raw) or str(raw).strip().lower() == "all":
        return list(DISC_TYPES)
    return [t.strip() for t in str(raw).split("|") if t.strip()]


# ---------------------------------------------------------------- cross join
pairs = []
for _, d in discs.iterrows():
    mfr_plastics = plastics[plastics["manufacturer"] == d["manufacturer"]]
    for _, p in mfr_plastics.iterrows():
        if d["disc_type"] in types_for(p["plastic_id"]):
            pairs.append(
                {
                    "disc_id": d["disc_id"],
                    "disc_name": d["disc_name"],
                    "manufacturer": d["manufacturer"],
                    "disc_type": d["disc_type"],
                    "plastic_id": p["plastic_id"],
                    "plastic_name": p["plastic_name"],
                    "plastic_category": p["plastic_category"],
                    "source": "rule",
                }
            )

dp = pd.DataFrame(pairs)

# ---------------------------------------------------------------- overrides
ov = read_csv(CFG / "overrides.csv")
ov = ov.dropna(subset=["disc_id", "plastic_id"])

removals = ov[ov["action"].str.lower() == "remove"]
key = set(zip(removals["disc_id"], removals["plastic_id"]))
before = len(dp)
dp = dp[~dp.apply(lambda r: (r.disc_id, r.plastic_id) in key, axis=1)]
removed = before - len(dp)

additions = ov[ov["action"].str.lower() == "add"]
added = 0
for _, a in additions.iterrows():
    if ((dp["disc_id"] == a["disc_id"]) & (dp["plastic_id"] == a["plastic_id"])).any():
        continue
    d = discs[discs["disc_id"] == a["disc_id"]]
    p = plastics[plastics["plastic_id"] == a["plastic_id"]]
    if d.empty or p.empty:
        print(f"  ! override references unknown id: {a['disc_id']} / {a['plastic_id']}")
        continue
    d, p = d.iloc[0], p.iloc[0]
    dp.loc[len(dp)] = {
        "disc_id": d["disc_id"],
        "disc_name": d["disc_name"],
        "manufacturer": d["manufacturer"],
        "disc_type": d["disc_type"],
        "plastic_id": p["plastic_id"],
        "plastic_name": p["plastic_name"],
        "plastic_category": p["plastic_category"],
        "source": "override",
    }
    added += 1

dp = dp.sort_values(["manufacturer", "disc_name", "plastic_name"]).reset_index(drop=True)

# ---------------------------------------------------------------- outputs
disc_cols = {
    "disc_id": "disc_id",
    "disc_name": "disc_name",
    "manufacturer": "manufacturer",
    "manufacturer_slug": "manufacturer_slug",
    "disc_type": "disc_type",
    "flight_speed": "speed",
    "flight_glide": "glide",
    "flight_turn": "turn",
    "flight_fade": "fade",
    "flight_stability": "stability",
    "pdga_approved": "pdga_approved",
}
discs_out = discs[list(disc_cols)].rename(columns=disc_cols).sort_values(
    ["manufacturer", "disc_name"]
)
plastics_out = plastics[
    ["plastic_id", "manufacturer", "manufacturer_slug", "plastic_name",
     "plastic_slug", "plastic_category"]
].sort_values(["manufacturer", "plastic_name"])

write_csv(discs_out, OUT / "discs.csv")
write_csv(plastics_out, OUT / "plastics.csv")
write_csv(dp, OUT / "disc_plastics.csv")

by_disc = dp.groupby("disc_id")["plastic_id"].apply(list).to_dict()
db = {
    "manufacturers": [
        {"id": slug(m), "name": m}
        for m in sorted(included)
    ],
    "plastics": [
        {
            "id": r.plastic_id,
            "name": r.plastic_name,
            "manufacturer_id": r.manufacturer_slug,
            "category": r.plastic_category,
        }
        for r in plastics_out.itertuples()
    ],
    "discs": [
        {
            "id": r.disc_id,
            "name": r.disc_name,
            "manufacturer_id": r.manufacturer_slug,
            "type": r.disc_type,
            "flight": [r.speed, r.glide, r.turn, r.fade],
            "plastic_ids": by_disc.get(r.disc_id, []),
        }
        for r in discs_out.itertuples()
    ],
}
with open(OUT / "dropdown_db.json", "w", encoding="utf-8", newline="\n") as fh:
    fh.write(json.dumps(db, indent=1, ensure_ascii=False))

# when building somewhere else, copy the editable config next to the outputs
if OUT.resolve() != CFG.resolve():
    for f in ["manufacturers.csv", "plastic_rules.csv", "overrides.csv"]:
        (OUT / f).write_bytes((CFG / f).read_bytes())

print(f"manufacturers : {len(included)}")
print(f"discs         : {len(discs_out)}")
print(f"plastics      : {len(plastics_out)}")
print(f"disc-plastic  : {len(dp)} pairs ({removed} removed, {added} added by override)")
print(f"avg per disc  : {len(dp)/len(discs_out):.1f}")
orphans = set(discs_out["disc_id"]) - set(by_disc)
if orphans:
    print(f"  ! {len(orphans)} discs with zero plastics: {sorted(orphans)[:5]}")
