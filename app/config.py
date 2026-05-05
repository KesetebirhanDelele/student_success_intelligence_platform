from enum import Enum
from typing import Optional
from pydantic_settings import BaseSettings


class SystemScope(str, Enum):
    MVP = "MVP"
    STANDARD = "STANDARD"
    PRODUCTION = "PRODUCTION"


class Settings(BaseSettings):
    SYSTEM_SCOPE: SystemScope = SystemScope.MVP

    DATABASE_URL: str = "sqlite:///./ssip.db"

    GHL_API_URL: str = "https://rest.gohighlevel.com/v1"
    GHL_API_KEY: str = ""
    GHL_LOCATION_ID: str = ""
    GHL_MOCK_MODE: bool = True

    SCHEDULER_ENABLED: bool = True
    SCHEDULER_HOUR: int = 18
    SCHEDULER_MINUTE: int = 0
    SCHEDULER_TIMEZONE: str = "America/Chicago"

    API_TOKEN: Optional[str] = None

    class Config:
        env_file = ".env"

    @property
    def max_attempts(self) -> int:
        return {"MVP": 1, "STANDARD": 2, "PRODUCTION": 3}[self.SYSTEM_SCOPE]

    @property
    def concurrency_limit(self) -> int:
        return {"MVP": 10, "STANDARD": 25, "PRODUCTION": 50}[self.SYSTEM_SCOPE]

    @property
    def exclusion_window_days(self) -> int:
        return 30

    @property
    def min_hw_threshold(self) -> int:
        return {"MVP": 2, "STANDARD": 2, "PRODUCTION": 1}[self.SYSTEM_SCOPE]

    @property
    def min_effort_threshold(self) -> float:
        return {"MVP": 3.0, "STANDARD": 2.8, "PRODUCTION": 2.5}[self.SYSTEM_SCOPE]

    @property
    def max_inactivity_days(self) -> int:
        return {"MVP": 7, "STANDARD": 6, "PRODUCTION": 5}[self.SYSTEM_SCOPE]

    @property
    def enable_retry(self) -> bool:
        return self.SYSTEM_SCOPE != SystemScope.MVP

    @property
    def enable_llm(self) -> bool:
        return self.SYSTEM_SCOPE == SystemScope.PRODUCTION

    @property
    def enable_escalation(self) -> bool:
        return self.SYSTEM_SCOPE != SystemScope.MVP

    @property
    def enable_channel_fallback(self) -> bool:
        return self.SYSTEM_SCOPE == SystemScope.PRODUCTION


settings = Settings()
