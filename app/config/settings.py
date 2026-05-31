import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    home_assistant_url: str | None
    home_assistant_token: str | None
    ecoflow_battery_power_sign: str = "unknown"

    def require_home_assistant(self) -> "Settings":
        missing: list[str] = []
        if not self.home_assistant_url:
            missing.append("HOME_ASSISTANT_URL")
        if not self.home_assistant_token:
            missing.append("HOME_ASSISTANT_TOKEN")
        if missing:
            joined = ", ".join(missing)
            raise RuntimeError(f"Missing required Home Assistant configuration: {joined}")
        return self


def get_settings() -> Settings:
    return Settings(
        home_assistant_url=os.getenv("HOME_ASSISTANT_URL"),
        home_assistant_token=os.getenv("HOME_ASSISTANT_TOKEN"),
        ecoflow_battery_power_sign=os.getenv("ECOFLOW_BATTERY_POWER_SIGN", "unknown"),
    )
