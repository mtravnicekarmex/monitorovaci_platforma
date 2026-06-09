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


class Dashboard_MapLayer(Base):
    __tablename__ = "Map_Layers"
    __table_args__ = {"schema": "dashboard"}

    layer_id: Mapped[str] = mapped_column(String(100), primary_key=True, nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(250), nullable=False)
    layer_kind: Mapped[str] = mapped_column(String(50), nullable=False, default="context", server_default="context")
    source_schema: Mapped[str] = mapped_column(String(100), nullable=False)
    source_table: Mapped[str] = mapped_column(String(250), nullable=False)
    geometry_column: Mapped[str] = mapped_column(String(100), nullable=False, default="geom", server_default="geom")
    identifier_column: Mapped[str] = mapped_column(String(100), nullable=False)
    source_srid: Mapped[int] = mapped_column(Integer, nullable=False, default=3857, server_default="3857")
    target_srid: Mapped[int] = mapped_column(Integer, nullable=False, default=4326, server_default="4326")
    property_columns: Mapped[str] = mapped_column(Text, nullable=False, default="[]", server_default="[]")
    property_aliases: Mapped[str] = mapped_column(Text, nullable=False, default="{}", server_default="{}")
    filter_columns: Mapped[str] = mapped_column(Text, nullable=False, default="[]", server_default="[]")
    popup_columns: Mapped[str] = mapped_column(Text, nullable=False, default="[]", server_default="[]")
    style: Mapped[str] = mapped_column(Text, nullable=False, default="{}", server_default="{}")
    device_section_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    restrict_to_allowed_devices: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    map_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    default_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    show_photo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    draw_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100, server_default="100")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, server_default=func.now(), onupdate=func.now())

    @staticmethod
    def _load_json_list(value: str | None) -> list[str]:
        if not value:
            return []
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, list):
            return []
        return [str(item) for item in parsed]

    @staticmethod
    def _load_json_dict(value: str | None) -> dict[str, object]:
        if not value:
            return {}
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if not isinstance(parsed, dict):
            return {}
        return {str(key): item for key, item in parsed.items()}

    def get_property_columns(self) -> list[str]:
        return self._load_json_list(self.property_columns)

    def set_property_columns(self, columns: list[str]) -> None:
        self.property_columns = json.dumps(columns, ensure_ascii=True)

    def get_property_aliases(self) -> dict[str, object]:
        return self._load_json_dict(self.property_aliases)

    def set_property_aliases(self, aliases: dict[str, object]) -> None:
        self.property_aliases = json.dumps(aliases, ensure_ascii=True)

    def get_filter_columns(self) -> list[str]:
        return self._load_json_list(self.filter_columns)

    def set_filter_columns(self, columns: list[str]) -> None:
        self.filter_columns = json.dumps(columns, ensure_ascii=True)

    def get_popup_columns(self) -> list[str]:
        return self._load_json_list(self.popup_columns)

    def set_popup_columns(self, columns: list[str]) -> None:
        self.popup_columns = json.dumps(columns, ensure_ascii=True)

    def get_style(self) -> dict[str, object]:
        return self._load_json_dict(self.style)

    def set_style(self, style: dict[str, object]) -> None:
        self.style = json.dumps(style, ensure_ascii=True)
