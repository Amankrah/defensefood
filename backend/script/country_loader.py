"""
Country Loader

Loads country pairs from updated_data_rasff_window.xlsx.
- From country: origin column
- To countries: for_followUp column (comma-separated)

Also provides M49 country code mappings for UN Comtrade API.
"""

import os
import pandas as pd
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set
from dataclasses import dataclass


# ─────────────────────────────────────────────
#  M49 COUNTRY CODES
#  Full mapping for European and major trading countries
# ─────────────────────────────────────────────

M49_COUNTRY_CODES = {
    # World / All
    "World": "0",
    "All": "0",

    # European Union (UN Comtrade specific codes)
    "Austria": "40",
    "Belgium": "56",
    "Bulgaria": "100",
    "Croatia": "191",
    "Cyprus": "196",
    "Czech Republic": "203",
    "Czechia": "203",
    "Denmark": "208",
    "Estonia": "233",
    "Finland": "246",
    "France": "251",       # UN Comtrade uses 251, not 250
    "Germany": "276",
    "Greece": "300",
    "Hungary": "348",
    "Ireland": "372",
    "Italy": "380",
    "Latvia": "428",
    "Lithuania": "440",
    "Luxembourg": "442",
    "Malta": "470",
    "Netherlands": "528",
    "Poland": "616",
    "Portugal": "620",
    "Romania": "642",
    "Slovakia": "703",
    "Slovenia": "705",
    "Spain": "724",
    "Sweden": "752",

    # Other European
    "Albania": "8",
    "Andorra": "20",
    "Belarus": "112",
    "Bosnia and Herzegovina": "70",
    "Iceland": "352",
    "Kosovo": "412",
    "Liechtenstein": "438",
    "Moldova": "498",
    "Monaco": "492",
    "Montenegro": "499",
    "North Macedonia": "807",
    "Norway": "578",
    "Russia": "643",
    "Russian Federation": "643",
    "San Marino": "674",
    "Serbia": "688",
    "Switzerland": "756",
    "Turkey": "792",
    "Ukraine": "804",
    "United Kingdom": "826",
    "UK": "826",
    "Vatican City": "336",

    # North America
    "Canada": "124",
    "Mexico": "484",
    "United States": "842",
    "USA": "842",
    "United States of America": "842",

    # South America
    "Argentina": "32",
    "Bolivia": "68",
    "Brazil": "76",
    "Chile": "152",
    "Colombia": "170",
    "Ecuador": "218",
    "Guyana": "328",
    "Paraguay": "600",
    "Peru": "604",
    "Suriname": "740",
    "Uruguay": "858",
    "Venezuela": "862",

    # Asia
    "Afghanistan": "4",
    "Bangladesh": "50",
    "Cambodia": "116",
    "China": "156",
    "Hong Kong": "344",
    "India": "356",
    "Indonesia": "360",
    "Iran": "364",
    "Iraq": "368",
    "Israel": "376",
    "Japan": "392",
    "Jordan": "400",
    "Kazakhstan": "398",
    "Kuwait": "414",
    "Laos": "418",
    "Lebanon": "422",
    "Malaysia": "458",
    "Mongolia": "496",
    "Myanmar": "104",
    "Nepal": "524",
    "North Korea": "408",
    "Oman": "512",
    "Pakistan": "586",
    "Philippines": "608",
    "Qatar": "634",
    "Saudi Arabia": "682",
    "Singapore": "702",
    "South Korea": "410",
    "Korea": "410",
    "Sri Lanka": "144",
    "Syria": "760",
    "Taiwan": "158",
    "Thailand": "764",
    "Turkmenistan": "795",
    "United Arab Emirates": "784",
    "UAE": "784",
    "Uzbekistan": "860",
    "Vietnam": "704",
    "Viet Nam": "704",
    "Yemen": "887",

    # Africa
    "Algeria": "12",
    "Angola": "24",
    "Benin": "204",
    "Botswana": "72",
    "Burkina Faso": "854",
    "Cameroon": "120",
    "Cote d'Ivoire": "384",
    "Ivory Coast": "384",
    "Egypt": "818",
    "Ethiopia": "231",
    "Ghana": "288",
    "Kenya": "404",
    "Libya": "434",
    "Madagascar": "450",
    "Mali": "466",
    "Morocco": "504",
    "Mozambique": "508",
    "Namibia": "516",
    "Niger": "562",
    "Nigeria": "566",
    "Senegal": "686",
    "South Africa": "710",
    "Sudan": "729",
    "Tanzania": "834",
    "Tunisia": "788",
    "Uganda": "800",
    "Zambia": "894",
    "Zimbabwe": "716",

    # Oceania
    "Australia": "36",
    "Fiji": "242",
    "New Zealand": "554",
    "Papua New Guinea": "598",

    # Central America & Caribbean
    "Costa Rica": "188",
    "Cuba": "192",
    "Dominican Republic": "214",
    "El Salvador": "222",
    "Guatemala": "320",
    "Haiti": "332",
    "Honduras": "340",
    "Jamaica": "388",
    "Nicaragua": "558",
    "Panama": "591",
    "Puerto Rico": "630",
    "Trinidad and Tobago": "780",
}


