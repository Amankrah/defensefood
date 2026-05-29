"""HS / CPC normalisation and concordance coverage."""

from defensefood.ingestion.hs_codes import (
    cpc_for_hs,
    hs_prefix,
    load_hs_cpc_concordance,
    normalize_cpc,
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


def test_normalize_cpc_pads_to_five():
    assert normalize_cpc(1929.0) == "01929"
    assert normalize_cpc("1910") == "01910"
    assert normalize_cpc(23720) == "23720"
    assert normalize_cpc("'04330") == "04330"


def test_hs_prefix():
    assert hs_prefix("100630", 4) == "1006"
    assert hs_prefix(30617, 2) == "03"


def test_concordance_loads_and_resolves():
    conc = load_hs_cpc_concordance()
    assert not conc.empty
    assert set(conc.columns) == {"commodity", "hs", "cpc"}
    # every code in the concordance is canonical
    assert all(len(c) == 5 for c in conc["cpc"])


def test_cpc_for_hs_exact_and_rollup():
    # mussels HS 030731 -> CPC 04330
    assert "04330" in cpc_for_hs("30731")
    # rice heading 1006 resolves via 4-digit rollup to its CPC children
    assert cpc_for_hs(1006), "1006 heading should resolve to at least one CPC"
