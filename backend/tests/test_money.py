# ruff: noqa: F811  (pytest fixtures `c` and `clean` are imported from test_sales and injected by name)
"""M4: customers + khata, FIFO collections, approvals, credit notes, expenses, borrowings, cash and labour."""

import os
import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from tests.test_sales import bill, c, clean, item, regular, signup, staff  # noqa: F401  (fixtures + helpers)

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").endswith("_test"), reason="needs anylo_test database"
)
PHONE = "9876500011"


def key() -> str:
    return str(uuid.uuid4())


def due_bill(
    c: TestClient, h: dict, v: str, qty: str, paid: str | None = None, phone: str = PHONE
) -> dict:
    pays = [{"method": "cash", "amount": paid}] if paid else []
    return bill(
        c,
        h,
        [{"variant_id": v, "qty": qty}],
        payments=pays,
        customer={"phone": phone, "name": "Ravi"},
    )


def cust(c: TestClient, h: dict, phone: str = PHONE) -> dict:
    return c.get("/v1/customers/lookup", headers=h, params={"phone": phone}).json()[0]


def test_tenant_tables_force_rls() -> None:
    eng = create_engine(os.environ["DATABASE_URL_OWNER"])
    with eng.connect() as conn:
        missing = (
            conn.execute(
                text(
                    "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
                    " WHERE n.nspname = 'public' AND c.relkind = 'r' AND (NOT c.relrowsecurity OR NOT c.relforcerowsecurity)"
                    " AND EXISTS (SELECT 1 FROM information_schema.columns k WHERE k.table_name = c.relname AND k.column_name = 'shop_id')"
                )
            )
            .scalars()
            .all()
        )
    eng.dispose()
    assert missing == [], f"tables with shop_id but no forced RLS: {missing}"


def test_lookup_by_first_digits_profile_and_isolation(c: TestClient) -> None:
    h = signup(c)
    regular(c, h)
    v = item(c, h, "Rice", "100.00", "0.00")
    due_bill(c, h, v, "2")
    c.post("/v1/customers", headers=h, json={"name": "Asha", "phone": "9876511111"})
    assert (
        c.get("/v1/customers/lookup", headers=h, params={"phone": "9876"}).json() == []
    )  # needs 5 digits
    names = {
        x["name"]
        for x in c.get("/v1/customers/lookup", headers=h, params={"phone": "98765"}).json()
    }
    assert names == {"Ravi", "Asha"}
    assert [
        x["name"]
        for x in c.get("/v1/customers/lookup", headers=h, params={"phone": "9876500"}).json()
    ] == ["Ravi"]
    dup = c.post("/v1/customers", headers=h, json={"name": "X", "phone": PHONE})
    assert dup.status_code == 409 and dup.json()["code"] == "customer.phone_taken"
    r = cust(c, h)
    assert r["balance"] == "200.00"
    prof = c.get(f"/v1/customers/{r['id']}", headers=h).json()
    assert prof["bills"] == 1 and prof["spent"] == "200.00"
    assert c.delete(f"/v1/customers/{r['id']}", headers=h).json()["code"] == "customer.has_balance"
    other = signup(c, 2)
    assert c.get("/v1/customers/lookup", headers=other, params={"phone": "98765"}).json() == []
    assert c.get(f"/v1/customers/{r['id']}", headers=other).status_code == 404


