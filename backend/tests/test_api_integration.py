"""End-to-end API integration against the real data on disk.

Skips automatically if the RASFF / trade source files aren't present, so the
unit suite still runs in a bare checkout.
"""

import pytest
from fastapi.testclient import TestClient

from defensefood.api import dependencies
from defensefood.ingestion.rasff import _get_rasff_path


def _data_available() -> bool:
    return _get_rasff_path().exists()


pytestmark = pytest.mark.skipif(
    not _data_available(), reason="RASFF source data not present"
)


@pytest.fixture(scope="module")
def client():
    dependencies.reload_data()  # fresh enriched state
    from defensefood.api.main import app
    with TestClient(app) as c:  # triggers lifespan -> scoring
        yield c


def test_health_ok(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert "status" in r.json()


def test_corridors_carry_dependency_fields(client):
    r = client.get("/api/v1/corridors?limit=500")
    assert r.status_code == 200
    corridors = r.json()["corridors"]
    assert corridors
    # At least some corridors must now carry Section 2 metrics.
    with_sci = [c for c in corridors if c.get("sci") is not None]
    assert with_sci, "no corridor received an SCI after startup enrichment"


def test_full_profile_has_dependency_and_cvs(client):
    top = client.get("/api/v1/corridors/top?sort_by=cvs&n=20").json()["corridors"]
    scored = [c for c in top if c.get("cvs") is not None]
    assert scored, "expected at least one corridor with a non-null CVS"

    c = scored[0]
    r = client.get(
        f"/api/v1/corridors/{c['commodity_hs']}/{c['destination_m49']}/{c['origin_m49']}/full"
    )
    assert r.status_code == 200
    body = r.json()
    assert body["dependency"] is not None
    assert "idr" in body["dependency"]
    assert body["cvs"] is not None
    assert body["cvs_mode"] in ("sci_his", "sci_crs_his")
