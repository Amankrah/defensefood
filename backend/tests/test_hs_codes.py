"""HS / CPC normalisation and concordance coverage."""

from defensefood.ingestion.hs_codes import (
    cpc_to_hs_for_production,
    fbs_item_to_hs,
    hs_prefix,
    load_hs_cpc_concordance,
    normalize_cpc,
    normalize_cpc_raw,
    normalize_hs,
)


def test_normalize_hs_restores_leading_zero():
    assert normalize_hs(30617) == "030617"   # 5-digit fish code -> 6 digit
    assert normalize_hs("30731") == "030731"
    assert normalize_hs(1006) == "1006"       # 4-digit heading kept
    assert normalize_hs("100630") == "100630"
    assert normalize_hs("100630.0") == "100630"


def test_normalize_hs_rejects_garbage():
    assert normalize_hs(None) is None
    assert normalize_hs("abc") is None
    assert normalize_hs("") is None


def test_normalize_cpc_pads_to_five_for_numeric_sources():
    # Legacy zfill path - used when the source dropped leading zeros (numeric CSV)
    assert normalize_cpc(1929.0) == "01929"
    assert normalize_cpc("1910") == "01910"
    assert normalize_cpc(23720) == "23720"
    assert normalize_cpc("'04330") == "04330"


def test_normalize_cpc_raw_preserves_length():
    # Length-preserving path for apostrophe-protected sources where length
    # encodes hierarchy (FAOSTAT bulk CSVs and the rebuilt concordance).
    assert normalize_cpc_raw("'0111") == "0111"       # 4-digit class kept
    assert normalize_cpc_raw("'01371") == "01371"     # 5-digit subclass kept
    assert normalize_cpc_raw("'F1717") == "F1717"     # F-prefix aggregate kept
    assert normalize_cpc_raw("01199.90") == "01199.90"


def test_hs_prefix():
    assert hs_prefix("100630", 4) == "1006"
    assert hs_prefix(30617, 2) == "03"


def test_concordance_loads_with_new_schema():
    conc = load_hs_cpc_concordance()
    assert not conc.empty
    expected = {"commodity", "hs", "cpc", "fbs_item_code", "faostat_item", "confidence"}
    assert expected.issubset(set(conc.columns))
    # Mapped CPCs use FAOSTAT's actual vocabulary - includes 4-digit class codes
    rice_rows = conc[conc["hs"].str.startswith("1006")]
    assert (rice_rows["cpc"] == "0113").any(), "Rice HS should map to FAOSTAT CPC 0113"
    wheat_rows = conc[conc["hs"] == "100190"]
    assert (wheat_rows["cpc"] == "0111").any(), "Other-wheat HS should map to FAOSTAT CPC 0111"


def test_concordance_resolves_seafood_via_fbs():
    # Seafood has no QCL production but maps to FBS aggregates.
    conc = load_hs_cpc_concordance()
    mussels = conc[conc["hs"] == "030731"]
    assert not mussels.empty
    # CPC may be empty (no QCL) but FBS should be populated
    assert (mussels["fbs_item_code"] == "S2767").any()


def test_cpc_to_hs_for_production_includes_canonical_entries():
    mapping = cpc_to_hs_for_production()
    # FAOSTAT's actual CPC for wheat
    assert "0111" in mapping
    # Rice HS codes are under CPC 0113
    rice_hs = mapping.get("0113", [])
    assert any(h.startswith("1006") for h in rice_hs)


def test_fbs_item_to_hs_includes_canonical_entries():
    mapping = fbs_item_to_hs()
    # Wheat FBS aggregate
    assert "S2511" in mapping
    # Seafood molluscs aggregate
    assert "S2767" in mapping
