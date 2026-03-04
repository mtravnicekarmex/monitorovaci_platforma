from decouple import config
from sqlalchemy import URL, create_engine
from sqlalchemy.orm import sessionmaker


def build_pg_url() -> str:
    return (
        f"postgresql://{config('USER')}:{config('PASSWORD')}@"
        f"{config('HOST')}:{config('PGPORT')}/{config('PGDATABASE')}"
    )


def build_ms_url() -> URL:
    return URL.create(
        "mssql+pyodbc",
        username=config("USER"),
        password=config("PASSWORD"),
        host=config("HOST"),
        port=config("MSPORT"),
        database=config("MSDATABASE"),
        query={
            "driver": "ODBC Driver 18 for SQL Server",
            "Encrypt": "no",
        },
    )


ENGINE_PG = create_engine(
    build_pg_url(),
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    pool_recycle=1800,
    connect_args={"options": "-c timezone=UTC"},
)

ENGINE_MS = create_engine(
    build_ms_url(),
    echo=False,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_recycle=1800,
)

SessionLocalPG = sessionmaker(
    bind=ENGINE_PG,
    autocommit=False,
    autoflush=False,
)

SessionLocalMS = sessionmaker(
    bind=ENGINE_MS,
    autocommit=False,
    autoflush=False,
)


def get_session_pg():
    return SessionLocalPG()


def get_session_ms():
    return SessionLocalMS()
