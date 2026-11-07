from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, UploadFile

from app.database import privileged_session
from app.deps import DB, CurrentActor, require
from app.errors import AppError
from app.schemas.shop import (
    NewShopIn,
    OnboardingOut,
    ShopOut,
    ShopPatch,
    StaffCreated,
    StaffIn,
    StaffOut,
    StaffPatch,
    TaxProfileIn,
)
from app.services import shop as svc

router = APIRouter(prefix="/v1", tags=["shop"])


@router.get("/shop", response_model=ShopOut, dependencies=[Depends(require("shop.view"))])
def get_shop(actor: CurrentActor, db: DB) -> Any:
    return svc.get_shop(db, actor)


@router.patch("/shop", response_model=ShopOut, dependencies=[Depends(require("shop.settings"))])
def patch_shop(data: ShopPatch, actor: CurrentActor, db: DB) -> Any:
    svc.update_shop(db, actor, data)
    return svc.get_shop(db, actor)


@router.put(
    "/shop/tax-profile", response_model=ShopOut, dependencies=[Depends(require("shop.tax_profile"))]
)
def put_tax_profile(data: TaxProfileIn, actor: CurrentActor, db: DB) -> Any:
    svc.put_tax_profile(db, actor, data)
    return svc.get_shop(db, actor)


@router.post("/shop/logo", dependencies=[Depends(require("shop.settings"))])
async def upload_logo(file: UploadFile, actor: CurrentActor, db: DB) -> dict[str, str | None]:
    data = await file.read(5 * 1024 * 1024 + 1)
    return {"logo_url": svc.set_logo(db, actor, data)}


@router.delete("/shop/logo", status_code=204, dependencies=[Depends(require("shop.settings"))])
def delete_logo(actor: CurrentActor, db: DB) -> None:
    svc.set_logo(db, actor, None)


@router.get(
    "/shop/onboarding",
    response_model=OnboardingOut,
    dependencies=[Depends(require("shop.settings"))],
)
def onboarding(actor: CurrentActor, db: DB) -> Any:
    return svc.onboarding(db, actor)


@router.post(
    "/shop/onboarding/complete", status_code=204, dependencies=[Depends(require("shop.settings"))]
)
def complete_onboarding(actor: CurrentActor, db: DB) -> None:
    svc.complete_onboarding(db, actor)


@router.post("/shops", status_code=201, dependencies=[Depends(require("subscription.pay"))])
def create_shop(data: NewShopIn, actor: CurrentActor) -> dict[str, UUID]:
    if actor.role != "owner":
        raise AppError("auth.forbidden", "Only owners can add shops.", 403)
    with privileged_session() as db:  # privileged: the new shop has no link to the owner yet
        sid = svc.create_shop(db, actor.user_id, data)  # type: ignore[arg-type]
    return {"id": sid}


# --- staff ---


@router.get(
    "/shop/staff",
    response_model=list[StaffOut],
    dependencies=[Depends(require("staff.salespeople"))],
)
def list_staff(actor: CurrentActor, db: DB) -> Any:
    return svc.list_staff(db, actor)


@router.post(
    "/shop/staff",
    response_model=StaffCreated,
    status_code=201,
    dependencies=[Depends(require("staff.salespeople"))],
)
def create_staff(data: StaffIn, actor: CurrentActor, db: DB) -> Any:
    u, password = svc.create_staff(db, actor, data)
    return {**u._asdict(), "temporary_password": password}


@router.patch(
    "/shop/staff/{user_id}",
    response_model=StaffOut,
    dependencies=[Depends(require("staff.salespeople"))],
)
def update_staff(user_id: UUID, data: StaffPatch, actor: CurrentActor, db: DB) -> Any:
    return svc.update_staff(db, actor, user_id, data)


@router.post(
    "/shop/staff/{user_id}/reset-password",
    response_model=StaffCreated,
    dependencies=[Depends(require("staff.salespeople"))],
)
def reset_staff_password(user_id: UUID, actor: CurrentActor, db: DB) -> Any:
    u, password = svc.reset_staff_password(db, actor, user_id)
    return {**u._asdict(), "temporary_password": password}
