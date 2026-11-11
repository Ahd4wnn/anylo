# ruff: noqa: F811  (pytest fixtures `c` and `clean` are imported from test_sales and injected by name)
"""M7 books & compliance: CMP-08 taxable turnover, expense ITC / reverse charge, CA role, bank matching,
capital & drawings, depreciation, year locks, filings and the balance sheet."""

import os
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.services.books import depreciation, parse_statement
from tests.test_sales import bill, c, clean, gstin, item, regular, signup, staff  # noqa: F401

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").endswith("_test"), reason="needs anylo_test database"
)
TODAY = date.today()
PERIOD = f"{TODAY:%Y-%m}"


def test_depreciation_half_rate_and_sale() -> None:
    # Computer ₹1,00,000 bought 1 Dec 2025: used 121 days in FY 25-26 → half of 40%.
    d1 = depreciation(Decimal("100000"), 40, date(2025, 12, 1), None, None, date(2026, 3, 1))
    assert (d1["depreciation"], d1["closing"]) == (Decimal("20000.00"), Decimal("80000.00"))
    d2 = depreciation(Decimal("100000"), 40, date(2025, 12, 1), None, None, date(2026, 6, 1))
    assert (d2["opening"], d2["depreciation"]) == (Decimal("80000.00"), Decimal("32000.00"))
    sold = depreciation(
        Decimal("100000"),
        40,
        date(2025, 12, 1),
        date(2026, 5, 1),
        Decimal("90000"),
        date(2026, 6, 1),
    )
    assert sold["closing"] == 0 and sold["sale_gain"] == Decimal("10000.00")


def test_parse_statement_with_preamble_and_debit_credit() -> None:
    rows = [
        ["Account statement for XXXX1234"],
        [],
        ["Txn Date", "Narration", "Chq./Ref.No.", "Withdrawal Amt.", "Deposit Amt.", "Balance"],
        ["01/11/2026", "UPI/RAVI", "UTR1", "", "1,180.00", "5000"],
        ["02-11-2026", "NEFT RENT", "UTR2", "500.00", "", "4500"],
        ["", "Closing balance", "", "", "", "4500"],
    ]
    assert parse_statement(rows) == [
        (date(2026, 11, 1), "UPI/RAVI", "UTR1", Decimal("1180.00")),
        (date(2026, 11, 2), "NEFT RENT", "UTR2", Decimal("-500.00")),
    ]


def test_cmp08_counts_taxable_turnover_only(c: TestClient) -> None:
    h = signup(c)
    c.put("/v1/shop/tax-profile", headers=h, json={"gst_scheme": "composition", "gstin": gstin()})
    v = item(c, h, "Soap", "100.00", "18.00")
    exempt = next(
        r["id"] for r in c.get("/v1/gst-rates", headers=h).json() if r["kind"] == "exempt"
    )
    bill(
        c,
        h,
        [
            {"variant_id": v, "qty": "1"},
            {"custom": {"name": "Spinach", "tax_rate_id": exempt}, "qty": "1", "unit_price": "50"},
        ],
        payments=[{"method": "cash", "amount": "150.00"}],
    )
    r = c.get("/v1/reports/gst/cmp08", headers=h, params={"from": str(TODAY), "to": str(TODAY)})
    assert r.json()["turnover"] == "100.00", r.text


def test_expense_itc_and_reverse_charge_in_3b(c: TestClient) -> None:
    h = signup(c)
    regular(c, h)
    c.post(
        "/v1/expenses",
        headers=h,
        json={"category_name": "Repairs", "amount": "118.00", "gst_amount": "18.00"},
    )
    c.post(
        "/v1/expenses",
        headers=h,
        json={
            "category_name": "Rent",
            "amount": "1000.00",
            "reverse_charge": True,
            "rcm_rate": "18",
            "supplier_name": "Landlord",
        },
    )
    g = c.get("/v1/reports/gst/gstr3b", headers=h, params={"period": PERIOD}).json()
    assert g["inward_rcm"]["cgst"] == "90.00" and g["inward_rcm"]["sgst"] == "90.00"
    # ITC = 9 + 9 from repairs, plus the RCM paid (90 + 90)
    assert (g["itc"]["cgst"], g["itc"]["sgst"]) == ("99.00", "99.00")
    pl = c.get("/v1/reports/pnl", headers=h).json()
    assert pl["total"]["expenses"] == "1100.00"  # ₹18 GST claimed back isn't a cost


def test_accountant_reads_but_cannot_write(c: TestClient) -> None:
    h = signup(c)
    ca = staff(c, h, "accountant")
    assert c.get("/v1/reports/pnl", headers=ca).status_code == 200
    assert c.get("/v1/books/position", headers=ca).status_code == 200
    assert c.get("/v1/expenses", headers=ca).status_code == 200
    assert (
        c.post(
            "/v1/expenses", headers=ca, json={"category_name": "Rent", "amount": "1"}
        ).status_code
        == 403
    )
    assert c.post("/v1/invoices", headers=ca, json={}).status_code in (403, 422)
    manager = staff(c, h, "manager")
    r = c.post(
        "/v1/shop/staff",
        headers=manager,
        json={"full_name": "CA Two", "email": "ca2@shop.in", "role": "accountant"},
    )
    assert r.status_code == 403  # only the owner invites the accountant


