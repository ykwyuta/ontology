"""TypeDB への接続とスキーマの適用。"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

from typedb.driver import Credentials, Driver, DriverOptions, DriverTlsConfig, TransactionType, TypeDB

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schema"

ADDRESS = os.environ.get("TYPEDB_ADDRESS", "127.0.0.1:1729")
USERNAME = os.environ.get("TYPEDB_USERNAME", "admin")
PASSWORD = os.environ.get("TYPEDB_PASSWORD", "password")
DATABASE = os.environ.get("TYPEDB_DATABASE", "legal")


@contextmanager
def connect() -> Driver:
    driver = TypeDB.driver(ADDRESS, Credentials(USERNAME, PASSWORD),
                           DriverOptions(DriverTlsConfig.disabled()))
    try:
        yield driver
    finally:
        driver.close()


def schema_text() -> str:
    """schema/*.tql を 1 つの define にまとめる（ファイルをまたいで相互に参照するため）。"""
    parts = []
    for f in sorted(SCHEMA_DIR.glob("*.tql")):
        body = f.read_text(encoding="utf-8")
        parts.append(body.replace("\ndefine\n", "\n", 1) if "\ndefine\n" in body else body)
    return "define\n" + "\n".join(parts)


def init_database(driver: Driver, database: str = DATABASE, *, recreate: bool = False) -> None:
    if driver.databases.contains(database):
        if not recreate:
            raise RuntimeError(f"database {database!r} already exists (use recreate=True)")
        driver.databases.get(database).delete()
    driver.databases.create(database)
    with driver.transaction(database, TransactionType.SCHEMA) as tx:
        tx.query(schema_text()).resolve()
        tx.commit()


def rows(driver: Driver, query: str, database: str = DATABASE) -> list:
    with driver.transaction(database, TransactionType.READ) as tx:
        ans = tx.query(query).resolve()
        if ans.is_concept_documents():
            return list(ans.as_concept_documents())
        return list(ans.as_concept_rows())
