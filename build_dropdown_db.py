#!/usr/bin/env python3
"""
Builds a two-dropdown database (disc -> plastics) from the two source CSVs.

Inputs  (source data, never modified):
    disc_golf_discs_flight_numbers_v2_powergrip_checked.csv
    disc_golf_manufacturer_plastics_v2_powergrip_checked.csv

Config  (hand-editable, re-run after editing):
    manufacturers.csv   - which brands are included
    plastic_rules.csv   - which disc types each plastic is allowed on
    overrides.csv       - per-disc add/remove exceptions

Outputs:
    discs.csv, plastics.csv, disc_plastics.csv, dropdown_db.json
"""
import json
import re
from pathlib import Path

import pandas as pd

SRC = Path("/mnt/user-data/uploads")
CFG = Path(".")
OUT = Path("/mnt/user-data/outputs")
OUT.mkdir(parents=True, exist_ok=True)

DISC_TYPES = ["Distance Driver", "Control Driver", "Mid Range", "Putt & Approach"]


def slug(s: str) -> str:
    # '+' is meaningful in disc names (TeeBird vs TeeBird+), so keep it
    s = str(s).lower().replace("+", " plus ")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


# ---------------------------------------------------------------- load source
discs = pd.read_csv(SRC / "disc_golf_discs_flight_numbers_v2_powergrip_checked.csv")
plastics = pd.read_csv(SRC / "disc_golf_manufacturer_plastics_v2_powergrip_checked.csv")

mfrs = pd.read_csv(CFG / "manufacturers.csv")
included = set(mfrs.loc[mfrs["include"] == True, "manufacturer"])  # noqa: E712

discs = discs[discs["manufacturer"].isin(included)].copy()
plastics = plastics[plastics["manufacturer"].isin(included)].copy()

# ---------------------------------------------------------------- ids
discs["manufacturer_slug"] = discs["manufacturer"].map(slug)
discs["disc_id"] = discs["manufacturer_slug"] + "__" + discs["disc_name"].map(slug)
plastics["plastic_id"] = (
    plastics["manufacturer_slug"] + "__" + plastics["plastic_slug"]
)

assert discs["disc_id"].is_unique, "duplicate disc_id"
assert plastics["plastic_id"].is_unique, "duplicate plastic_id"

# ---------------------------------------------------------------- rules
rules = pd.read_csv(CFG / "plastic_rules.csv")
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
ov = pd.read_csv(CFG / "overrides.csv")
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

discs_out.to_csv(OUT / "discs.csv", index=False)
plastics_out.to_csv(OUT / "plastics.csv", index=False)
dp.to_csv(OUT / "disc_plastics.csv", index=False)

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
(OUT / "dropdown_db.json").write_text(json.dumps(db, indent=1, ensure_ascii=False))

# also copy the editable config next to the outputs
for f in ["manufacturers.csv", "plastic_rules.csv", "overrides.csv"]:
    (OUT / f).write_text(Path(f).read_text())

print(f"manufacturers : {len(included)}")
print(f"discs         : {len(discs_out)}")
print(f"plastics      : {len(plastics_out)}")
print(f"disc-plastic  : {len(dp)} pairs ({removed} removed, {added} added by override)")
print(f"avg per disc  : {len(dp)/len(discs_out):.1f}")
orphans = set(discs_out["disc_id"]) - set(by_disc)
if orphans:
    print(f"  ! {len(orphans)} discs with zero plastics: {sorted(orphans)[:5]}")