def test_bank_import_matches_upi_sale(c: TestClient) -> None:
    h = signup(c)
    regular(c, h)
    v = item(c, h, "Shirt", "100.00", "18.00", stock="5")
    bill(c, h, [{"variant_id": v, "qty": "1"}], payments=[{"method": "upi", "amount": "118.00"}])
    bank = c.post(
        "/v1/books/banks", headers=h, json={"name": "SBI Current", "account_last4": "1234"}
    ).json()
    assert bank["is_default"] and bank["book_balance"] == "118.00"
    csv = f"Date,Description,Reference,Amount\n{TODAY:%d/%m/%Y},UPI credit,UTR9,118.00\n{TODAY:%d/%m/%Y},Bank charges,,-5.90\n"
    r = c.post(
        f"/v1/books/banks/{bank['id']}/statement",
        headers=h,
        files={"file": ("st.csv", csv.encode(), "text/csv")},
    ).json()
    assert (r["added"], r["matched"], r["unmatched"]) == (2, 1, 1)
    again = c.post(
        f"/v1/books/banks/{bank['id']}/statement",
        headers=h,
        files={"file": ("st.csv", csv.encode(), "text/csv")},
    ).json()
    assert again["added"] == 0  # importing the same statement twice adds nothing
    rec = c.get(f"/v1/books/banks/{bank['id']}/reconciliation", headers=h).json()
    assert rec["bank"]["statement_balance"] == "112.10" and rec["not_in_statement"] == []


def test_capital_drawings_assets_and_balance_sheet(c: TestClient) -> None:
    h = signup(c)
    regular(c, h)
    c.put("/v1/books/settings", headers=h, json={"opening_cash": "1000.00"})
    c.post("/v1/books/owner", headers=h, json={"kind": "capital", "amount": "5000"})
    c.post("/v1/books/owner", headers=h, json={"kind": "drawing", "amount": "700"})
    v = item(c, h, "Shirt", "100.00", "18.00", stock="10")
    bill(c, h, [{"variant_id": v, "qty": "2"}], payments=[{"method": "cash", "amount": "236.00"}])
    c.post(
        "/v1/books/assets",
        headers=h,
        json={
            "name": "Billing PC",
            "block": "computer",
            "cost": "3000",
            "bought_on": str(TODAY),
            "paid_method": "cash",
        },
    )
    p = c.get("/v1/books/position", headers=h).json()
    assets = {a["name"]: a["amount"] for a in p["assets"]}
    # 1000 opening + 5000 capital - 700 drawings + 236 sale - 3000 PC
    assert assets["Cash in hand"] == "2536.00"
    assert assets["Closing stock"] == "400.00"  # 8 x 50
    assert p["total_assets"] == p["total_liabilities_capital"]
    assert p["trial_totals"]["debit"] == p["trial_totals"]["credit"]
    tb = {r["account"]: r for r in p["trial_balance"]}
    assert tb["Drawings"]["debit"] == "700.00" and tb["Capital introduced"]["credit"] == "5000.00"
    cf = c.get("/v1/reports/cash-flow", headers=h).json()
    labels = {x["label"] for x in cf["lines"]}
    assert {"Capital introduced", "Owner drawings", "Assets bought"} <= labels
    ca = staff(c, h, "accountant")
    assert (
        c.post("/v1/books/owner", headers=ca, json={"kind": "capital", "amount": "1"}).status_code
        == 403
    )


def test_year_lock_blocks_backdated_changes(c: TestClient) -> None:
    h = signup(c)
    last_fy_end = date(TODAY.year if TODAY.month >= 4 else TODAY.year - 1, 3, 31)
    fy = f"{last_fy_end.year - 1}-{last_fy_end.year % 100:02d}"
    old = last_fy_end - timedelta(days=10)
    e = c.post(
        "/v1/expenses",
        headers=h,
        json={"category_name": "Rent", "amount": "100", "occurred_on": str(old)},
    ).json()
    assert c.post("/v1/books/locks", headers=h, json={"fy": fy}).status_code == 200
    r = c.post(
        "/v1/expenses",
        headers=h,
        json={"category_name": "Rent", "amount": "100", "occurred_on": str(old)},
    )
    assert r.status_code == 409 and r.json()["code"] == "books.locked"
    assert c.delete(f"/v1/expenses/{e['id']}", headers=h).json()["code"] == "books.locked"
    assert (
        c.post(
            "/v1/books/locks",
            headers=h,
            json={"fy": f"{TODAY.year + 1}-{(TODAY.year + 2) % 100:02d}"},
        ).json()["code"]
        == "books.year_open"
    )
    c.delete(f"/v1/books/locks/{fy}", headers=h)
    assert c.delete(f"/v1/expenses/{e['id']}", headers=h).status_code == 204


def test_filings_and_calendar(c: TestClient) -> None:
    h = signup(c)
    regular(c, h)
    cal = c.get("/v1/books/calendar", headers=h).json()
    first = next(x for x in cal if x["return_type"] == "GSTR3B")
    assert first["status"] in ("overdue", "due_soon", "upcoming")
    r = c.post(
        "/v1/books/filings",
        headers=h,
        json={
            "return_type": "GSTR3B",
            "period": first["period"],
            "filed_on": str(TODAY),
            "arn": "AA321126000001X",
            "tax_paid": "250",
        },
    )
    assert r.status_code == 201, r.text
    cal = c.get("/v1/books/calendar", headers=h).json()
    done = next(x for x in cal if (x["return_type"], x["period"]) == ("GSTR3B", first["period"]))
    assert done["status"] == "filed" and done["arn"] == "AA321126000001X"
    assert (
        c.post(
            "/v1/books/filings",
            headers=h,
            json={"return_type": "GSTR3B", "period": first["period"], "filed_on": str(TODAY)},
        ).json()["code"]
        == "books.filed_already"
    )
    cf = c.get("/v1/reports/cash-flow", headers=h).json()
    assert any(x["label"] == "Tax paid" for x in cf["lines"])
