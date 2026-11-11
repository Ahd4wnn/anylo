"""Permission → roles map. Generated from docs/03-roles-permissions.md; every route declares one."""

O, M, S, A, SU = "owner", "manager", "salesperson", "admin", "support"
AC = "accountant"  # the shop's CA: reads everything money-related, changes nothing
SHOP_STAFF = frozenset({O, M, S})
SHOP_ADMINS = frozenset({O, M})

PERMISSIONS: dict[str, frozenset[str]] = {
    # sales
    "invoice.create": SHOP_STAFF,
    "invoice.view": SHOP_STAFF | {A, SU, AC},
    "invoice.edit": SHOP_ADMINS,
    "invoice.cancel": SHOP_ADMINS,
    "credit_note.create": SHOP_STAFF,  # salesperson → approval request
    "payment.collect": SHOP_STAFF,  # salesperson → pending approval
    "approval.decide": SHOP_ADMINS,
    "held_bill.manage": SHOP_STAFF,
    # catalogue & stock
    "product.view": SHOP_STAFF | {A, SU, AC},
    "product.manage": SHOP_ADMINS,
    "product.snap": SHOP_STAFF,
    "stock.manage": SHOP_ADMINS,
    "purchase.manage": SHOP_ADMINS,
    # people & money
    "customer.view": SHOP_STAFF | {AC},
    "customer.ledger": SHOP_ADMINS | {AC},
    "customer.manage": SHOP_ADMINS,
    "customer.export": SHOP_ADMINS,
    "expense.create": SHOP_STAFF,
    "expense.view": SHOP_STAFF | {AC},
    "expense.manage": SHOP_ADMINS,
    "labour.attendance": SHOP_STAFF,
    "labour.manage": SHOP_ADMINS,
    "borrowing.manage": SHOP_ADMINS,
    "cash.view_today": SHOP_STAFF,
    "cash.close": SHOP_STAFF,  # salesperson → manager confirms
    "cash.book": SHOP_ADMINS | {AC},
    "books.view": SHOP_ADMINS | {AC},  # read-only: purchases, wages, loans
    # insight
    "report.view": SHOP_ADMINS | {AC},
    "report.gst": SHOP_ADMINS | {AC},
    "goal.manage": SHOP_ADMINS,
    "goal.view": SHOP_STAFF | {AC},
    "ai.use": frozenset({O}),  # owner-exclusive
    # shop
    "shop.view": SHOP_STAFF | {A, SU, AC},
    "shop.settings": SHOP_ADMINS,
    "shop.tax_profile": frozenset({O}),
    "shop.payment_details": frozenset({O}),  # UPI ID: owner only (fraud fix)
    "staff.salespeople": SHOP_ADMINS,
    "staff.managers": frozenset({O}),  # also invites / revokes the accountant
    "subscription.view": SHOP_ADMINS | {A, SU},
    "subscription.pay": frozenset({O}),
    "shop.delete": frozenset({O, A}),
    # platform
    "platform.shops": frozenset({A, SU}),
    "platform.customers": frozenset({A}),
    "platform.config": frozenset({A}),
    "platform.ledger": frozenset({A}),
    "platform.ledger_view": frozenset({A, SU}),
}


def allowed(permission: str, role: str) -> bool:
    return role in PERMISSIONS[permission]