def test_fifo_collection_receipt_ledger_and_replay(c: TestClient) -> None:
    h = signup(c)
    regular(c, h)
    v = item(c, h, "Rice", "100.00", "0.00", stock="50")
    b1 = due_bill(c, h, v, "3", paid="100.00")  # 200 due
    b2 = due_bill(c, h, v, "2")  # 200 due
    cid = cust(c, h)["id"]
    body = {"amount": "250.00", "method": "upi", "idempotency_key": key()}
    r = c.post(f"/v1/customers/{cid}/payments", headers=h, json=body)
    assert r.status_code == 201, r.text
    rc = r.json()
    assert rc["receipt_no"].startswith("RCPT/") and rc["status"] == "confirmed"
    assert [a["amount"] for a in rc["allocations"]] == ["200.00", "50.00"]  # oldest bill first
    assert rc["balance_after"] == "150.00"
    again = c.post(f"/v1/customers/{cid}/payments", headers=h, json=body)
    assert again.status_code == 200 and again.headers["Idempotent-Replay"] == "true"
    dues = {i["number"]: i["due_total"] for i in c.get("/v1/invoices", headers=h).json()["items"]}
    assert dues[b1["number"]] == "0.00" and dues[b2["number"]] == "150.00"
    too_much = c.post(
        f"/v1/customers/{cid}/payments",
        headers=h,
        json={"amount": "151.00", "idempotency_key": key()},
    )
    assert too_much.json()["code"] == "collection.more_than_due"
    led = c.get(f"/v1/customers/{cid}/ledger", headers=h).json()
    assert [e["kind"] for e in led["entries"]] == [
        "bill",
        "paid_at_bill",
        "bill",
        "payment",
        "payment",
    ]
    assert led["entries"][-1]["balance"] == led["balance"] == "150.00"


def test_salesperson_collection_needs_approval(c: TestClient) -> None:
    h = signup(c)
    regular(c, h)
    v = item(c, h, "Rice", "100.00", "0.00")
    due_bill(c, h, v, "2")
    cid = cust(c, h)["id"]
    s = staff(c, h)
    r = c.post(
        f"/v1/customers/{cid}/payments",
        headers=s,
        json={"amount": "100.00", "idempotency_key": key()},
    ).json()
    assert r["status"] == "pending_approval"
    assert cust(c, h)["balance"] == "200.00"  # not counted until approved
    assert c.get("/v1/cash/today", headers=h).json()["pending_cash"] == "100.00"
    assert c.get("/v1/approvals", headers=s).status_code == 403
    pending = c.get("/v1/approvals", headers=h).json()
    assert len(pending) == 1 and pending[0]["kind"] == "collection"
    assert (
        c.post(f"/v1/approvals/{pending[0]['id']}/approve", headers=h, json={}).json()["status"]
        == "approved"
    )
    assert cust(c, h)["balance"] == "100.00"
    assert (
        c.post(f"/v1/approvals/{pending[0]['id']}/approve", headers=h, json={}).json()["code"]
        == "approval.decided"
    )
    # a rejected collection never touches the balance
    c.post(
        f"/v1/customers/{cid}/payments",
        headers=s,
        json={"amount": "50.00", "idempotency_key": key()},
    )
    rid = c.get("/v1/approvals", headers=h).json()[0]["id"]
    c.post(f"/v1/approvals/{rid}/reject", headers=h, json={"note": "not received"})
    assert cust(c, h)["balance"] == "100.00"


