# ruff: noqa: F811  (pytest fixtures `c` and `clean` are imported from test_sales and injected by name)
"""M6: metrics, dashboard, P&L, cash flow, ageing, goals, GSTR-1/3B and the Excel workbooks, against hand-computed numbers."""

import io
import os
import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import text

from app.database import privileged_session
from tests.test_sales import bill, c, clean, gstin, item, regular, signup, staff  # noqa: F401

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").endswith("_test"), reason="needs anylo_test database"
)
PERIOD = f"{date.today():%Y-%m}"


def key() -> str:
    return str(uuid.uuid4())


def line_id(invoice_id: str) -> str:
    with privileged_session() as db:  # privileged: tests read across RLS to get the line id
        return str(
            db.execute(
                text("SELECT id FROM invoice_lines WHERE invoice_id = :i"), {"i": invoice_id}
            ).scalar()
        )


@pytest.fixture
def shop(c: TestClient) -> dict:
    """Regular shop. Shirt: ₹100 + 18% (cost 50). One B2C bill of 3, one B2B bill of 2 with ₹100 due, one return of 1 shirt."""
    h = signup(c)
    regular(c, h)
    v = item(c, h, "Shirt", "100.00", "18.00", stock="20")
    b2c = bill(
        c, h, [{"variant_id": v, "qty": "3"}], payments=[{"method": "cash", "amount": "354.00"}]
    )
    bill(
        c,
        h,
        [{"variant_id": v, "qty": "2"}],
        payments=[{"method": "upi", "amount": "136.00"}],
        customer={
            "phone": "9876500011",
            "name": "Ravi Traders",
            "gstin": gstin("32", "AAAPR1234A"),
        },
    )
    c.post(
        "/v1/credit-notes",
        headers=h,
        json={
            "invoice_id": b2c["id"],
            "lines": [{"invoice_line_id": line_id(b2c["id"]), "qty": "1"}],
            "refund_method": "cash",
            "idempotency_key": key(),
        },
    )
    c.post("/v1/expenses", headers=h, json={"category_name": "Rent", "amount": "100.00"})
    return {"h": h, "v": v}


def test_dashboard_metrics(c: TestClient, shop: dict) -> None:
    d = c.get("/v1/dashboard", headers=shop["h"]).json()
    m = d["current"]
    # Sales 354 + 236 = 590, return 118 → net 472. Revenue ex-tax 400, COGS (5 - 1 restocked) x 50 = 200.
    assert (m["gross_sales"], m["returns"], m["net_sales"]) == ("590.00", "118.00", "472.00")
    assert (m["net_revenue"], m["cogs"], m["gross_profit"], m["gross_margin_pct"]) == (
        "400.00",
        "200.00",
        "200.00",
        "50.0",
    )
    assert (m["expenses"], m["net_profit"], m["invoices_count"], m["output_tax"]) == (
        "100.00",
        "100.00",
        2,
        "72.00",
    )
    assert d["receivables"] == "100.00" and d["stock_value"] == "800.00"  # 16 shirts x 50
    assert {x["method"]: x["amount"] for x in d["payment_mix"]} == {
        "cash": "354.00",
        "upi": "136.00",
        "due": "100.00",
    }
    assert d["top_by_revenue"][0]["name"] == "Shirt" and d["staff"][0]["bills"] == 2
    assert sum(float(t["sales"]) for t in d["trend"]) == 472.0
    month = c.get("/v1/dashboard", headers=shop["h"], params={"from": str(date.today().replace(day=1)), "to": str(date.today())}).json()
    assert len(month["trend"]) == date.today().day  # one bar per day, empty days included
    assert c.get("/v1/dashboard", headers=staff(c, shop["h"])).status_code == 403


