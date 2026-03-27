from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Streamlit_Users(Base):
    __tablename__ = "Streamlit_Users"
    __table_args__ = {"schema": "dashboard"}

    uzivatel: Mapped[str] = mapped_column(String(100), primary_key=True, nullable=False, unique=True)
    email: Mapped[str | None] = mapped_column(String(250), nullable=True)
    heslo: Mapped[str] = mapped_column(String(255), nullable=False)  # uklada hash hesla
    dostupne_sekce: Mapped[str | None] = mapped_column(Text, nullable=True)
    dostupne_stranky: Mapped[str | None] = mapped_column(Text, nullable=True)
    seznam_zarizeni: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON list identifikaci
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, server_default=func.now(), onupdate=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    @staticmethod
    def _load_json_list(value: str | None) -> list[str] | None:
        if value is None:
            return None
        if not value:
            return []
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, list):
            return []
        return [str(item) for item in parsed]

    def get_dostupne_sekce(self) -> list[str] | None:
        return self._load_json_list(self.dostupne_sekce)

    def set_dostupne_sekce(self, sekce: list[str] | None) -> None:
        self.dostupne_sekce = None if sekce is None else json.dumps(sekce, ensure_ascii=True)

    def get_dostupne_stranky(self) -> list[str] | None:
        return self._load_json_list(self.dostupne_stranky)

    def set_dostupne_stranky(self, stranky: list[str] | None) -> None:
        self.dostupne_stranky = None if stranky is None else json.dumps(stranky, ensure_ascii=True)

    def get_seznam_zarizeni(self) -> list[str]:
        return self._load_json_list(self.seznam_zarizeni) or []

    def set_seznam_zarizeni(self, zarizeni: list[str]) -> None:
        self.seznam_zarizeni = json.dumps(zarizeni, ensure_ascii=True)