def get_m49_code(country_name: str) -> Optional[str]:
    """
    Get M49 country code from country name.

    Args:
        country_name: Country name (case-insensitive, handles common variations)

    Returns:
        M49 code string or None if not found
    """
    if not country_name or pd.isna(country_name):
        return None

    # Clean the country name
    name = country_name.strip()

    # Try exact match first (case-insensitive)
    for key, code in M49_COUNTRY_CODES.items():
        if key.lower() == name.lower():
            return code

    # Try partial match
    name_lower = name.lower()
    for key, code in M49_COUNTRY_CODES.items():
        if name_lower in key.lower() or key.lower() in name_lower:
            return code

    return None


# ─────────────────────────────────────────────
#  RASFF DATA LOADER
# ─────────────────────────────────────────────

def get_rasff_excel_path() -> Path:
    """Get the path to the RASFF Excel file."""
    script_dir = Path(__file__).parent
    backend_dir = script_dir.parent
    return backend_dir / "updated_data_rasff_window.xlsx"


def load_rasff_data() -> pd.DataFrame:
    """
    Load the RASFF data from Excel.

    Returns:
        DataFrame with RASFF notification data
    """
    excel_path = get_rasff_excel_path()

    if not excel_path.exists():
        raise FileNotFoundError(f"RASFF Excel not found at: {excel_path}")

    df = pd.read_excel(excel_path)
    return df


@dataclass
class TradePair:
    """Represents a trade relationship between two countries."""
    reference: str
    from_country: str
    from_country_code: Optional[str]
    to_country: str
    to_country_code: Optional[str]
    hs_code: Optional[str]
    commodity: Optional[str]


def extract_trade_pairs() -> List[TradePair]:
    """
    Extract trade pairs from RASFF data.

    From country: origin column
    To countries: for_followUp column (comma-separated)

    Returns:
        List of TradePair objects
    """
    df = load_rasff_data()
    trade_pairs = []

    for _, row in df.iterrows():
        reference = str(row.get("reference", ""))
        origin = row.get("origin")
        follow_up = row.get("for_followUp")
        hs_code = row.get("hs_code")
        commodity = row.get("commodities")

        # Skip if no origin
        if pd.isna(origin) or not origin:
            continue

        origin = str(origin).strip()
        origin_code = get_m49_code(origin)

        # Handle HS code
        hs_code_str = None
        if pd.notna(hs_code):
            try:
                hs_code_str = str(int(float(hs_code)))
            except (ValueError, TypeError):
                hs_code_str = str(hs_code)

        # Parse follow_up countries
        if pd.notna(follow_up) and follow_up:
            to_countries = [c.strip() for c in str(follow_up).split(",")]

            for to_country in to_countries:
                if to_country:
                    to_code = get_m49_code(to_country)
                    trade_pairs.append(TradePair(
                        reference=reference,
                        from_country=origin,
                        from_country_code=origin_code,
                        to_country=to_country,
                        to_country_code=to_code,
                        hs_code=hs_code_str,
                        commodity=commodity if pd.notna(commodity) else None,
                    ))

    return trade_pairs


