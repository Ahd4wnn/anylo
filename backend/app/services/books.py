"""Books & compliance (docs/19-roadmap.md M7): opening balances, bank accounts and statement matching,
owner capital/drawings, filings + compliance calendar, fixed assets with income-tax WDV depreciation,
year locks, balance sheet and trial balance."""

import re
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.database import Actor
from app.errors import AppError
from app.schemas.money import q2
from app.services import audit
from app.services.catalogue_io import MAX_FILE, sheet_rows
from app.services.finance.metrics import balances, compute
from app.services.sales import ShopCtx, _q, _today, shop_ctx

ZERO = Decimal("0")
NON_CASH = ("upi", "card", "bank", "cheque")
# Income-tax Act block rates (WDV). ponytail: one rate per block; ask a CA for special blocks (e.g. 15% vs 30% vehicles).
BLOCK_RATE = {"furniture": 10, "plant": 15, "computer": 40, "vehicle": 15, "building": 10}


def fy_start(d: date) -> date:
    return date(d.year if d.month >= 4 else d.year - 1, 4, 1)


def fy_name(d: date) -> str:
    s = fy_start(d).year
    return f"{s}-{(s + 1) % 100:02d}"


def _fy_end(fy: str) -> date:
    m = re.fullmatch(r"(\d{4})-(\d{2})", fy)
    if not m or (int(m[1]) + 1) % 100 != int(m[2]):
        raise AppError("books.bad_fy", "Write the year as 2025-26.", 422)
    return date(int(m[1]) + 1, 3, 31)


# --- period lock ---


def ensure_open(db: Session, shop_id: UUID, day: date) -> None:
    """Closed years can't change: the CA has filed on those numbers."""
    locked = _q(
        db,
        "SELECT fy FROM book_locks WHERE shop_id = :s AND locked_until >= :d LIMIT 1",
        s=shop_id,
        d=day,
    ).scalar()
    if locked:
        raise AppError(
            "books.locked",
            f"The books for {locked} are closed. Ask the owner to reopen the year first.",
            409,
        )


def locks(db: Session, actor: Actor) -> list[dict[str, Any]]:
    ctx = shop_ctx(db, actor)
    return [
        dict(r)
        for r in _q(
            db,
            "SELECT fy, locked_until, locked_at FROM book_locks WHERE shop_id = :s ORDER BY fy",
            s=ctx.id,
        ).mappings()
    ]


def lock_year(db: Session, actor: Actor, fy: str) -> list[dict[str, Any]]:
    ctx = shop_ctx(db, actor)
    end = _fy_end(fy)
    if end >= _today(ctx):
        raise AppError("books.year_open", "A year can be closed only after 31 March.", 409)
    _q(
        db,
        "INSERT INTO book_locks (shop_id, fy, locked_until, locked_by) VALUES (:s, :f, :e, :u)"
        " ON CONFLICT (shop_id, fy) DO NOTHING",
        s=ctx.id,
        f=fy,
        e=end,
        u=actor.user_id,
    )
    audit.record(db, actor, "book_lock", ctx.id, "lock", None, {"fy": fy})
    return locks(db, actor)


def unlock_year(db: Session, actor: Actor, fy: str) -> list[dict[str, Any]]:
    ctx = shop_ctx(db, actor)
    _q(db, "DELETE FROM book_locks WHERE shop_id = :s AND fy = :f", s=ctx.id, f=fy)
    audit.record(db, actor, "book_lock", ctx.id, "unlock", {"fy": fy}, None)
    return locks(db, actor)


# --- settings (opening balances) ---


def _start(db: Session, ctx: ShopCtx) -> date:
    r = _q(
        db,
        "SELECT coalesce(books_start, (created_at AT TIME ZONE :tz)::date) FROM shops WHERE id = :s",
        s=ctx.id,
        tz=str(ctx.tz),
    ).scalar()
    assert isinstance(r, date)
    return r


def settings(db: Session, actor: Actor) -> dict[str, Any]:
    ctx = shop_ctx(db, actor)
    cash = _q(db, "SELECT opening_cash FROM shops WHERE id = :s", s=ctx.id).scalar()
    return {"books_start": _start(db, ctx), "opening_cash": cash}


def update_settings(
    db: Session, actor: Actor, books_start: date | None, opening_cash: Decimal
) -> dict[str, Any]:
    ctx = shop_ctx(db, actor)
    if books_start:
        ensure_open(db, ctx.id, books_start)
    before = settings(db, actor)
    _q(
        db,
        "UPDATE shops SET books_start = :b, opening_cash = :c WHERE id = :s",
        b=books_start,
        c=opening_cash,
        s=ctx.id,
    )
    after = settings(db, actor)
    audit.record(db, actor, "shop", ctx.id, "books_settings", _j(before), _j(after))
    return after


