"""Safety guards shared by every legacy-source adapter."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Delete, Insert, Update
from sqlalchemy.engine import make_url
from sqlalchemy.sql.ddl import DDLElement


class _DryRunResult:
    """Minimal empty SQLAlchemy result returned for suppressed writes."""

    def scalar_one_or_none(self) -> None:
        return None

    def scalar(self) -> None:
        return None

    def scalars(self) -> _DryRunResult:
        return self

    def mappings(self) -> _DryRunResult:
        return self

    def first(self) -> None:
        return None

    def all(self) -> list[Any]:
        return []


class DryRunSession:
    """Read-through target session that suppresses every ORM/SQL mutation."""

    def __init__(self, session: Any) -> None:
        self._session = session
        self.suppressed_writes = 0

    def __getattr__(self, name: str) -> Any:
        return getattr(self._session, name)

    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        if isinstance(statement, (Insert, Update, Delete, DDLElement)):
            self.suppressed_writes += 1
            return _DryRunResult()
        sql = str(statement).lstrip().split(None, 1)[0].upper() if str(statement).strip() else ""
        if sql not in {"SELECT", "SHOW", "SET", "WITH"}:
            self.suppressed_writes += 1
            return _DryRunResult()
        return await self._session.execute(statement, *args, **kwargs)

    def add(self, instance: Any, _warn: bool = True) -> None:
        del instance, _warn
        self.suppressed_writes += 1

    def add_all(self, instances: Any) -> None:
        self.suppressed_writes += len(list(instances))

    async def delete(self, instance: Any) -> None:
        del instance
        self.suppressed_writes += 1

    async def flush(self, objects: Any = None) -> None:
        del objects

    async def commit(self) -> None:
        return None


def database_identity(dsn: str) -> tuple[str, int, str]:
    """Return a credential-free identity suitable for source/target guards."""

    url = make_url(dsn)
    host = str(url.host or "localhost").strip().lower()
    if host in {"localhost", "127.0.0.1", "::1"}:
        host = "localhost"
    return host, int(url.port or 5432), str(url.database or "").strip()


def ensure_distinct_databases(source_dsn: str, target_dsn: str) -> None:
    if database_identity(source_dsn) == database_identity(target_dsn):
        raise ValueError("Source and target DSNs resolve to the same PostgreSQL database")
