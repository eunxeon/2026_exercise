import os
from pathlib import Path


TRUTHY = {"1", "true", "yes", "on"}


class DatabaseUnavailable(Exception):
    """Raised when MSSQL is not configured or cannot be reached."""


def load_env_file(path=None):
    env_path = Path(path or Path(__file__).with_name(".env"))
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path)
        return
    except ImportError:
        pass

    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _env(primary_name, fallback_name, default=""):
    value = os.getenv(primary_name)
    if value not in (None, ""):
        return value
    return os.getenv(fallback_name, default)


class MSSQLDatabase:
    """Small pyodbc wrapper for the smart mirror prototype APIs."""

    def __init__(self):
        load_env_file()
        self.enabled = _env("DB_ENABLED", "MSSQL_ENABLED", "0").lower() in TRUTHY
        self.driver = _env(
            "DB_DRIVER", "MSSQL_DRIVER", "ODBC Driver 18 for SQL Server"
        )
        self.server = _env("DB_SERVER", "MSSQL_SERVER", "")
        self.port = _env("DB_PORT", "MSSQL_PORT", "")
        self.database = _env("DB_NAME", "MSSQL_DATABASE", "")
        self.username = _env("DB_USERNAME", "MSSQL_USERNAME", "")
        self.password = _env("DB_PASSWORD", "MSSQL_PASSWORD", "")
        self.trusted_connection = (
            _env("DB_TRUSTED_CONNECTION", "MSSQL_TRUSTED_CONNECTION", "0").lower()
            in TRUTHY
        )
        self.trust_server_certificate = (
            _env(
                "DB_TRUST_SERVER_CERTIFICATE",
                "MSSQL_TRUST_SERVER_CERTIFICATE",
                "1",
            ).lower()
            in TRUTHY
        )
        self.timeout = int(
            _env("DB_CONNECTION_TIMEOUT", "MSSQL_CONNECTION_TIMEOUT", "3")
        )

    def is_configured(self):
        if not self.enabled:
            return False
        if not self.server or not self.database:
            return False
        if self.trusted_connection:
            return True
        return bool(self.username and self.password)

    def _connection_string(self):
        server = self.server
        if self.port:
            server = f"{server},{self.port}"

        parts = [
            f"DRIVER={{{self.driver}}}",
            f"SERVER={server}",
            f"DATABASE={self.database}",
            f"TrustServerCertificate={'yes' if self.trust_server_certificate else 'no'}",
        ]

        if self.trusted_connection:
            parts.append("Trusted_Connection=yes")
        else:
            parts.extend([f"UID={self.username}", f"PWD={self.password}"])

        return ";".join(parts)

    def connect(self):
        if not self.is_configured():
            raise DatabaseUnavailable("MSSQL is not enabled or configured")

        try:
            import pyodbc
        except ImportError as exc:
            raise DatabaseUnavailable("pyodbc is not installed") from exc

        try:
            return pyodbc.connect(self._connection_string(), timeout=self.timeout)
        except Exception as exc:
            raise DatabaseUnavailable(str(exc)) from exc

    def query_one(self, sql, params=None):
        rows = self.query_all(sql, params)
        return rows[0] if rows else None

    def query_all(self, sql, params=None):
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, *(params or []))
            columns = [column[0] for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def execute(self, sql, params=None):
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, *(params or []))
            conn.commit()
            return cursor.rowcount

    def execute_returning_one(self, sql, params=None):
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, *(params or []))
            columns = [column[0] for column in cursor.description]
            row = cursor.fetchone()
            conn.commit()
            return dict(zip(columns, row)) if row else None
