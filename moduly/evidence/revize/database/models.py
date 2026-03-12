from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import Integer, String, Date, Text, Index, UniqueConstraint, ForeignKey, Numeric
from core.db.connect import ENGINE_PG



class Base(DeclarativeBase):
    pass



class Revize(Base):
    __tablename__ = "revize"
    __table_args__ = (UniqueConstraint("budova", "datum", "soubor", name="uq_revize_budova_datum_soubor"),
                Index("idx_revize_platnost", "datum_platnosti"),
                Index("idx_revize_budova", "budova"),
        {"schema": "revize"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True) # Primární klíč
    budova: Mapped[str] = mapped_column(String(50), nullable=False)  # Budova / objekt, ze kterého soubor pochází
    datum: Mapped[Date] = mapped_column(Date, nullable=False)  # Datum provedení revize
    delka_platnosti: Mapped[float] = mapped_column(Numeric(4, 2), nullable=False) # Délka platnosti v rocích
    datum_platnosti: Mapped[Date] = mapped_column(Date, nullable=True) # Datum platnosti (datum + délka platnosti)
    typ_zarizeni: Mapped[str | None] = mapped_column(String(100), nullable=True) # Typ zařízení, kterého se revize týká
    nazev_revize: Mapped[str | None] = mapped_column(String(255), nullable=True) # Název revize odvozený z Excelu
    dodavatel: Mapped[str | None] = mapped_column(String(200), nullable=True) # Dodavatel revize
    servisni_smlouva: Mapped[str | None] = mapped_column(String(500), nullable=True) # Odkaz na smlouvu, pokud existuje
    soubor: Mapped[str | None] = mapped_column(String(500), nullable=True) # Odkaz na soubor revize
    poznamka: Mapped[str | None] = mapped_column(Text, nullable=True) # Poznámka (volitelná)

    # Relationship
    revize_zarizeni: Mapped[list["Revize_zarizeni"]] = relationship("Revize_zarizeni", back_populates="revize")

    def __repr__(self) -> str:
        return f"{self.id} - {self.budova} - {self.datum} - {self.delka_platnosti} - {self.dodavatel}"





class Revize_zarizeni(Base):
    __tablename__ = "revize_zarizeni"
    __table_args__ = (UniqueConstraint("revize_id", "typ_zarizeni", "zarizeni_id", name="uq_revize_zarizeni_revize_typ_id",),
            Index("idx_revize_zarizeni_typ_id", "typ_zarizeni", "zarizeni_id"),
        {"schema": "revize"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    revize_id: Mapped[int] = mapped_column(Integer, ForeignKey("revize.revize.id"), nullable=False)
    typ_zarizeni: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    zarizeni_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)

 # Relationship
    revize: Mapped["Revize"] = relationship("Revize", back_populates="revize_zarizeni")

    def __repr__(self) -> str:
        return f"{self.id} - {self.revize_id} - {self.typ_zarizeni} - {self.zarizeni_id}"


# Revize.__table__.create(bind=ENGINE_PG, checkfirst=True)