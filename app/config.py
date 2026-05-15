from enum import Enum
from pydantic_settings import BaseSettings, SettingsConfigDict


class ExecutionMode(str, Enum):
    SHADOW = "SHADOW"
    LIVE = "LIVE"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    EXECUTION_MODE: ExecutionMode = ExecutionMode.SHADOW

    # PostgreSQL — system of record
    DATABASE_URL: str = "postgresql+asyncpg://ssip:ssip@localhost:5432/ssip"

    # SQL Server — read-only student source
    MSSQL_HOST: str = ""
    MSSQL_PORT: str = "1433"
    MSSQL_USER: str = ""
    MSSQL_PASS: str = ""
    MSSQL_DATABASE: str = ""

    # GHL — currently READ ONLY / SHADOW MODE
    GHL_API_KEY: str = ""
    GHL_BASE_URL: str = "https://rest.gohighlevel.com"
    GHL_LOCATION_ID: str = ""
    GHL_TIMEOUT_SECONDS: int = 30
    GHL_RETRY_MAX: int = 3
    # Custom field mappings (GHL internal field IDs)
    GHL_FIELD_MESSAGE: str = ""
    GHL_TASK_TITLE: str = ""
    GHL_TASK_DESCRIPTION: str = ""
    GHL_TASK_DUE_DATE: str = ""
    GHL_FIELD_VM_EMAIL_HTML: str = ""
    GHL_FIELD_VM_EMAIL_SUBJECT: str = ""

    # Synthflow
    SYNTHFLOW_API_KEY: str = ""
    SYNTHFLOW_PHONE_NUMBER: str = ""

    # LLM
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o"

    # Scheduler
    SCHEDULER_HOUR: int = 18
    SCHEDULER_MINUTE: int = 0
    SCHEDULER_TIMEZONE: str = "America/Chicago"

    # Retry
    MAX_ATTEMPTS: int = 3
    RETRY_INTERVAL_HOURS: int = 24

    @property
    def mssql_dsn(self) -> str:
        return (
            f"DRIVER={{ODBC Driver 18 for SQL Server}};"
            f"SERVER={self.MSSQL_HOST},{self.MSSQL_PORT};"
            f"DATABASE={self.MSSQL_DATABASE};"
            f"UID={self.MSSQL_USER};"
            f"PWD={self.MSSQL_PASS};"
            f"TrustServerCertificate=yes;"
            f"Encrypt=yes;"
        )

    @property
    def mssql_configured(self) -> bool:
        return bool(self.MSSQL_HOST and self.MSSQL_USER and self.MSSQL_DATABASE)

    @property
    def is_shadow(self) -> bool:
        return self.EXECUTION_MODE == ExecutionMode.SHADOW


settings = Settings()
