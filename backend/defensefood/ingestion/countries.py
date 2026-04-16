"""
Country M49 code mappings for UN Comtrade API.

Refactored from backend/script/country_loader.py.
"""

from typing import Optional

import pandas as pd


M49_COUNTRY_CODES: dict[str, int] = {
    # World / All
    "World": 0,
    "All": 0,
    # European Union
    "Austria": 40, "Belgium": 56, "Bulgaria": 100, "Croatia": 191,
    "Cyprus": 196, "Czech Republic": 203, "Czechia": 203, "Denmark": 208,
    "Estonia": 233, "Finland": 246, "France": 251, "Germany": 276,
    "Greece": 300, "Hungary": 348, "Ireland": 372, "Italy": 380,
    "Latvia": 428, "Lithuania": 440, "Luxembourg": 442, "Malta": 470,
    "Netherlands": 528, "Poland": 616, "Portugal": 620, "Romania": 642,
    "Slovakia": 703, "Slovenia": 705, "Spain": 724, "Sweden": 752,
    # Other European
    "Albania": 8, "Andorra": 20, "Belarus": 112,
    "Bosnia and Herzegovina": 70, "Iceland": 352, "Kosovo": 412,
    "Liechtenstein": 438, "Moldova": 498, "Monaco": 492,
    "Montenegro": 499, "North Macedonia": 807, "Norway": 578,
    "Russia": 643, "Russian Federation": 643, "San Marino": 674,
    "Serbia": 688, "Switzerland": 756, "Turkey": 792, "Türkiye": 792,
    "Ukraine": 804, "United Kingdom": 826, "UK": 826, "Vatican City": 336,
    "Georgia": 268,
    # North America
    "Canada": 124, "Mexico": 484,
    "United States": 842, "USA": 842, "United States of America": 842,
    # South America
    "Argentina": 32, "Bolivia": 68, "Brazil": 76, "Chile": 152,
    "Colombia": 170, "Ecuador": 218, "Guyana": 328, "Paraguay": 600,
    "Peru": 604, "Suriname": 740, "Uruguay": 858, "Venezuela": 862,
    # Asia
    "Afghanistan": 4, "Bangladesh": 50, "Cambodia": 116, "China": 156,
    "Hong Kong": 344, "India": 356, "Indonesia": 360, "Iran": 364,
    "Iraq": 368, "Israel": 376, "Japan": 392, "Jordan": 400,
    "Kazakhstan": 398, "Kuwait": 414, "Laos": 418, "Lebanon": 422,
    "Malaysia": 458, "Mongolia": 496, "Myanmar": 104, "Nepal": 524,
    "North Korea": 408, "Oman": 512, "Pakistan": 586, "Philippines": 608,
    "Qatar": 634, "Saudi Arabia": 682, "Singapore": 702,
    "South Korea": 410, "Korea": 410, "Sri Lanka": 144, "Syria": 760,
    "Taiwan": 158, "Thailand": 764, "Turkmenistan": 795,
    "United Arab Emirates": 784, "UAE": 784, "Uzbekistan": 860,
    "Vietnam": 704, "Viet Nam": 704, "Yemen": 887,
    # Africa
    "Algeria": 12, "Angola": 24, "Benin": 204, "Botswana": 72,
    "Burkina Faso": 854, "Cameroon": 120,
    "Cote d'Ivoire": 384, "C\u00f4te d'Ivoire": 384,
    "Ivory Coast": 384, "Egypt": 818, "Ethiopia": 231, "Ghana": 288,
    "Kenya": 404, "Libya": 434, "Madagascar": 450, "Mali": 466,
    "Morocco": 504, "Mozambique": 508, "Namibia": 516, "Niger": 562,
    "Nigeria": 566, "Senegal": 686, "South Africa": 710, "Sudan": 729,
    "Tanzania": 834, "Tunisia": 788, "Togo": 768, "Uganda": 800,
    "Rwanda": 646, "Zambia": 894, "Zimbabwe": 716,
    "Chad": 148, "Congo (Brazzaville)": 178, "Djibouti": 262,
    "Gabon": 266, "Mauritius": 480,
    # Oceania
    "Australia": 36, "Fiji": 242, "New Zealand": 554, "Papua New Guinea": 598,
    # Central America & Caribbean
    "Costa Rica": 188, "Cuba": 192, "Dominican Republic": 214,
    "El Salvador": 222, "Guatemala": 320, "Haiti": 332, "Honduras": 340,
    "Jamaica": 388, "Nicaragua": 558, "Panama": 591, "Puerto Rico": 630,
    "Trinidad and Tobago": 780,
    # Additional (from RASFF unmapped)
    "Azerbaijan": 31, "Falkland Islands": 238,
}

# EU27 member state M49 codes
EU27_M49 = {
    40, 56, 100, 191, 196, 203, 208, 233, 246, 251, 276, 300, 348,
    372, 380, 428, 440, 442, 470, 528, 616, 620, 642, 703, 705, 724, 752,
}

# Build reverse lookup: M49 -> canonical country name
_M49_TO_NAME: dict[int, str] = {}
for _name, _code in M49_COUNTRY_CODES.items():
    if _code not in _M49_TO_NAME:
        _M49_TO_NAME[_code] = _name


def get_m49_code(country_name: str) -> Optional[int]:
    """Look up M49 code from country name (case-insensitive, partial match)."""
    if not country_name or (isinstance(country_name, float) and pd.isna(country_name)):
        return None

    name = str(country_name).strip()

    # Exact match (case-insensitive)
    for key, code in M49_COUNTRY_CODES.items():
        if key.lower() == name.lower():
            return code

    # Partial match
    name_lower = name.lower()
    for key, code in M49_COUNTRY_CODES.items():
        if name_lower in key.lower() or key.lower() in name_lower:
            return code

    return None


def get_country_name(m49_code: int) -> Optional[str]:
    """Look up canonical country name from M49 code."""
    return _M49_TO_NAME.get(m49_code)


def is_eu27(m49_code: int) -> bool:
    """Check if a country is an EU27 member state."""
    return m49_code in EU27_M49
