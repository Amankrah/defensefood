"""
One-shot rebuild of ``unique_commodities_hs_cpc.csv``.

The legacy file ships CPC codes from a vocabulary that doesn't join with the
FAOSTAT QCL data (e.g. CPC ``01140`` for maize where FAOSTAT actually uses
``0112``). This script rebuilds the file in-place using FAOSTAT's real CPC
codes and adds an FBS item code so a single concordance covers both the
production and the food-balance accumulators.

Each HS code is mapped via three layers, in order of priority:
  1. ``HS6_OVERRIDES`` — 6-digit HS code with explicit FAOSTAT item
  2. ``HS4_HEADINGS``  — 4-digit HS heading default
  3. ``HS2_CHAPTERS``  — 2-digit chapter default (rare, mostly None)

Anything that resolves to ``None`` is left with empty CPC / FBS / item
columns and marked ``mapping_confidence='unmapped'``. These are typically
non-FAOSTAT chapters (chemicals, leather, minerals) or heterogeneous food
preps that don't map cleanly to one commodity.

Output columns:
    commodity, hs_code_comtrade, faostat_cpc, fbs_item_code,
    faostat_item, mapping_confidence

Run from the repo root:
    python backend/script/rebuild_hs_concordance.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ── Rule tables ────────────────────────────────────────────────────────────
# Each value is (faostat_cpc, fbs_item_code, faostat_item_name, note).
# None for any component means "not mapped at this level — try next layer".

HS6_OVERRIDES: dict[str, tuple] = {
    # Cereals - Chapter 10 (specific subclasses)
    "100110": ("0111", "S2511", "Wheat", "Durum wheat"),
    "100190": ("0111", "S2511", "Wheat", "Spelt / other wheat"),
    "100200": ("0116", "S2515", "Rye", ""),
    "100300": ("0115", "S2513", "Barley", ""),
    "100400": ("0117", "S2516", "Oats", ""),
    "100590": ("0112", "S2514", "Maize (corn)", "Other maize"),
    "100620": ("0113", "S2807", "Rice", "Husked rice"),
    "100630": ("0113", "S2807", "Rice", "Milled rice"),
    "100640": ("0113", "S2807", "Rice", "Broken rice"),
    "100700": ("0114", "S2518", "Sorghum", ""),
    "100810": ("01192", "S2520", "Buckwheat", ""),
    "100820": ("0118", "S2517", "Millet", ""),
    "100850": ("01199.90", "S2520", "Cereals n.e.c.", "Quinoa proxy"),
    "100859": ("01199.90", "S2520", "Cereals n.e.c.", "Teff/fonio proxy"),
    "100880": ("0111", "S2511", "Wheat", "Triticale (wheat-rye hybrid) proxy"),
    "100890": ("01199.90", "S2520", "Cereals n.e.c.", "Amaranth/other"),

    # Mill products - Chapter 11
    "110100": ("0111", "S2511", "Wheat", "Wheat flour proxy"),
    "110220": ("0112", "S2514", "Maize (corn)", "Maize flour"),
    "110230": ("0113", "S2807", "Rice", "Rice flour"),
    "110290": ("F1717", "S2520", "Cereals; primary", "Other cereal flour proxy"),
    "110311": ("0111", "S2511", "Wheat", "Bulgur/freekeh"),
    "110312": ("0111", "S2511", "Wheat", "Precooked wheat"),
    "110313": ("0112", "S2514", "Maize (corn)", "Maize groats"),
    "110319": ("F1717", "S2520", "Cereals; primary", "Other cereal groats"),
    "110412": ("0117", "S2516", "Oats", "Oat flakes"),
    "110429": ("F1717", "S2520", "Cereals; primary", "Other processed cereal grains"),
    "110430": ("0117", "S2516", "Oats", "Oat flakes (rolled)"),
    "110600": ("01703", None, "Chick peas", "Chickpea flour proxy"),
    "110812": ("0112", "S2514", "Maize (corn)", "Maize starch"),
    "110814": ("01520.01", None, "Cassava; fresh", "Cassava starch"),
    "110819": (None, None, None, "Heterogeneous starches"),
    "110900": ("0111", "S2511", "Wheat", "Wheat gluten"),

    # Oilseeds - Chapter 12 (specific items)
    "120119": (None, None, None, "Coconut flour"),
    "120190": ("0141", "S2555", "Soya beans", ""),
    "120242": ("0142", "S2552", "Groundnuts; excluding shelled", ""),
    "120510": ("01441", "S2570", "Linseed", "Note: legacy label says flax but HS 1205 is rape; using linseed as FAOSTAT closest"),
    "120590": ("01441", "S2570", "Linseed", "Note: legacy label says rapeseed; map to linseed/oilcrops other"),
    "120600": ("01445", "S2557", "Sunflower seed", ""),
    "120740": ("01444", "S2561", "Sesame seed", ""),
    "120760": ("01491.02", "S2562", "Palm kernels", ""),
    "120799": (None, "S2570", "Oilcrops, Other", "Heterogeneous (almond meal, pine nuts)"),
    "120810": ("0141", "S2555", "Soya beans", "Soya flour"),

    # Pulses & legumes
    "071340": ("01704", None, "Lentils; dry", ""),

    # Treenuts - Chapter 08
    "080212": ("01371", "S2912", "Almonds; in shell", ""),
    "080299": ("01371", "S2912", "Almonds; in shell", "Other tree nuts proxy"),

    # Spices - Chapter 09
    "090999": ("01699", "S2645", "Other stimulant; spice and aromatic crops; n.e.c.", ""),
    "091030": ("01699", "S2645", "Other stimulant; spice and aromatic crops; n.e.c.", "Turmeric"),

    # Animal products - Chapters 02/04
    "020719": ("21121", "S2734", "Meat of chickens; fresh or chilled", ""),
    "021199": ("21121", "S2734", "Meat of chickens; fresh or chilled", "Chicken by-products"),
    "040490": (None, "S2848", "Milk - Excluding Butter", "Dairy permeate"),
    "040690": (None, "S2848", "Milk - Excluding Butter", "Cheese (Mutter paneer)"),

    # Fish (Chapter 03) - QCL doesn't have these; only FBS aggregate
    "030239": (None, "S2763", "Pelagic Fish", "Tuna"),
    "030249": (None, "S2763", "Pelagic Fish", "Sardines"),
    "030519": (None, "S2765", "Crustaceans", "Shrimp powder"),
    "030539": (None, "S2765", "Crustaceans", "Dried/smoked shrimps"),
    "030612": (None, "S2765", "Crustaceans", "Lobster"),
    "030613": (None, "S2765", "Crustaceans", "Crayfish"),
    "030614": (None, "S2765", "Crustaceans", "Crab"),
    "030616": (None, "S2765", "Crustaceans", "Cold-water shrimps"),
    "030617": (None, "S2765", "Crustaceans", "Other shrimps"),
    "030623": (None, "S2765", "Crustaceans", "Frozen crayfish"),
    "030624": (None, "S2765", "Crustaceans", "Frozen crabs"),
    "030699": (None, "S2765", "Crustaceans", "Other crustaceans"),
    "030711": (None, "S2767", "Molluscs, Other", "Live oysters"),
    "030712": (None, "S2767", "Molluscs, Other", "Frozen/preserved oysters"),
    "030721": (None, "S2767", "Molluscs, Other", "Live scallops"),
    "030722": (None, "S2767", "Molluscs, Other", "Frozen scallops"),
    "030731": (None, "S2767", "Molluscs, Other", "Live mussels"),
    "030732": (None, "S2767", "Molluscs, Other", "Frozen/preserved mussels"),
    "030741": (None, "S2766", "Cephalopods", "Live/fresh squid"),
    "030743": (None, "S2766", "Cephalopods", "Frozen squid"),
    "030751": (None, "S2766", "Cephalopods", "Live octopus"),
    "030752": (None, "S2766", "Cephalopods", "Frozen octopus"),
    "030771": (None, "S2767", "Molluscs, Other", "Live clams"),
    "030772": (None, "S2767", "Molluscs, Other", "Frozen/preserved clams"),
    "030779": (None, "S2767", "Molluscs, Other", "Other aquatic invertebrates"),
    "030791": (None, "S2767", "Molluscs, Other", "Live snails (marine)"),
    "030799": (None, "S2767", "Molluscs, Other", "Mixed seafood"),

    # Animal by-products (Chapter 05) - non-food, unmapped
    "050400": (None, None, None, "Animal guts (treats for dogs)"),
    "050800": (None, None, None, "Coral / shells - non-food"),
    "051199": (None, None, None, "Animal by-products non-food"),
    "051299": (None, None, None, "Animal by-products non-food"),

    # Gums & resins (Chapter 13)
    "130219": (None, None, None, "Plant extracts (heterogeneous)"),
    "130239": (None, None, None, "Plant extracts (heterogeneous)"),

    # Oils - Chapter 15
    "150420": (None, "S2782", "Fish, Liver Oil", "Fish oil"),
    "151290": ("2161", "S2571", "Soya bean oil", ""),
    "151521": ("21691.02", "S2582", "Maize Germ Oil", "Corn oil"),
    "151690": (None, None, None, "Hydrogenated/processed fats"),

    # Prepared meat/fish - Chapter 16
    "160100": (None, None, None, "Sausages (mixed meat)"),
    "160510": (None, "S2765", "Crustaceans", "Crab prepared"),
    "160521": (None, "S2765", "Crustaceans", "Shrimps prepared"),
    "160553": (None, "S2767", "Molluscs, Other", "Mussels prepared"),
    "160556": (None, "S2767", "Molluscs, Other", "Clams prepared"),
    "160559": (None, "S2767", "Molluscs, Other", "Other mollusks prepared"),

    # Sugar - Chapter 17
    "170260": ("0115", "S2513", "Barley", "Barley malt syrup"),
    "170310": ("23540", None, "Molasses", ""),

    # Cereal preparations - Chapter 19
    "190110": (None, None, None, "Heterogeneous baby food"),
    "190211": ("0111", "S2511", "Wheat", "Couscous / vermicelli"),
    "190219": ("0111", "S2511", "Wheat", "Pasta"),
    "190220": ("0111", "S2511", "Wheat", "Stuffed pasta"),
    "190240": ("0111", "S2511", "Wheat", "Bulgur / millet couscous"),
    "190410": ("F1717", "S2520", "Cereals; primary", "Breakfast cereals"),
    "190430": ("0111", "S2511", "Wheat", "Bulgur"),
    "190490": ("F1717", "S2520", "Cereals; primary", "Cereal bars"),
    "190510": ("0111", "S2511", "Wheat", "Crispbread"),
    "190530": ("0111", "S2511", "Wheat", "Sweet biscuits"),
    "190531": ("0111", "S2511", "Wheat", "Cookies"),
    "190532": ("0111", "S2511", "Wheat", "Crackers"),
    "190533": ("0111", "S2511", "Wheat", "Wafers"),
    "190590": ("0111", "S2511", "Wheat", "Other bakery"),

    # Vegetable / fruit preparations - Chapter 20
    "200819": ("01444", "S2561", "Sesame seed", "Sesame paste"),
    "200990": (None, None, None, "Concentrated juices"),

    # Food preparations - Chapter 21
    "210210": (None, None, None, "Yeast (microbial)"),
    "210690": (None, None, None, "Heterogeneous food supplements"),

    # Beverages - Chapter 22
    "220110": (None, None, None, "Bottled water"),

    # Residues / feed - Chapter 23
    "230110": (None, None, None, "Animal meal (pet food)"),
    "230120": (None, "S2766", "Cephalopods", "Fish meal proxy"),
    "230210": ("0111", "S2511", "Wheat", "Wheat bran"),
    "230240": ("0113", "S2807", "Rice", "Rice bran"),
    "230300": ("0115", "S2513", "Barley", "Brewer's grain (barley residue)"),
    "230310": ("0112", "S2514", "Maize (corn)", "Maize gluten feed"),
    "230400": ("0141", "S2555", "Soya beans", "Soybean cake"),
    "230500": (None, None, None, "Mixed oilseed meals"),
    "230800": ("01341", None, "Apples", "Apple pomace"),
    "230910": (None, None, None, "Pet food"),
    "230990": (None, None, None, "Mixed animal feed"),

    # Sowing & forage (Chapter 12 tail)
    "120921": (None, None, None, "Clover seeds (sowing)"),
    "120929": (None, None, None, "Onion seeds (sowing)"),
    "121120": (None, None, None, "Liquorice (extract)"),
    "121190": (None, None, None, "Herbal powders"),
    "121210": ("01356", None, "Locust beans (carobs)", ""),
    "121221": (None, None, None, "Seaweed meal"),
    "121300": (None, None, None, "Hay (forage)"),
    "121400": (None, None, None, "Alfalfa (forage)"),

    # Non-food chapters - explicitly unmapped
    "250700": (None, None, None, "Kaolin clay (non-food)"),
    "271400": (None, None, None, "Leonardite (non-food)"),
    "281030": (None, None, None, "Magnesium oxide (chemical)"),
    "282090": (None, None, None, "Manganese oxide (chemical)"),
    "283525": (None, None, None, "Dicalcium phosphate (feed additive)"),
    "283650": (None, None, None, "Calcium carbonate"),
    "291570": (None, None, None, "Calcium stearate (chemical)"),
    "292369": (None, None, None, "Choline chloride (additive)"),
    "293690": (None, None, None, "Vitamin D3 (additive)"),
    "350190": (None, None, None, "Hemoglobin meal (animal protein)"),
    "350490": (None, None, None, "Chitin"),
    "382311": (None, None, None, "Palm fatty acid (chemical)"),
    "410510": (None, None, None, "Animal hide / leather"),
    "999999": (None, None, None, "Unspecified"),
}

# 4-digit defaults for HS codes not in HS6_OVERRIDES (rare — most are covered above).
HS4_HEADINGS: dict[str, tuple] = {
    "1001": ("0111", "S2511", "Wheat", "Wheat heading default"),
    "1002": ("0116", "S2515", "Rye", "Rye heading"),
    "1003": ("0115", "S2513", "Barley", "Barley heading"),
    "1004": ("0117", "S2516", "Oats", "Oats heading"),
    "1005": ("0112", "S2514", "Maize (corn)", "Maize heading"),
    "1006": ("0113", "S2807", "Rice", "Rice heading"),
    "1007": ("0114", "S2518", "Sorghum", "Sorghum heading"),
    "1008": ("01199.90", "S2520", "Cereals n.e.c.", "Other cereals heading"),
    "1101": ("0111", "S2511", "Wheat", "Wheat flour heading"),
    "1102": ("F1717", "S2520", "Cereals; primary", "Other cereal flours"),
    "1103": ("F1717", "S2520", "Cereals; primary", "Cereal groats"),
    "1104": ("F1717", "S2520", "Cereals; primary", "Other worked grains"),
    "1108": (None, None, None, "Mixed starches"),
    "1905": ("0111", "S2511", "Wheat", "Bakery default proxy"),
}

# 2-digit chapter fallback (very coarse). Only set where it's meaningful.
HS2_CHAPTERS: dict[str, tuple] = {
    # Most chapters with unmapped tail content default to None
}


def resolve(hs: str) -> tuple:
    """Three-layer resolution. Returns (cpc, fbs, item, note, confidence)."""
    if hs in HS6_OVERRIDES:
        cpc, fbs, item, note = HS6_OVERRIDES[hs]
        return cpc, fbs, item, note, "override"
    h4 = hs[:4]
    if h4 in HS4_HEADINGS:
        cpc, fbs, item, note = HS4_HEADINGS[h4]
        return cpc, fbs, item, note, "heading"
    h2 = hs[:2]
    if h2 in HS2_CHAPTERS:
        cpc, fbs, item, note = HS2_CHAPTERS[h2]
        return cpc, fbs, item, note, "chapter"
    return None, None, None, "no rule", "unmapped"


def normalize_hs(code: object) -> str:
    """Local HS normaliser (mirrors defensefood.ingestion.hs_codes)."""
    if code is None:
        return ""
    s = str(code).strip().lstrip("'")
    if s.endswith(".0"):
        s = s[:-2]
    if not s or not s.isdigit():
        return ""
    if len(s) % 2 == 1:
        s = "0" + s
    return s[:6]


def main() -> int:
    src = Path(__file__).resolve().parent.parent / "unique_commodities_hs_cpc.csv"
    backup = src.with_suffix(".csv.legacy_pre_fix.bak")

    if not src.exists():
        print(f"[ERR] {src} not found", file=sys.stderr)
        return 1

    df = pd.read_csv(src)
    print(f"Loaded {len(df)} rows, {df['hs_code_comtrade'].nunique()} distinct raw HS codes")

    # Back up original
    if not backup.exists():
        df.to_csv(backup, index=False)
        print(f"Backed up original to {backup.name}")

    # Normalise HS codes (zero-pad odd-length)
    df["hs_code_comtrade"] = df["hs_code_comtrade"].apply(normalize_hs)
    df = df[df["hs_code_comtrade"] != ""].copy()

    # Resolve each row through the three-layer rules
    resolved = df["hs_code_comtrade"].apply(resolve)
    df["faostat_cpc"] = [r[0] or "" for r in resolved]
    df["fbs_item_code"] = [r[1] or "" for r in resolved]
    df["faostat_item"] = [r[2] or "" for r in resolved]
    df["mapping_note"] = [r[3] or "" for r in resolved]
    df["mapping_confidence"] = [r[4] for r in resolved]

    # Diagnostics
    by_conf = df["mapping_confidence"].value_counts()
    print()
    print("Mapping confidence breakdown:")
    for conf, n in by_conf.items():
        print(f"  {conf:>10}: {n:>4} rows")
    unmapped = df[df["mapping_confidence"] == "unmapped"]
    if not unmapped.empty:
        print()
        print("Unmapped HS codes (explicitly out-of-scope or unrecognised):")
        for hs in sorted(unmapped["hs_code_comtrade"].unique()):
            sample = unmapped[unmapped["hs_code_comtrade"] == hs]["commodity"].iloc[0]
            print(f"  HS {hs}  e.g. {sample}")

    # Reorder columns and write
    out_cols = [
        "commodity",
        "hs_code_comtrade",
        "faostat_cpc",
        "fbs_item_code",
        "faostat_item",
        "mapping_confidence",
        "mapping_note",
    ]
    df = df[out_cols].drop_duplicates().reset_index(drop=True)
    df.to_csv(src, index=False)
    print()
    print(f"Wrote {len(df)} rows to {src.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