def test_credit_note_pro_rata_restock_refund_and_rules(c: TestClient) -> None:
    h = signup(c)
    regular(c, h)
    v = item(c, h, "Shirt", "118.00", "18.00", inclusive=True, stock="10")
    inv = bill(
        c, h, [{"variant_id": v, "qty": "3"}], payments=[{"method": "cash", "amount": "354.00"}]
    )
    full = c.get(f"/v1/invoices/{inv['id']}", headers=h).json()
    line = c.get("/v1/credit-notes", headers=h, params={"invoice_id": inv["id"]}).json()["items"]
    assert line == []
    eng = create_engine(os.environ["DATABASE_URL_OWNER"])
    with eng.connect() as conn:
        conn.execute(text("SET app.role = 'system'"))
        line_id = conn.execute(
            text("SELECT id FROM invoice_lines WHERE invoice_id = :i"), {"i": inv["id"]}
        ).scalar()
    eng.dispose()
    r = c.post(
        "/v1/credit-notes",
        headers=h,
        json={
            "invoice_id": inv["id"],
            "lines": [{"invoice_line_id": str(line_id), "qty": "1"}],
            "refund_method": "cash",
            "idempotency_key": key(),
        },
    )
    assert r.status_code == 201, r.text
    cn = r.json()
    assert cn["number"].startswith("CN/") and cn["invoice_number"] == full["number"]
    assert (cn["taxable_total"], cn["cgst_total"], cn["sgst_total"], cn["grand_total"]) == (
        "100.00",
        "9.00",
        "9.00",
        "118.00",
    )
    assert cn["refunded"] == "118.00"
    stock = c.get("/v1/products", headers=h).json()["items"][0]["variants"][0]["stock_qty"]
    assert stock == "8"  # 10 - 3 + 1
    # the remainder takes the exact leftover; more than that is refused
    over = c.post(
        "/v1/credit-notes",
        headers=h,
        json={
            "invoice_id": inv["id"],
            "lines": [{"invoice_line_id": str(line_id), "qty": "3"}],
            "idempotency_key": key(),
        },
    )
    assert over.json()["code"] == "credit_note.too_many"
    rest = c.post(
        "/v1/credit-notes",
        headers=h,
        json={
            "invoice_id": inv["id"],
            "lines": [{"invoice_line_id": str(line_id), "qty": "2"}],
            "restock": False,
            "idempotency_key": key(),
        },
    ).json()
    assert rest["grand_total"] == "236.00"
    assert (
        c.post(f"/v1/invoices/{inv['id']}/cancel", headers=h, json={"reason": "mistake"}).json()[
            "code"
        ]
        == "invoice.has_returns"
    )
    cash = c.get("/v1/cash/today", headers=h).json()
    assert cash["cash_in"] == "354.00" and cash["cash_out"] == "354.00"


def test_return_on_due_bill_clears_due_and_store_credit(c: TestClient) -> None:
    h = signup(c)
    regular(c, h)
    v = item(c, h, "Rice", "100.00", "0.00")
    inv = due_bill(c, h, v, "3", paid="100.00")  # 200 due
    eng = create_engine(os.environ["DATABASE_URL_OWNER"])
    with eng.connect() as conn:
        conn.execute(text("SET app.role = 'system'"))
        line_id = str(
            conn.execute(
                text("SELECT id FROM invoice_lines WHERE invoice_id = :i"), {"i": inv["id"]}
            ).scalar()
        )
    eng.dispose()
    cn = c.post(
        "/v1/credit-notes",
        headers=h,
        json={
            "invoice_id": inv["id"],
            "lines": [{"invoice_line_id": line_id, "qty": "3"}],
            "refund_method": "store_credit",
            "idempotency_key": key(),
        },
    ).json()
    assert cn["due_adjusted"] == "200.00" and cn["refunded"] == "0.00"
    assert cn["customer_balance"] == "-100.00"  # the 100 they paid is now store credit


def test_salesperson_return_goes_through_approval(c: TestClient) -> None:
    h = signup(c)
    regular(c, h)
    v = item(c, h, "Rice", "100.00", "0.00")
    s = staff(c, h)
    inv = bill(
        c, s, [{"variant_id": v, "qty": "2"}], payments=[{"method": "cash", "amount": "200.00"}]
    )
    eng = create_engine(os.environ["DATABASE_URL_OWNER"])
    with eng.connect() as conn:
        conn.execute(text("SET app.role = 'system'"))
        line_id = str(
            conn.execute(
                text("SELECT id FROM invoice_lines WHERE invoice_id = :i"), {"i": inv["id"]}
            ).scalar()
        )
    eng.dispose()
    r = c.post(
        "/v1/credit-notes",
        headers=s,
        json={
            "invoice_id": inv["id"],
            "lines": [{"invoice_line_id": line_id, "qty": "1"}],
            "idempotency_key": key(),
        },
    )
    assert r.status_code == 202 and r.json()["approval_required"]
    assert c.get("/v1/credit-notes", headers=h).json()["items"] == []
    done = c.post(f"/v1/approvals/{r.json()['approval_id']}/approve", headers=h, json={}).json()
    assert done["result"]["grand_total"] == "100.00"
    assert len(c.get("/v1/credit-notes", headers=h).json()["items"]) == 1


