import sys
import tomllib
from pathlib import Path

import pytest

from secmate_worker.runtime_policy import (
    DEEPEVAL_VERSION,
    DEEPTEAM_COMMIT,
    REQUIRED_ENVIRONMENT,
    RuntimePolicyError,
    configure_runtime_environment,
    validate_installed_frameworks,
    validate_runtime,
)


def test_dependency_identity_is_fixed_to_reviewed_versions():
    assert DEEPTEAM_COMMIT == "2fd3445c5bb2070ce09834f66f1622eb914f6f46"
    assert DEEPEVAL_VERSION == "3.6.2"
    assert validate_installed_frameworks() == DEEPTEAM_COMMIT


def test_project_metadata_pins_runtime_and_framework_identity():
    project_file = Path(__file__).parents[1] / "pyproject.toml"
    project = tomllib.loads(project_file.read_text(encoding="ascii"))["project"]

    assert project["requires-python"] == ">=3.11,<3.12"
    assert project["dependencies"] == [
        "httpx==0.28.1",
        "pydantic==2.13.5",
        "python-dotenv==1.2.3",
    ]
    assert project["optional-dependencies"]["runtime"] == [
        "deepeval==3.6.2",
        (
            "deepteam @ git+https://github.com/Paramount-Assure/deepteam.git@"
            "2fd3445c5bb2070ce09834f66f1622eb914f6f46"
        ),
    ]
    assert project["optional-dependencies"]["test"] == [
        "pytest==9.1.1",
        "pytest-asyncio==1.4.0",
        "pytest-repeat==0.9.4",
    ]


def test_runtime_environment_is_configured_before_framework_imports():
    environment: dict[str, str] = {}

    configure_runtime_environment(environment)
    validate_runtime(environment, version_info=(3, 11))

    assert environment == REQUIRED_ENVIRONMENT


def test_confident_key_is_rejected_instead_of_silently_removed():
    environment = {"CONFIDENT_API_KEY": "must-not-be-present"}

    with pytest.raises(RuntimePolicyError, match="CONFIDENT_API_KEY"):
        configure_runtime_environment(environment)


def test_policy_configuration_fails_after_framework_import(monkeypatch):
    monkeypatch.setitem(sys.modules, "deepteam", object())
    for name in REQUIRED_ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(RuntimePolicyError, match="before importing: .*deepteam"):
        configure_runtime_environment()


def test_non_python_311_runtime_is_rejected():
    with pytest.raises(RuntimePolicyError, match="requires Python 3.11"):
        validate_runtime(REQUIRED_ENVIRONMENT, version_info=(3, 14))


def test_missing_telemetry_policy_is_rejected():
    environment = dict(REQUIRED_ENVIRONMENT)
    del environment["DEEPTEAM_TELEMETRY_OPT_OUT"]

    with pytest.raises(RuntimePolicyError, match="DEEPTEAM_TELEMETRY_OPT_OUT"):
        validate_runtime(environment, version_info=(3, 11))
