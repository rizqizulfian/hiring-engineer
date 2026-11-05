"""Tests for the cached weekly report.

Raw data and the cost counters are shared by every test in one run, and a
loaded delta cannot be undone. Keep the startup test before the delta test.
"""

from fastapi.testclient import TestClient

from app.main import app

W10 = "/shops/SHP141660/weekly-report?week=2025-W10"

def test_startup_twice_does_not_double_the_cache():
    with TestClient(app) as client:
        cost_1 = client.get("/stats").json()["rows_scanned"]
        report_1 = client.get(W10).json()
    with TestClient(app) as client:        # startup() jalan lagi
        cost_2 = client.get("/stats").json()["rows_scanned"]
        report_2 = client.get(W10).json()
    assert cost_2 == cost_1        # tidak ada scan tambahan
    assert report_2 == report_1      # laporan tidak berubah
    assert report_2["revenue"] == 429524900

def test_delta_refreshes_only_affected_reports():
    with TestClient(app) as client:
        before = client.get("/stats").json()["rows_scanned"]
        assert client.post("/load-delta").json()["loaded"] is True
        after = client.get("/stats").json()["rows_scanned"]
        report = client.get(W10).json()
    assert after - before == 63956          # 17.458 + 46.498
    assert report["revenue"] == 429344900
    assert report["units"] == 1818