def _j(d: dict[str, Any]) -> dict[str, str]:
    return {k: str(v) for k, v in d.items()}


# --- bank accounts ---


def _bank_sql(where: str) -> str:
    # Non-cash money with no bank chosen lands in the default account.
    return f"""
    SELECT a.id, a.name, a.account_last4, a.opening_balance, a.is_default,
      a.opening_balance + coalesce((SELECT sum(CASE WHEN p.direction = 'in' THEN p.amount ELSE -p.amount END) FROM payments p
        WHERE p.shop_id = a.shop_id AND p.status = 'confirmed' AND p.method IN ('upi','card','bank','cheque')
          AND (p.bank_account_id = a.id OR (p.bank_account_id IS NULL AND a.is_default))), 0) AS book_balance,
      a.opening_balance + coalesce((SELECT sum(l.amount) FROM bank_lines l WHERE l.bank_account_id = a.id), 0) AS statement_balance,
      (SELECT count(*) FROM bank_lines l WHERE l.bank_account_id = a.id AND l.payment_id IS NULL) AS unmatched
    FROM bank_accounts a WHERE {where} AND a.deleted_at IS NULL ORDER BY a.is_default DESC, a.name"""


def banks(db: Session, actor: Actor) -> list[dict[str, Any]]:
    ctx = shop_ctx(db, actor)
    return [dict(r) for r in _q(db, _bank_sql("a.shop_id = :s"), s=ctx.id).mappings()]


def _bank(db: Session, ctx: ShopCtx, bid: UUID) -> dict[str, Any]:
    r = _q(db, _bank_sql("a.id = :i AND a.shop_id = :s"), i=bid, s=ctx.id).mappings().first()
    if not r:
        raise AppError("bank.not_found", "This bank account was not found.", 404)
    return dict(r)


def add_bank(
    db: Session,
    actor: Actor,
    name: str,
    last4: str | None,
    opening: Decimal,
    is_default: bool,
) -> dict[str, Any]:
    ctx = shop_ctx(db, actor)
    first = not _q(
        db, "SELECT 1 FROM bank_accounts WHERE shop_id = :s AND deleted_at IS NULL", s=ctx.id
    ).first()
    if is_default or first:
        _q(db, "UPDATE bank_accounts SET is_default = false WHERE shop_id = :s", s=ctx.id)
    bid = _q(
        db,
        "INSERT INTO bank_accounts (shop_id, name, account_last4, opening_balance, is_default)"
        " VALUES (:s, :n, :l, :o, :d) RETURNING id",
        s=ctx.id,
        n=name.strip(),
        l=last4,
        o=opening,
        d=is_default or first,
    ).scalar_one()
    audit.record(db, actor, "bank_account", bid, "create", None, {"name": name})
    return _bank(db, ctx, bid)


def delete_bank(db: Session, actor: Actor, bid: UUID) -> None:
    ctx = shop_ctx(db, actor)
    b = _bank(db, ctx, bid)
    _q(
        db,
        "UPDATE bank_accounts SET deleted_at = now(), is_default = false WHERE id = :i",
        i=bid,
    )
    audit.record(db, actor, "bank_account", bid, "delete", {"name": b["name"]}, None)


DATE_FORMATS = ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d-%b-%Y", "%d %b %Y", "%d/%m/%y", "%d-%m-%y")
COLS = {
    "date": ("date", "txn_date", "transaction_date", "value_date", "tran_date", "value_dt"),
    "description": ("description", "narration", "particulars", "remarks", "details"),
    "reference": ("reference", "ref", "ref_no", "chq_ref_no", "cheque_no", "utr", "chq_no"),
    "amount": ("amount",),
    "debit": ("debit", "withdrawal", "withdrawals", "withdrawal_amt", "dr"),
    "credit": ("credit", "deposit", "deposits", "deposit_amt", "cr"),
}


def _date(v: str) -> date:
    v = v.strip().split(" ")[0] if re.match(r"\d{4}-\d{2}-\d{2} ", v) else v.strip()
    for f in DATE_FORMATS:
        try:
            return datetime.strptime(v, f).date()
        except ValueError:
            pass
    raise ValueError(v)


def _num(v: str) -> Decimal:
    v = v.replace(",", "").replace("₹", "").strip()
    return Decimal(v) if v else ZERO


