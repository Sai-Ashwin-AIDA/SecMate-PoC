from dataclasses import dataclass, field
from functools import lru_cache
import os
from pathlib import Path

from dotenv import load_dotenv


API_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(API_ROOT / ".env")
DATA_ROOT = Path(os.getenv("SECMATE_API_DATA_ROOT", API_ROOT / "data")).resolve()


@dataclass(frozen=True)
class Settings:
    groq_api_key: str = field(repr=False)
    openrouter_api_key: str = field(repr=False)
    request_timeout_seconds: float
    groq_critic_api_key: str = field(default="", repr=False)

    @property
    def groq_critic_configured(self) -> bool:
        return bool(self.groq_critic_api_key)

    @property
    def groq_configured(self) -> bool:
        return bool(self.groq_api_key)

    @property
    def openrouter_configured(self) -> bool:
        return bool(self.openrouter_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings(
        groq_api_key=os.getenv("GROQ_API_KEY", "").strip(),
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY", "").strip(),
        groq_critic_api_key=os.getenv("GROQ_CRITIC_API_KEY", "").strip(),
        request_timeout_seconds=float(
            os.getenv("SECMATE_REQUEST_TIMEOUT_SECONDS", "90")
        ),
    )
