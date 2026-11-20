"""Explicit app-local configuration loading; no environment access on import."""

import os
import re
from pathlib import Path
from typing import Mapping

from dotenv import dotenv_values
from pydantic import Field, SecretStr, ValidationError, model_validator

from .contracts import StrictModel

MODEL = "nvidia/nemotron-3.5-super-vl:free"
BASE_URL = "https://openrouter.ai/api/v1"


class ConfigurationError(ValueError):
    """Safe configuration error, without rejected values or secrets."""


class Configuration(StrictModel):
    input_dir: Path
    output_dir: Path
    api_key: SecretStr = Field(default_factory=lambda: SecretStr(""), repr=False, exclude=True)
    model: str = MODEL
    base_url: str = BASE_URL
    allow_transmission: bool = False
    request_timeout_seconds: int = Field(default=30, ge=5, le=60)
    turn_timeout_seconds: int = Field(default=120, ge=15, le=180)
    max_model_calls_per_turn: int = Field(default=8, ge=1, le=12)
    max_tool_calls_per_turn: int = Field(default=12, ge=1, le=20)
    max_output_tokens: int = Field(default=2048, ge=256, le=4096)
    context_budget_units: int = Field(default=32768, ge=8192, le=65536)
    max_turn_token_budget: int = Field(default=80000, ge=8192, le=160000)
    max_history_turns: int = Field(default=4, ge=0, le=8)

    @model_validator(mode="after")
    def validate_route_and_time(self) -> "Configuration":
        if self.model != MODEL or self.base_url != BASE_URL:
            raise ValueError("Only the configured blueprint route is supported.")
        if self.turn_timeout_seconds < self.request_timeout_seconds:
            raise ValueError("Turn timeout must cover the request timeout.")
        return self

    def require_inference_ready(self) -> None:
        """Future Slice 2 gate; never constructs a provider client."""
        if not self.api_key.get_secret_value().strip():
            raise ConfigurationError("OPENROUTER_API_KEY is required for inference.")
        if not self.allow_transmission:
            raise ConfigurationError("Document transmission consent is required for inference.")


def reject_tracing(environment: Mapping[str, str]) -> None:
    for name in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2", "LANGCHAIN_TRACING"):
        if environment.get(name, "").casefold() not in ("", "false", "0"):
            raise ConfigurationError("Tracing must be disabled.")


def load_configuration(
    app_root: Path, *, environment: Mapping[str, str] | None = None
) -> Configuration:
    """Read exactly app_root/.env, then overlay process settings without mutation.

    Offline configuration permits a missing key and false transmission consent.
    FilesystemRoots performs the separate root-access validation.
    """
    root = app_root.resolve(strict=True)
    # No find_dotenv(), interpolation, parent search, or load_dotenv side effects.
    values = {
        key: value for key, value in dotenv_values(root / ".env", interpolate=False).items()
        if value is not None
    }
    values.update(dict(os.environ if environment is None else environment))
    reject_tracing(values)

    def directory(name: str, default: str) -> Path:
        value = values.get(name, default)
        if not value.strip():
            raise ConfigurationError(f"{name} must not be blank.")
        path = Path(value)
        return path if path.is_absolute() else root / path

    def integer(name: str, default: int) -> int:
        value = values.get(name, str(default))
        if re.fullmatch(r"[0-9]+", value) is None:
            raise ConfigurationError(f"{name} must be an integer.")
        return int(value)

    consent = values.get("ALLOW_OPENROUTER_DOCUMENT_TRANSMISSION", "false")
    if consent not in ("true", "false"):
        raise ConfigurationError("Transmission consent must be exactly true or false.")
    try:
        return Configuration(
            input_dir=directory("DOCUMENT_INPUT_DIR", "./data/input"),
            output_dir=directory("DOCUMENT_OUTPUT_DIR", "./data/output"),
            api_key=SecretStr(values.get("OPENROUTER_API_KEY", "")),
            model=values.get("OPENROUTER_MODEL", MODEL),
            base_url=values.get("OPENROUTER_BASE_URL", BASE_URL),
            allow_transmission=consent == "true",
            **{
                name: integer(name.upper(), field.default)
                for name, field in Configuration.model_fields.items()
                if name in {
                    "request_timeout_seconds", "turn_timeout_seconds",
                    "max_model_calls_per_turn", "max_tool_calls_per_turn",
                    "max_output_tokens", "context_budget_units",
                    "max_turn_token_budget", "max_history_turns",
                }
            },
        )
    except ValidationError:
        raise ConfigurationError("Invalid route, timeout, or numeric configuration bounds.") from None