def parse_statement(rows: list[list[str]]) -> list[tuple[date, str, str, Decimal]]:
    """Find the header row (banks put a few lines of account details above it) and read the lines."""
    for i, row in enumerate(rows[:30]):  # noqa: B007  (i is the header row, used below)
        head = [re.sub(r"[^a-z0-9]+", "_", c.lower()).strip("_") for c in row]
        col = {
            k: next((head.index(n) for n in names if n in head), None) for k, names in COLS.items()
        }
        if col["date"] is not None and (
            col["amount"] is not None or (col["debit"] is not None and col["credit"] is not None)
        ):
            break
    else:
        raise AppError(
            "bank.columns",
            "Couldn't find Date and Amount (or Debit and Credit) columns in this statement.",
            400,
        )

    def cell(r: list[str], k: str) -> str:
        j = col[k]
        return r[j] if j is not None and j < len(r) else ""

    out = []
    for r in rows[i + 1 :]:
        try:
            day = _date(cell(r, "date"))
        except ValueError:
            continue  # totals, opening-balance and footer rows
        try:
            amt = (
                _num(cell(r, "amount"))
                if col["amount"] is not None
                else _num(cell(r, "credit")) - _num(cell(r, "debit"))
            )
        except ArithmeticError:
            continue
        if amt:
            out.append((day, cell(r, "description")[:300], cell(r, "reference")[:80], amt))
    return out


def import_statement(
    db: Session, actor: Actor, bid: UUID, data: bytes, filename: str
) -> dict[str, Any]:
    ctx = shop_ctx(db, actor)
    _bank(db, ctx, bid)
    if len(data) > MAX_FILE:
        raise AppError("import.too_large", "The file is too big. Keep it under 10 MB.", 413)
    lines = parse_statement(sheet_rows(data, filename))
    added = 0
    for day, desc, ref, amt in lines:
        added += _q(
            db,
            "INSERT INTO bank_lines (shop_id, bank_account_id, txn_date, description, reference, amount)"
            " VALUES (:s, :b, :d, :ds, :r, :a) ON CONFLICT DO NOTHING",
            s=ctx.id,
            b=bid,
            d=day,
            ds=desc,
            r=ref,
            a=amt,
        ).rowcount
    matched = auto_match(db, ctx, bid)
    audit.record(db, actor, "bank_account", bid, "import", None, {"lines": added})
    return {"read": len(lines), "added": added, "matched": matched} | _bank(db, ctx, bid)


def auto_match(db: Session, ctx: ShopCtx, bid: UUID) -> int:
    """Same amount and direction, within 3 days; the closest date wins."""
    n = 0
    for line in _q(
        db,
        "SELECT l.id, l.txn_date, l.amount, a.is_default FROM bank_lines l JOIN bank_accounts a ON a.id = l.bank_account_id"
        " WHERE l.bank_account_id = :b AND l.payment_id IS NULL ORDER BY l.txn_date",
        b=bid,
    ).all():
        pid = _q(
            db,
            "SELECT p.id FROM payments p WHERE p.shop_id = :s AND p.status = 'confirmed' AND p.method IN ('upi','card','bank','cheque')"
            " AND p.direction = :dir AND p.amount = :a AND (p.bank_account_id = :b OR (p.bank_account_id IS NULL AND :dflt))"
            " AND (p.occurred_at AT TIME ZONE :tz)::date BETWEEN :d1 AND :d2"
            " AND NOT EXISTS (SELECT 1 FROM bank_lines x WHERE x.payment_id = p.id)"
            " ORDER BY abs((p.occurred_at AT TIME ZONE :tz)::date - :d) LIMIT 1",
            s=ctx.id,
            dir="in" if line.amount > 0 else "out",
            a=abs(line.amount),
            b=bid,
            dflt=line.is_default,
            tz=str(ctx.tz),
            d=line.txn_date,
            d1=line.txn_date - timedelta(days=3),
            d2=line.txn_date + timedelta(days=3),
        ).scalar()
        if pid:
            _q(db, "UPDATE bank_lines SET payment_id = :p WHERE id = :i", p=pid, i=line.id)
            n += 1
    return n


def reconciliation(db: Session, actor: Actor, bid: UUID) -> dict[str, Any]:
    ctx = shop_ctx(db, actor)
    bank = _bank(db, ctx, bid)
    lines = [
        dict(r)
        for r in _q(
            db,
            "SELECT l.id, l.txn_date, l.description, l.reference, l.amount, l.payment_id,"
            " p.method, p.applies_to_type, p.note FROM bank_lines l LEFT JOIN payments p ON p.id = l.payment_id"
            " WHERE l.bank_account_id = :b ORDER BY l.txn_date DESC, l.imported_at DESC LIMIT 500",
            b=bid,
        ).mappings()
    ]
    # In Anylo but not on the statement yet (cheques not cleared, UPI not settled, or a wrong entry).
    pending = [
        dict(r)
        for r in _q(
            db,
            "SELECT p.id, p.occurred_at, p.direction, p.method, p.amount, p.applies_to_type, p.note FROM payments p"
            " WHERE p.shop_id = :s AND p.status = 'confirmed' AND p.method IN ('upi','card','bank','cheque')"
            " AND (p.bank_account_id = :b OR (p.bank_account_id IS NULL AND :dflt))"
            " AND NOT EXISTS (SELECT 1 FROM bank_lines x WHERE x.payment_id = p.id)"
            " AND p.occurred_at >= coalesce((SELECT min(txn_date) FROM bank_lines WHERE bank_account_id = :b), now())"
            " ORDER BY p.occurred_at DESC LIMIT 500",
            s=ctx.id,
            b=bid,
            dflt=bank["is_default"],
        ).mappings()
    ]
    return {"bank": bank, "lines": lines, "not_in_statement": pending}