def test_credit_limit_blocks_salesperson_only(c: TestClient) -> None:
    h = signup(c)
    regular(c, h)
    v = item(c, h, "Rice", "100.00", "0.00", stock="50")
    due_bill(c, h, v, "1")
    cid = cust(c, h)["id"]
    c.put(
        f"/v1/customers/{cid}",
        headers=h,
        json={"name": "Ravi", "phone": PHONE, "credit_limit": "250.00"},
    )
    s = staff(c, h)
    body = {
        "lines": [{"variant_id": v, "qty": "2"}],
        "customer": {"phone": PHONE},
        "idempotency_key": key(),
    }
    assert c.post("/v1/invoices", headers=s, json=body).json()["code"] == "invoice.credit_limit"
    assert c.post("/v1/invoices", headers=h, json=body).status_code == 201  # owner decides


def test_expenses_borrowings_cash_and_day_close(c: TestClient) -> None:
    h = signup(c)
    cats = c.get("/v1/expenses/categories", headers=h).json()
    assert "Rent" in {x["name"] for x in cats}
    e = c.post("/v1/expenses", headers=h, json={"category_name": "Tea", "amount": "40.00"}).json()
    c.post(
        "/v1/expenses",
        headers=h,
        json={"category_id": cats[0]["id"], "amount": "500.00", "method": "upi"},
    )
    lst = c.get("/v1/expenses", headers=h).json()
    assert lst["total"] == "540.00" and len(lst["items"]) == 2
    c.put(f"/v1/expenses/{e['id']}", headers=h, json={"category_name": "Tea", "amount": "60.00"})
    b = c.post(
        "/v1/borrowings", headers=h, json={"lender_name": "Uncle", "principal": "1000.00"}
    ).json()
    assert b["outstanding"] == "1000.00"
    assert (
        c.post(f"/v1/borrowings/{b['id']}/repay", headers=h, json={"amount": "1200.00"}).json()[
            "code"
        ]
        == "borrowing.overpay"
    )
    paid = c.post(f"/v1/borrowings/{b['id']}/repay", headers=h, json={"amount": "1000.00"}).json()
    assert paid["status"] == "closed"
    t = c.get("/v1/cash/today", headers=h).json()
    assert (t["cash_in"], t["cash_out"], t["expected_cash"]) == ("1000.00", "1060.00", "-60.00")
    c.delete(f"/v1/expenses/{e['id']}", headers=h)
    t = c.get("/v1/cash/today", headers=h).json()
    assert t["expected_cash"] == "0.00"
    book = c.get("/v1/cash/book", headers=h).json()
    labels = [x["label"] for x in book["entries"]]
    assert (
        "Borrowed from Uncle" in labels
        and "Repaid Uncle" in labels
        and book["closing_cash"] == "0.00"
    )
    closed = c.post("/v1/cash/close", headers=h, json={"counted_cash": "0.00"}).json()
    assert closed["close"]["status"] == "confirmed"
    assert (
        c.post("/v1/cash/close", headers=h, json={"counted_cash": "0.00"}).json()["code"]
        == "cash.already_closed"
    )
    s = staff(c, h)
    assert c.post("/v1/expenses", headers=s, json={"amount": "10.00"}).status_code == 201
    assert c.delete(f"/v1/expenses/{lst['items'][0]['id']}", headers=s).status_code == 403
    assert c.get("/v1/borrowings", headers=s).status_code == 403


def test_opening_cash_carries_from_last_close(c: TestClient) -> None:
    h = signup(c)
    eng = create_engine(os.environ["DATABASE_URL_OWNER"])
    yesterday = date.today() - timedelta(days=3)
    with eng.begin() as conn:
        conn.execute(text("SET LOCAL app.role = 'system'"))
        sid = conn.execute(text("SELECT id FROM shops LIMIT 1")).scalar()
        conn.execute(
            text(
                "INSERT INTO day_closes (shop_id, business_date, opening_cash, cash_in, cash_out, expected_cash, counted_cash,"
                " difference, status) VALUES (:s, :d, 0, 500, 0, 500, 480, -20, 'confirmed')"
            ),
            {"s": sid, "d": yesterday},
        )
    eng.dispose()
    assert c.get("/v1/cash/today", headers=h).json()["opening_cash"] == "480.00"


