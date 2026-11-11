from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator

from app.deps import DB, CurrentActor, require
from app.services.finance import export, gst_returns, reports
from app.services.sales import _today, shop_ctx

router = APIRouter(prefix="/v1", tags=["finance"])
VIEW = [Depends(require("report.view"))]
GST = [Depends(require("report.gst"))]
From = Annotated[date | None, Query(alias="from")]
Metric = Literal[
    "sales",
    "gross_profit",
    "net_profit",
    "invoices_count",
    "avg_bill_value",
    "new_customers",
    "collections",
]
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class GoalIn(BaseModel):
    metric: Metric
    title: str | None = Field(default=None, max_length=80)
    period_start: date
    period_end: date
    target: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    user_id: UUID | None = None

    @model_validator(mode="after")
    def _range(self) -> "GoalIn":
        if self.period_end < self.period_start:
            raise ValueError("The end date is before the start date.")
        return self


def _range(
    db: DB, actor: CurrentActor, frm: date | None, to: date | None, default: str = "month"
) -> tuple[date, date]:
    today = _today(shop_ctx(db, actor))
    end = to or today
    return frm or (today if default == "day" else end.replace(day=1)), end


@router.get("/dashboard", dependencies=VIEW)
def dashboard(actor: CurrentActor, db: DB, frm: From = None, to: date | None = None) -> Any:
    return reports.dashboard(db, actor, *_range(db, actor, frm, to, "day"))


@router.get("/reports/pnl", dependencies=VIEW)
def pnl(actor: CurrentActor, db: DB, frm: From = None, to: date | None = None) -> Any:
    return reports.pnl(db, actor, *_range(db, actor, frm, to))


@router.get("/reports/cash-flow", dependencies=VIEW)
def cash_flow(actor: CurrentActor, db: DB, frm: From = None, to: date | None = None) -> Any:
    return reports.cash_flow(db, actor, *_range(db, actor, frm, to))


@router.get("/reports/receivables", dependencies=VIEW)
def receivables(actor: CurrentActor, db: DB) -> Any:
    return reports.receivables(db, actor)


@router.get("/reports/payables", dependencies=VIEW)
def payables(actor: CurrentActor, db: DB) -> Any:
    return reports.payables(db, actor)


@router.get("/reports/gst/gstr1", dependencies=GST)
def gstr1(period: str, actor: CurrentActor, db: DB) -> Any:
    return gst_returns.gstr1(db, actor, period)


@router.get("/reports/gst/gstr3b", dependencies=GST)
def gstr3b(period: str, actor: CurrentActor, db: DB) -> Any:
    return gst_returns.gstr3b(db, actor, period)


@router.get("/reports/gst/cmp08", dependencies=GST)
def cmp08(actor: CurrentActor, db: DB, frm: From = None, to: date | None = None) -> Any:
    return gst_returns.cmp08(db, actor, *_range(db, actor, frm, to))


@router.get("/reports/export", dependencies=VIEW)
def export_xlsx(
    actor: CurrentActor,
    db: DB,
    kind: Literal["full", "gstr1"] = "full",
    frm: From = None,
    to: date | None = None,
    period: str | None = None,
) -> Response:
    if kind == "gstr1":
        require("report.gst")(actor)
        p = period or f"{_today(shop_ctx(db, actor)):%Y-%m}"
        data, name = export.gstr1(db, actor, p), f"anylo-gstr1-{p}.xlsx"
    else:
        a, b = _range(db, actor, frm, to)
        data, name = export.business(db, actor, a, b), f"anylo-business-{a}-to-{b}.xlsx"
    return Response(
        data, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{name}"'}
    )


@router.get("/goals", dependencies=[Depends(require("goal.view"))])
def list_goals(actor: CurrentActor, db: DB) -> Any:
    return reports.list_goals(db, actor)


@router.get("/goals/suggest", dependencies=[Depends(require("goal.manage"))])
def suggest(metric: Metric, start: date, end: date, actor: CurrentActor, db: DB) -> Any:
    return reports.suggest_goal(db, actor, metric, start, end)


@router.post("/goals", status_code=201, dependencies=[Depends(require("goal.manage"))])
def create_goal(data: GoalIn, actor: CurrentActor, db: DB) -> Any:
    return reports.create_goal(db, actor, data)


@router.delete("/goals/{goal_id}", status_code=204, dependencies=[Depends(require("goal.manage"))])
def delete_goal(goal_id: UUID, actor: CurrentActor, db: DB) -> None:
    reports.delete_goal(db, actor, goal_id)
