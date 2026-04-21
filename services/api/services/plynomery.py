from __future__ import annotations

from core.db.connect import get_session_pg
from moduly.mereni.plynomery.database.models import Mereni_plynomery
from services.api.services.dashboard_auth import DashboardUserContext, require_section_access


def list_accessible_devices(
    user_context: DashboardUserContext,
    *,
    limit: int = 500,
) -> list[str]:
    require_section_access(user_context, "plynomery")

    session = get_session_pg()
    try:
        query = session.query(Mereni_plynomery.identifikace).distinct()
        if not user_context.is_admin:
            query = query.filter(Mereni_plynomery.identifikace.in_(user_context.allowed_devices))

        rows = query.order_by(Mereni_plynomery.identifikace).limit(limit).all()
        return [str(row[0]) for row in rows if row[0]]
    finally:
        session.close()
