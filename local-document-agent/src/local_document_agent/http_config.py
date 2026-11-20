"""Explicit app-local adapter overlay. Production roots cannot be overridden."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from dotenv import dotenv_values
from pydantic import SecretStr

from .config import Configuration, ConfigurationError, load_configuration
from .contracts import DocumentError
from .filesystem import FilesystemRoots
from .http_contracts import Limits, Readiness, SafeError


@dataclass(frozen=True)
class AdapterSettings:
    configuration: Configuration
    token: SecretStr = field(repr=False)

    def require_token(self) -> None:
        token = self.token.get_secret_value()
        if not token or not token.isascii() or any(ord(c) <= 32 or ord(c) >= 127 for c in token):
            raise ConfigurationError("A nonblank ASCII adapter bearer token without whitespace is required.")
        if token == self.configuration.api_key.get_secret_value():
            raise ConfigurationError("The adapter bearer token must differ from the provider key.")

    def roots(self) -> FilesystemRoots:
        return FilesystemRoots(self.configuration.input_dir, self.configuration.output_dir)

    def readiness(self) -> Readiness:
        from .config import reject_tracing

        reasons = []
        try:
            self.configuration.require_inference_ready()
        except ConfigurationError:
            reasons.append(SafeError(
                code="INFERENCE_NOT_READY",
                message="Supply app-local provider settings and explicit transmission consent privately.",
            ))
        try:
            reject_tracing(os.environ)
        except ConfigurationError:
            reasons.append(SafeError(code="TRACING_ENABLED", message="Tracing must be disabled."))
        try:
            self.roots()
        except (DocumentError, OSError, ValueError):
            reasons.append(SafeError(
                code="ROOTS_NOT_READY",
                message="Require existing separate local directories: data/input/mock-workspace and data/output. "
                        "Ask permission before creating/copying the tracked examples; never merge existing data.",
            ))
        return Readiness(ready=not reasons, reasons=tuple(reasons))

    def limits(self) -> Limits:
        names = (
            "request_timeout_seconds", "turn_timeout_seconds", "max_model_calls_per_turn",
            "max_tool_calls_per_turn", "max_output_tokens", "context_budget_units",
            "max_turn_token_budget", "max_history_turns",
        )
        return Limits(**{name: getattr(self.configuration, name) for name in names})


def load_adapter_settings(
    app_root: Path, *, environment: Mapping[str, str] | None = None,
) -> AdapterSettings:
    """No parent search, no mutation, no secret printing, no directory creation."""
    root = app_root.resolve(strict=True)
    values = {
        key: value for key, value in dotenv_values(root / ".env", interpolate=False).items()
        if value is not None
    }
    values.update(dict(os.environ if environment is None else environment))
    # Reuse all existing parsing and validation, overriding only CLI root settings.
    values["DOCUMENT_INPUT_DIR"] = str(root / "data/input/mock-workspace")
    values["DOCUMENT_OUTPUT_DIR"] = str(root / "data/output")
    configuration = load_configuration(root, environment=values)
    settings = AdapterSettings(
        configuration, SecretStr(values.get("LOCAL_DOCUMENT_AGENT_ADAPTER_TOKEN", "")),
    )
    settings.require_token()
    return settings