def test_salesperson_day_close_needs_confirmation(c: TestClient) -> None:
    h = signup(c)
    s = staff(c, h)
    t = c.post("/v1/cash/close", headers=s, json={"counted_cash": "0.00", "note": "ok"}).json()
    assert t["close"]["status"] == "pending"
    rid = c.get("/v1/approvals", headers=h).json()[0]["id"]
    c.post(f"/v1/approvals/{rid}/approve", headers=h, json={})
    assert c.get("/v1/cash/today", headers=h).json()["close"]["status"] == "confirmed"


def test_labour_attendance_pay_and_balance(c: TestClient) -> None:
    h = signup(c)
    today = date.today()
    w = c.post(
        "/v1/labour/workers",
        headers=h,
        json={
            "name": "Suresh",
            "gender": "male",
            "daily_wage": "500.00",
            "joined_on": str(today - timedelta(days=5)),
        },
    ).json()
    s = staff(c, h)
    for d, st in ((1, "present"), (2, "half_day"), (3, "absent")):
        r = c.post(
            "/v1/labour/attendance",
            headers=s,
            json={"labourer_id": w["id"], "day": str(today - timedelta(days=d)), "status": st},
        )
        assert r.status_code == 200, r.text
    future = c.post(
        "/v1/labour/attendance",
        headers=h,
        json={"labourer_id": w["id"], "day": str(today + timedelta(days=1)), "status": "present"},
    )
    assert future.json()["code"] == "labour.future"
    assert (
        c.post(
            "/v1/labour/payments", headers=s, json={"labourer_id": w["id"], "cash_amount": "100.00"}
        ).status_code
        == 403
    )
    after = c.post(
        "/v1/labour/payments",
        headers=h,
        json={"labourer_id": w["id"], "cash_amount": "300.00", "upi_amount": "100.00"},
    ).json()
    assert (after["earned"], after["total_paid"], after["balance_to_pay"]) == (
        "750.00",
        "400.00",
        "350.00",
    )
    assert c.get("/v1/cash/today", headers=h).json()["cash_out"] == "300.00"
    st = c.get(f"/v1/labour/workers/{w['id']}/statement", headers=h).json()
    assert len(st["attendance"]) == 3 and st["payments"][0]["upi_amount"] == "100.00"
    c.delete(f"/v1/labour/payments/{st['payments'][0]['id']}", headers=h)
    assert c.get("/v1/labour/workers", headers=h).json()["items"][0]["balance_to_pay"] == "750.00"
    no_wage = c.post("/v1/labour/workers", headers=h, json={"name": "X", "gender": "other"})
    assert no_wage.json()["code"] == "labour.no_wage"


def test_owner_manages_expense_categories(c: TestClient) -> None:
    h = signup(c)
    c.get("/v1/expenses/categories", headers=h)
    tea = c.post("/v1/expenses/categories", headers=h, json={"name": "Tea & snacks"})
    assert tea.status_code == 201
    names = [x["name"] for x in c.get("/v1/expenses/categories", headers=h).json()]
    assert "Tea & snacks" in names and "Rent" in names
    s = staff(c, h)
    assert c.post("/v1/expenses/categories", headers=s, json={"name": "Party"}).status_code == 403
    assert (
        c.post("/v1/expenses", headers=s, json={"category_name": "Party", "amount": "10"}).json()[
            "code"
        ]
        == "expense.category_not_allowed"
    )
    assert (
        c.post(
            "/v1/expenses", headers=s, json={"category_name": "tea & snacks", "amount": "10"}
        ).status_code
        == 201
    )  # existing, any case
    rent = next(
        x for x in c.get("/v1/expenses/categories", headers=h).json() if x["name"] == "Rent"
    )
    assert (
        c.delete(f"/v1/expenses/categories/{rent['id']}", headers=h).json()["code"]
        == "expense.category_system"
    )
    assert c.delete(f"/v1/expenses/categories/{tea.json()['id']}", headers=h).status_code == 204
    assert (
        c.get("/v1/expenses", headers=h).json()["items"][0]["category_name"] == "Tea & snacks"
    )  # history keeps the name
