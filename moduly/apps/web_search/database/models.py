from datetime import datetime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, ForeignKey, Text, Float, Boolean, BigInteger, Integer, Numeric, DateTime, func, Index, \
    UniqueConstraint, text, CheckConstraint
from geoalchemy2 import Geometry
from typing import List



class Base(DeclarativeBase):
    pass

# hledané výrazy prohledávání webu na PG
class Monitor(Base):
    __tablename__ = "monitors"
    __table_args__ = {'schema': 'web_search'}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, nullable=False)
    url: Mapped[str] = mapped_column(String(550), nullable=False)
    vyrazy: Mapped[str] = mapped_column(Text, nullable=False)  # uložíme JSON string
    email: Mapped[str] = mapped_column(String(250), nullable=False)
    last_run: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=True)
    created: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=datetime.now)

    # Relationships

    results: Mapped[List["Result"]] = relationship(back_populates="monitor", cascade="all, delete-orphan", passive_deletes=True)




# výsledky prohledání webu na PG
class Result(Base):
    __tablename__ = "results"
    __table_args__ = {'schema': 'web_search'}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, nullable=False)
    monitor_id: Mapped[int] = mapped_column(ForeignKey("web_search.monitors.id", ondelete="CASCADE"), nullable=False)
    url: Mapped[str] = mapped_column(String(550), nullable=False)
    vyraz: Mapped[str] = mapped_column(String(550), nullable=False)
    snippet: Mapped[str] = mapped_column(Text, nullable=True)
    odkaz: Mapped[str] = mapped_column(String(550), nullable=True)
    datum: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    notified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Relationships

    monitor: Mapped["Monitor"] = relationship("Monitor", back_populates="results")