def match_line(db: Session, actor: Actor, line_id: UUID, payment_id: UUID | None) -> dict[str, Any]:
    ctx = shop_ctx(db, actor)
    line = _q(
        db, "SELECT * FROM bank_lines WHERE id = :i AND shop_id = :s", i=line_id, s=ctx.id
    ).first()
    if not line:
        raise AppError("bank.line_not_found", "This statement line was not found.", 404)
    if payment_id:
        p = _q(
            db,
            "SELECT amount, direction FROM payments WHERE id = :i AND shop_id = :s AND status = 'confirmed'",
            i=payment_id,
            s=ctx.id,
        ).first()
        if not p or p.amount != abs(line.amount) or (p.direction == "in") != (line.amount > 0):
            raise AppError("bank.mismatch", "The amount or direction doesn't match this line.", 422)
        if _q(db, "SELECT 1 FROM bank_lines WHERE payment_id = :p", p=payment_id).first():
            raise AppError("bank.already_matched", "That entry is already matched.", 409)
    _q(db, "UPDATE bank_lines SET payment_id = :p WHERE id = :i", p=payment_id, i=line_id)
    return reconciliation(db, actor, line.bank_account_id)


# --- owner capital & drawings ---


def owner_money(db: Session, actor: Actor) -> dict[str, Any]:
    ctx = shop_ctx(db, actor)
    rows = [
        dict(r)
        for r in _q(
            db,
            "SELECT id, applies_to_type AS kind, method, amount, occurred_at, note FROM payments"
            " WHERE shop_id = :s AND applies_to_type IN ('capital','drawing') AND status = 'confirmed'"
            " ORDER BY occurred_at DESC",
            s=ctx.id,
        ).mappings()
    ]
    total = {
        k: sum((r["amount"] for r in rows if r["kind"] == k), ZERO) for k in ("capital", "drawing")
    }
    return {"items": rows, "capital": total["capital"], "drawings": total["drawing"]}


def add_owner_money(
    db: Session,
    actor: Actor,
    kind: str,
    amount: Decimal,
    method: str,
    on: date | None,
    note: str | None,
    bank_account_id: UUID | None,
) -> dict[str, Any]:
    """Capital in, or money the owner takes home. Drawings are never an expense."""
    ctx = shop_ctx(db, actor)
    day = on or _today(ctx)
    if day > _today(ctx):
        raise AppError("books.future", "This can't be dated in the future.", 422)
    ensure_open(db, ctx.id, day)
    if bank_account_id:
        _bank(db, ctx, bank_account_id)
    pid = _q(
        db,
        "INSERT INTO payments (shop_id, direction, method, amount, applies_to_type, received_by, occurred_at, note,"
        " bank_account_id) VALUES (:s, :d, :m, :a, :k, :u, :o, :n, :b) RETURNING id",
        s=ctx.id,
        d="in" if kind == "capital" else "out",
        m=method,
        a=amount,
        k=kind,
        u=actor.user_id,
        o=_at(ctx, day),
        n=note,
        b=bank_account_id if method != "cash" else None,
    ).scalar_one()
    audit.record(db, actor, "payment", pid, kind, None, {"amount": str(amount)})
    return owner_money(db, actor)


def delete_owner_money(db: Session, actor: Actor, pid: UUID) -> dict[str, Any]:
    ctx = shop_ctx(db, actor)
    r = _q(
        db,
        "UPDATE payments SET status = 'reversed' WHERE id = :i AND shop_id = :s AND applies_to_type IN ('capital','drawing')"
        " AND status = 'confirmed' RETURNING amount, applies_to_type, occurred_at",
        i=pid,
        s=ctx.id,
    ).first()
    if not r:
        raise AppError("books.not_found", "This entry was not found.", 404)
    ensure_open(db, ctx.id, r.occurred_at.astimezone(ctx.tz).date())
    audit.record(
        db,
        actor,
        "payment",
        pid,
        "reverse",
        {"kind": r.applies_to_type, "amount": str(r.amount)},
        None,
    )
    return owner_money(db, actor)


def _at(ctx: ShopCtx, day: date) -> datetime:
    now = datetime.now(UTC)
    return now if day == now.astimezone(ctx.tz).date() else datetime.combine(day, time(12), ctx.tz)


# --- filings & compliance calendar ---