def test_pnl_cash_flow_and_ageing(c: TestClient, shop: dict) -> None:
    h = shop["h"]
    pl = c.get("/v1/reports/pnl", headers=h).json()
    assert pl["total"]["net_profit"] == "100.00" and pl["expenses_by_category"] == [
        {"name": "Rent", "amount": "100.00"}
    ]
    cf = c.get("/v1/reports/cash-flow", headers=h).json()
    flows = {(x["label"]): (x["cash"], x["bank"]) for x in cf["lines"]}
    assert flows["Sales"] == ("354.00", "136.00") and flows["Refunds to customers"] == (
        "118.00",
        "0",
    )
    assert cf["net_cash"] == "136.00" and cf["closing_cash"] == "136.00"  # 354 - 118 - 100 rent
    ar = c.get("/v1/reports/receivables", headers=h).json()
    assert ar["items"][0]["0_30"] == "100.00" and ar["totals"]["balance"] == "100.00"


def test_gstr1_sections_and_3b(c: TestClient, shop: dict) -> None:
    g = c.get("/v1/reports/gst/gstr1", headers=shop["h"], params={"period": PERIOD}).json()
    assert (
        len(g["b2b"]) == 1 and g["b2b"][0]["taxable"] == "200.00" and g["b2b"][0]["cgst"] == "18.00"
    )
    # B2CS: 300 sold, 100 returned on the same B2CS bill → netted to 200 (Table 7)
    assert [(r["rate"], r["taxable"], r["cgst"]) for r in g["b2cs"]] == [
        ("18.00", "200.00", "18.00")
    ]
    assert g["cdnr"] == [] and g["cdnur"] == []
    hsn = g["hsn"]["b2c"][0]
    assert (hsn["hsn"], hsn["qty"], hsn["taxable"]) == ("1006", "2.000", "200.00")
    assert g["docs"][0]["total"] == 2 and g["docs"][1]["nature"] == "Credit notes"
    g3 = c.get("/v1/reports/gst/gstr3b", headers=shop["h"], params={"period": PERIOD}).json()
    assert g3["outward_taxable"]["taxable"] == "400.00" and g3["payable"]["cgst"] == "36.00"
    assert (
        c.get("/v1/reports/gst/gstr1", headers=shop["h"], params={"period": "nope"}).json()["code"]
        == "gst.bad_period"
    )


def test_goals_progress_and_staff_view(c: TestClient, shop: dict) -> None:
    h = shop["h"]
    today = date.today()
    g = c.post(
        "/v1/goals",
        headers=h,
        json={
            "metric": "sales",
            "period_start": str(today),
            "period_end": str(today),
            "target": "400",
        },
    ).json()
    assert (g["actual"], g["status"], g["percent"]) == ("472.00", "achieved", "118.0")
    s = staff(c, h)
    c.post(
        "/v1/goals",
        headers=h,
        json={
            "metric": "invoices_count",
            "period_start": str(today.replace(day=1)),
            "period_end": "2099-12-31",
            "target": "1000",
            "user_id": None,
        },
    )
    assert len(c.get("/v1/goals", headers=s).json()) == 2
    assert (
        c.post(
            "/v1/goals",
            headers=s,
            json={
                "metric": "sales",
                "period_start": str(today),
                "period_end": str(today),
                "target": "1",
            },
        ).status_code
        == 403
    )
    c.delete(f"/v1/goals/{g['id']}", headers=h)
    left = c.get("/v1/goals", headers=h).json()
    assert len(left) == 1 and left[0]["status"] in ("behind", "at_risk", "on_track")


def test_excel_workbooks(c: TestClient, shop: dict) -> None:
    r = c.get("/v1/reports/export", headers=shop["h"])
    assert r.status_code == 200, r.text
    wb = load_workbook(io.BytesIO(r.content))
    assert {"Summary", "P&L", "Sales Register", "Receivables Ageing", "Goals"} <= set(wb.sheetnames)
    reg = wb["Sales Register"]
    assert reg.cell(5, 1).value.startswith("INV/") and str(reg.cell(7, 12).value).startswith(
        "=SUM("
    )
    g1 = load_workbook(
        io.BytesIO(
            c.get(
                "/v1/reports/export", headers=shop["h"], params={"kind": "gstr1", "period": PERIOD}
            ).content
        )
    )
    assert {"b2b", "b2cs", "hsn(b2c)", "docs", "GSTR-3B"} <= set(g1.sheetnames)
