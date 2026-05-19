from __future__ import annotations

from sqlalchemy.orm import Session

from core.db.connect import ENGINE_PG
from moduly.mereni.kalorimetry.database.models import Mereni_kalorimetry
from moduly.mereni.kalorimetry.database.outlier_review_apply import apply_outlier_review_update
from moduly.mereni.kalorimetry.database.outlier_reviews import list_outlier_reviews
from services.api.services.dashboard_admin import require_admin_access
from services.api.services.dashboard_auth import DashboardUserContext


class KalorimetryAdminOperationError(ValueError):
    """Raised when a kalorimetry admin operation is invalid."""


def list_devices_admin(
    user_context: DashboardUserContext,
    *,
    limit: int = 5000,
) -> list[str]:
    require_admin_access(user_context)
    resolved_limit = max(1, min(int(limit), 5000))
    with Session(ENGINE_PG, autoflush=False, expire_on_commit=False) as session:
        rows = (
            session.query(Mereni_kalorimetry.identifikace)
            .filter(Mereni_kalorimetry.identifikace.is_not(None))
            .filter(Mereni_kalorimetry.platne.is_(True))
            .distinct()
            .order_by(Mereni_kalorimetry.identifikace)
            .limit(resolved_limit)
            .all()
        )
        return [str(row[0]) for row in rows if row[0]]


def list_outlier_reviews_admin(
    user_context: DashboardUserContext,
    *,
    review_status: str | None = None,
    identifikace: str | None = None,
    source_filter: str = "VSE",
    limit: int = 200,
) -> list[dict[str, object]]:
    require_admin_access(user_context)
    try:
        return list_outlier_reviews(
            review_status=review_status,
            identifikace=identifikace,
            source_filter=source_filter,
            limit=limit,
        )
    except ValueError as exc:
        raise KalorimetryAdminOperationError(str(exc)) from exc


def update_outlier_review_admin(
    user_context: DashboardUserContext,
    *,
    review_id: int,
    review_status: str,
    review_note: str | None = None,
) -> dict[str, object]:
    require_admin_access(user_context)
    try:
        return apply_outlier_review_update(
            review_id,
            review_status=review_status,
            review_note=review_note,
            actor=user_context.username,
        )
    except ValueError as exc:
        raise KalorimetryAdminOperationError(str(exc)) from exc