NAMES = {
    "GSTR1": "GSTR-1",
    "GSTR3B": "GSTR-3B",
    "CMP08": "CMP-08",
    "GSTR4": "GSTR-4",
    "GSTR9": "GSTR-9",
    "ITR": "Income-tax return",
    "ADVANCE_TAX": "Advance tax",
}


def calendar(db: Session, actor: Actor, today: date | None = None) -> list[dict[str, Any]]:
    """Due dates from 2 months back to 4 months ahead. ponytail: standard due dates; the government
    often extends them, and QRMP / audit cases have other dates."""
    ctx = shop_ctx(db, actor)
    today = today or _today(ctx)
    lo, hi = today - timedelta(days=62), today + timedelta(days=124)
    due: list[tuple[str, str, date]] = []

    def month(y: int, m: int) -> tuple[int, int]:
        return (y + (m - 1) // 12, (m - 1) % 12 + 1)

    for k in range(-4, 6):
        y, m = month(today.year, today.month + k)
        ny, nm = month(y, m + 1)
        if ctx.scheme == "regular":
            due.append(("GSTR1", f"{y}-{m:02d}", date(ny, nm, 11)))
            due.append(("GSTR3B", f"{y}-{m:02d}", date(ny, nm, 20)))
        elif ctx.scheme == "composition" and m in (6, 9, 12, 3):
            q = {6: 1, 9: 2, 12: 3, 3: 4}[m]
            due.append(("CMP08", f"{fy_name(date(y, m, 1))} Q{q}", date(ny, nm, 18)))
    for y in (today.year - 1, today.year, today.year + 1):
        prev = f"{y - 1}-{y % 100:02d}"  # the FY that ended on 31 March of year y
        due.append(("ITR", prev, date(y, 7, 31)))
        if ctx.scheme == "composition":
            due.append(("GSTR4", prev, date(y, 4, 30)))
        if ctx.scheme == "regular":
            due.append(("GSTR9", prev, date(y, 12, 31)))
        cur = f"{y}-{(y + 1) % 100:02d}"
        for i, (mm, yy) in enumerate(((6, y), (9, y), (12, y), (3, y + 1)), start=1):
            due.append(("ADVANCE_TAX", f"{cur} #{i}", date(yy, mm, 15)))
    filed = {
        (r.return_type, r.period): r
        for r in _q(
            db,
            "SELECT return_type, period, filed_on, arn FROM filings WHERE shop_id = :s",
            s=ctx.id,
        )
    }
    out = []
    for kind, period, d in sorted(due, key=lambda x: (x[2], x[0])):
        if not lo <= d <= hi:
            continue
        f = filed.get((kind, period))
        status = (
            "filed"
            if f
            else "overdue"
            if d < today
            else "due_soon"
            if d <= today + timedelta(days=7)
            else "upcoming"
        )
        out.append(
            {
                "return_type": kind,
                "name": NAMES[kind],
                "period": period,
                "due_on": d,
                "status": status,
                "filed_on": f.filed_on if f else None,
                "arn": f.arn if f else None,
            }
        )
    return out


def filings(db: Session, actor: Actor) -> list[dict[str, Any]]:
    ctx = shop_ctx(db, actor)
    return [
        dict(r)
        for r in _q(
            db,
            "SELECT id, return_type, period, filed_on, arn, tax_paid, note FROM filings WHERE shop_id = :s"
            " ORDER BY filed_on DESC, created_at DESC",
            s=ctx.id,
        ).mappings()
    ]


def add_filing(
    db: Session,
    actor: Actor,
    return_type: str,
    period: str,
    filed_on: date,
    arn: str | None,
    tax_paid: Decimal,
    method: str,
    note: str | None,
) -> list[dict[str, Any]]:
    ctx = shop_ctx(db, actor)
    if filed_on > _today(ctx):
        raise AppError("books.future", "This can't be dated in the future.", 422)
    fid = _q(
        db,
        "INSERT INTO filings (shop_id, return_type, period, filed_on, arn, tax_paid, note, created_by)"
        " VALUES (:s, :t, :p, :f, :a, :tp, :n, :u) ON CONFLICT (shop_id, return_type, period) DO NOTHING RETURNING id",
        s=ctx.id,
        t=return_type,
        p=period.strip(),
        f=filed_on,
        a=arn,
        tp=tax_paid,
        n=note,
        u=actor.user_id,
    ).scalar()
    if not fid:
        raise AppError("books.filed_already", "This return is already marked as filed.", 409)
    if tax_paid > 0:
        # Tax paid with the return leaves the shop's money; it isn't a business expense.
        _q(
            db,
            "INSERT INTO payments (shop_id, direction, method, amount, applies_to_type, applies_to_id, received_by,"
            " occurred_at, note) VALUES (:s, 'out', :m, :a, 'tax', :i, :u, :o, :n)",
            s=ctx.id,
            m=method,
            a=tax_paid,
            i=fid,
            u=actor.user_id,
            o=_at(ctx, filed_on),
            n=f"{NAMES.get(return_type, return_type)} {period}",
        )
    audit.record(db, actor, "filing", fid, "create", None, {"type": return_type, "period": period})
    return filings(db, actor)


def delete_filing(db: Session, actor: Actor, fid: UUID) -> list[dict[str, Any]]:
    ctx = shop_ctx(db, actor)
    r = _q(
        db,
        "DELETE FROM filings WHERE id = :i AND shop_id = :s RETURNING return_type, period",
        i=fid,
        s=ctx.id,
    ).first()
    if not r:
        raise AppError("books.not_found", "This entry was not found.", 404)
    _q(
        db,
        "UPDATE payments SET status = 'reversed' WHERE applies_to_type = 'tax' AND applies_to_id = :i",
        i=fid,
    )
    audit.record(
        db, actor, "filing", fid, "delete", {"type": r.return_type, "period": r.period}, None
    )
    return filings(db, actor)


# --- fixed assets ---


def depreciation(
    cost: Decimal, rate: int, bought: date, sold: date | None, sale: Decimal | None, fy_of: date
) -> dict[str, Decimal]:
    """WDV per income-tax rules for the FY containing `fy_of`: half rate if used under 180 days in the
    year it was bought, nothing in the year it's sold (profit/loss instead)."""
    wdv, start = cost, fy_start(bought)
    target = fy_start(fy_of)
    while True:
        end = date(start.year + 1, 3, 31)
        if sold and sold <= end:
            gain = (sale or ZERO) - wdv
            return {"opening": wdv, "depreciation": ZERO, "closing": ZERO, "sale_gain": gain}
        days = (end - bought).days + 1 if start == fy_start(bought) else 365
        dep = q2(wdv * rate / 100 / (2 if days < 180 else 1))
        if start == target:
            return {"opening": wdv, "depreciation": dep, "closing": wdv - dep, "sale_gain": ZERO}
        wdv -= dep
        start = date(start.year + 1, 4, 1)


def assets(db: Session, actor: Actor, as_of: date | None = None) -> dict[str, Any]:
    ctx = shop_ctx(db, actor)
    as_of = as_of or _today(ctx)
    items = []
    for r in _q(
        db,
        "SELECT id, name, block, cost, bought_on, paid_method, sold_on, sale_value FROM fixed_assets"
        " WHERE shop_id = :s AND deleted_at IS NULL AND bought_on <= :d ORDER BY bought_on",
        s=ctx.id,
        d=as_of,
    ).mappings():
        rate = BLOCK_RATE[r["block"]]
        sold = r["sold_on"] if r["sold_on"] and r["sold_on"] <= as_of else None
        d = depreciation(r["cost"], rate, r["bought_on"], sold, r["sale_value"], as_of)
        items.append(dict(r) | {"rate": rate} | d)
    tot = {
        k: sum((i[k] for i in items), ZERO)
        for k in ("cost", "opening", "depreciation", "closing", "sale_gain")
    }
    return {"fy": fy_name(as_of), "items": items, "totals": tot}


def add_asset(
    db: Session,
    actor: Actor,
    name: str,
    block: str,
    cost: Decimal,
    bought_on: date,
    paid_method: str | None,
) -> dict[str, Any]:
    ctx = shop_ctx(db, actor)
    if bought_on > _today(ctx):
        raise AppError("books.future", "This can't be dated in the future.", 422)
    ensure_open(db, ctx.id, bought_on)
    aid = _q(
        db,
        "INSERT INTO fixed_assets (shop_id, name, block, cost, bought_on, paid_method)"
        " VALUES (:s, :n, :b, :c, :d, :m) RETURNING id",
        s=ctx.id,
        n=name.strip(),
        b=block,
        c=cost,
        d=bought_on,
        m=paid_method,
    ).scalar_one()
    if paid_method:
        _q(
            db,
            "INSERT INTO payments (shop_id, direction, method, amount, applies_to_type, applies_to_id, received_by,"
            " occurred_at, note) VALUES (:s, 'out', :m, :a, 'asset', :i, :u, :o, :n)",
            s=ctx.id,
            m=paid_method,
            a=cost,
            i=aid,
            u=actor.user_id,
            o=_at(ctx, bought_on),
            n=name.strip(),
        )
    audit.record(db, actor, "fixed_asset", aid, "create", None, {"name": name, "cost": str(cost)})
    return assets(db, actor)


def sell_asset(
    db: Session, actor: Actor, aid: UUID, sold_on: date, value: Decimal, method: str
) -> dict[str, Any]:
    ctx = shop_ctx(db, actor)
    a = _q(
        db,
        "SELECT name, bought_on, sold_on FROM fixed_assets WHERE id = :i AND shop_id = :s AND deleted_at IS NULL",
        i=aid,
        s=ctx.id,
    ).first()
    if not a or a.sold_on:
        raise AppError("books.not_found", "This asset was not found or is already sold.", 404)
    if not a.bought_on <= sold_on <= _today(ctx):
        raise AppError("books.bad_date", "Pick a date between purchase and today.", 422)
    ensure_open(db, ctx.id, sold_on)
    _q(
        db,
        "UPDATE fixed_assets SET sold_on = :d, sale_value = :v WHERE id = :i",
        d=sold_on,
        v=value,
        i=aid,
    )
    if value > 0:
        _q(
            db,
            "INSERT INTO payments (shop_id, direction, method, amount, applies_to_type, applies_to_id, received_by,"
            " occurred_at, note) VALUES (:s, 'in', :m, :a, 'asset', :i, :u, :o, :n)",
            s=ctx.id,
            m=method,
            a=value,
            i=aid,
            u=actor.user_id,
            o=_at(ctx, sold_on),
            n=f"Sold {a.name}",
        )
    audit.record(db, actor, "fixed_asset", aid, "sell", None, {"value": str(value)})
    return assets(db, actor)


def delete_asset(db: Session, actor: Actor, aid: UUID) -> dict[str, Any]:
    ctx = shop_ctx(db, actor)
    a = _q(
        db,
        "UPDATE fixed_assets SET deleted_at = now() WHERE id = :i AND shop_id = :s AND deleted_at IS NULL"
        " RETURNING name, bought_on",
        i=aid,
        s=ctx.id,
    ).first()
    if not a:
        raise AppError("books.not_found", "This asset was not found.", 404)
    ensure_open(db, ctx.id, a.bought_on)
    _q(
        db,
        "UPDATE payments SET status = 'reversed' WHERE applies_to_type = 'asset' AND applies_to_id = :i",
        i=aid,
    )
    audit.record(db, actor, "fixed_asset", aid, "delete", {"name": a.name}, None)
    return assets(db, actor)


# --- balance sheet & trial balance ---


def _money_sum(db: Session, ctx: ShopCtx, start: date, end: date, where: str) -> Decimal:
    a = datetime.combine(start, time(0), ctx.tz)
    b = datetime.combine(end + timedelta(days=1), time(0), ctx.tz)
    r = _q(
        db,
        "SELECT coalesce(sum(CASE WHEN direction = 'in' THEN amount ELSE -amount END), 0) FROM payments"
        f" WHERE shop_id = :s AND status = 'confirmed' AND occurred_at >= :a AND occurred_at < :b AND {where}",
        s=ctx.id,
        a=a,
        b=b,
    ).scalar()
    assert isinstance(r, Decimal)
    return r


def position(db: Session, actor: Actor, as_of: date | None = None) -> dict[str, Any]:
    """Balance sheet and trial balance from the same numbers, since the books start.
    ponytail: receivables, payables and stock are today's figures (no history of balances yet), so a
    past date is approximate. The difference against opening balances shows as opening capital."""
    ctx = shop_ctx(db, actor)
    d = as_of or _today(ctx)
    start = _start(db, ctx)
    opening_cash = _q(db, "SELECT opening_cash FROM shops WHERE id = :s", s=ctx.id).scalar() or ZERO
    cash = opening_cash + _money_sum(db, ctx, start, d, "method = 'cash'")
    bank_rows = banks(db, actor)
    no_bank = _money_sum(db, ctx, start, d, "method IN ('upi','card','bank','cheque')") - sum(
        (b["book_balance"] - b["opening_balance"] for b in bank_rows), ZERO
    )
    bal = balances(db, ctx)
    fa = assets(db, actor, d)
    fixed = fa["totals"]["closing"]
    loans = _q(
        db,
        "SELECT coalesce(sum(b.principal - coalesce((SELECT sum(p.amount) FROM payments p WHERE p.applies_to_type = 'borrowing'"
        " AND p.applies_to_id = b.id AND p.direction = 'out' AND p.status = 'confirmed'), 0)), 0)"
        " FROM borrowings b WHERE b.shop_id = :s AND b.deleted_at IS NULL",
        s=ctx.id,
    ).scalar()
    gst_ret = "applies_to_id IN (SELECT id FROM filings WHERE return_type IN ('GSTR3B','CMP08','GSTR4','GSTR9'))"
    gst_paid = -_money_sum(db, ctx, start, d, f"applies_to_type = 'tax' AND {gst_ret}")
    capital_in = _money_sum(db, ctx, start, d, "applies_to_type = 'capital'")
    # A proprietor's income tax is personal, so it counts as drawings.
    drawings = -_money_sum(
        db,
        ctx,
        start,
        d,
        f"(applies_to_type = 'drawing' OR (applies_to_type = 'tax' AND NOT {gst_ret}))",
    )
    m = compute(db, ctx, start, d)
    dep_total = _dep_since(db, ctx, start, d)
    # Composition tax comes out of the shop's pocket (it can't be collected), so it's a cost.
    comp_tax = gst_paid if ctx.scheme == "composition" else ZERO
    profit = m.net_profit - dep_total - comp_tax
    gst = (
        ZERO
        if ctx.scheme == "composition"
        else m.output_tax - _itc_since(db, ctx, start, d) - gst_paid
    )

    asset_lines = [("Cash in hand", cash)]
    asset_lines += [(f"Bank: {b['name']}", b["book_balance"]) for b in bank_rows]
    if not bank_rows:
        asset_lines.append(("Bank / UPI (no account set)", no_bank))
    asset_lines += [
        ("Receivables (customers)", bal["receivables"]),
        ("Closing stock", bal["stock_value"]),
        ("Fixed assets (after depreciation)", fixed),
    ]
    liab_lines = [
        ("Payables (suppliers)", bal["payables"]),
        ("Loans", loans),
        ("GST payable (estimate)", gst),
    ]
    total_assets = sum((v for _, v in asset_lines), ZERO)
    total_liab = sum((v for _, v in liab_lines), ZERO)
    opening_capital = total_assets - total_liab - capital_in + drawings - profit
    capital_lines = [
        ("Opening capital (balancing figure)", opening_capital),
        ("Capital introduced", capital_in),
        ("Profit since books start", profit),
        ("Less: drawings", -drawings),
    ]
    trial = [
        *[(n, v, ZERO) for n, v in asset_lines],
        *[(n, ZERO, v) for n, v in liab_lines],
        ("Opening capital", ZERO, opening_capital),
        ("Capital introduced", ZERO, capital_in),
        ("Drawings", drawings, ZERO),
        ("Sales (net of returns, ex-GST)", ZERO, m.net_revenue),
        ("Cost of goods sold", m.cogs, ZERO),
        ("Expenses", m.expenses, ZERO),
        ("Wages", m.labour, ZERO),
        ("Depreciation", dep_total, ZERO),
        ("Composition tax", comp_tax, ZERO),
    ]
    # Negative balances sit on the other side, as in any trial balance.
    tb = [
        {
            "account": n,
            "debit": dr - cr if dr - cr > 0 else ZERO,
            "credit": cr - dr if cr - dr > 0 else ZERO,
        }
        for n, dr, cr in trial
        if dr or cr
    ]
    return {
        "as_of": d,
        "books_start": start,
        "assets": [{"name": n, "amount": v} for n, v in asset_lines],
        "liabilities": [{"name": n, "amount": v} for n, v in liab_lines],
        "capital": [{"name": n, "amount": v} for n, v in capital_lines],
        "total_assets": total_assets,
        "total_liabilities_capital": total_liab + sum((v for _, v in capital_lines), ZERO),
        "trial_balance": tb,
        "trial_totals": {
            "debit": sum((r["debit"] for r in tb), ZERO),
            "credit": sum((r["credit"] for r in tb), ZERO),
        },
        "note": "Prepared from what was entered in Anylo. Opening capital is the balancing figure; check it with your CA.",
    }


def _dep_since(db: Session, ctx: ShopCtx, start: date, end: date) -> Decimal:
    total = ZERO
    for r in _q(
        db,
        "SELECT cost, block, bought_on, sold_on, sale_value FROM fixed_assets WHERE shop_id = :s AND deleted_at IS NULL"
        " AND bought_on <= :d",
        s=ctx.id,
        d=end,
    ):
        y = max(fy_start(start), fy_start(r.bought_on))
        while y <= end:
            sold = r.sold_on if r.sold_on and r.sold_on <= end else None
            dep = depreciation(r.cost, BLOCK_RATE[r.block], r.bought_on, sold, r.sale_value, y)
            total += dep["depreciation"]
            if dep["closing"] == ZERO:
                total -= dep["sale_gain"]  # a profit on sale lowers the charge, a loss adds to it
                break
            y = date(y.year + 1, 4, 1)
    return total


def _itc_since(db: Session, ctx: ShopCtx, start: date, end: date) -> Decimal:
    r = _q(
        db,
        "SELECT (SELECT coalesce(sum(igst_total + cgst_total + sgst_total + cess_total), 0) FROM purchases"
        "   WHERE shop_id = :s AND status = 'posted' AND itc_eligible"
        "   AND coalesce(supplier_invoice_date, (posted_at AT TIME ZONE :tz)::date) BETWEEN :a AND :b)"
        " + (SELECT coalesce(sum(gst_amount), 0) FROM expenses WHERE shop_id = :s AND deleted_at IS NULL AND itc_eligible"
        "   AND occurred_on BETWEEN :a AND :b)",
        s=ctx.id,
        tz=str(ctx.tz),
        a=start,
        b=end,
    ).scalar()
    assert isinstance(r, Decimal)
    return r