def get_unique_country_pairs() -> List[Tuple[str, str, str, str]]:
    """
    Get unique country pairs (from_code, to_code, from_name, to_name).

    Returns:
        List of tuples (from_code, to_code, from_name, to_name)
    """
    trade_pairs = extract_trade_pairs()

    # Use set for unique pairs
    unique_pairs: Set[Tuple[str, str, str, str]] = set()

    for pair in trade_pairs:
        if pair.from_country_code and pair.to_country_code:
            unique_pairs.add((
                pair.from_country_code,
                pair.to_country_code,
                pair.from_country,
                pair.to_country,
            ))

    return list(unique_pairs)


def get_unique_from_countries() -> Dict[str, str]:
    """
    Get unique 'from' countries with their M49 codes.

    Returns:
        Dict mapping country name to M49 code
    """
    df = load_rasff_data()
    origins = df["origin"].dropna().unique()

    result = {}
    for origin in origins:
        origin = str(origin).strip()
        code = get_m49_code(origin)
        if code:
            result[origin] = code

    return result


def get_unique_to_countries() -> Dict[str, str]:
    """
    Get unique 'to' countries (from for_followUp) with their M49 codes.

    Returns:
        Dict mapping country name to M49 code
    """
    df = load_rasff_data()
    follow_ups = df["for_followUp"].dropna()

    result = {}
    for follow_up in follow_ups:
        countries = [c.strip() for c in str(follow_up).split(",")]
        for country in countries:
            if country and country not in result:
                code = get_m49_code(country)
                if code:
                    result[country] = code

    return result


def get_trade_pairs_with_hs_codes(exclude_self_trade: bool = True) -> pd.DataFrame:
    """
    Get trade pairs grouped with their associated HS codes.

    Args:
        exclude_self_trade: If True, excludes pairs where from_country == to_country

    Returns:
        DataFrame with columns: from_country, from_code, to_country, to_code, hs_codes
    """
    trade_pairs = extract_trade_pairs()

    # Group by country pair
    pair_hs_codes: Dict[Tuple[str, str], Set[str]] = {}
    pair_info: Dict[Tuple[str, str], Tuple[str, str]] = {}

    for pair in trade_pairs:
        if pair.from_country_code and pair.to_country_code and pair.hs_code:
            # Skip self-trade if requested
            if exclude_self_trade and pair.from_country_code == pair.to_country_code:
                continue

            key = (pair.from_country_code, pair.to_country_code)
            if key not in pair_hs_codes:
                pair_hs_codes[key] = set()
                pair_info[key] = (pair.from_country, pair.to_country)
            pair_hs_codes[key].add(pair.hs_code)

    # Convert to DataFrame
    rows = []
    for (from_code, to_code), hs_codes in pair_hs_codes.items():
        from_name, to_name = pair_info[(from_code, to_code)]
        rows.append({
            "from_country": from_name,
            "from_code": from_code,
            "to_country": to_name,
            "to_code": to_code,
            "hs_codes": list(hs_codes),
            "hs_code_count": len(hs_codes),
        })

    return pd.DataFrame(rows)


def print_country_summary():
    """Print summary of countries in the dataset."""
    print("=" * 60)
    print("RASFF Country Data Summary")
    print("=" * 60)

    from_countries = get_unique_from_countries()
    print(f"\nUnique 'from' countries (origin): {len(from_countries)}")
    for name, code in sorted(from_countries.items()):
        print(f"  {name}: {code}")

    to_countries = get_unique_to_countries()
    print(f"\nUnique 'to' countries (for_followUp): {len(to_countries)}")
    for name, code in sorted(to_countries.items()):
        print(f"  {name}: {code}")

    pairs_df = get_trade_pairs_with_hs_codes()
    print(f"\nUnique country pairs: {len(pairs_df)}")
    print(f"Total HS codes across pairs: {pairs_df['hs_code_count'].sum()}")


if __name__ == "__main__":
    print_country_summary()

    print("\n\nSample trade pairs with HS codes:")
    df = get_trade_pairs_with_hs_codes()
    print(df.head(10).to_string())
