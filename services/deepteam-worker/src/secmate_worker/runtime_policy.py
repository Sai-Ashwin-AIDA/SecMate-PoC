import json
import os
import sys
from collections.abc import Mapping, MutableMapping
from importlib.metadata import PackageNotFoundError, distribution, version


REQUIRED_PYTHON = (3, 11)
DEEPTEAM_COMMIT = "2fd3445c5bb2070ce09834f66f1622eb914f6f46"
DEEPEVAL_VERSION = "3.6.2"
REQUIRED_ENVIRONMENT = {
    "DEEPTEAM_TELEMETRY_OPT_OUT": "YES",
    "DEEPEVAL_TELEMETRY_OPT_OUT": "1",
    "DEEPTEAM_SHOW_PROGRESS": "false",
    "TELEMETRY_OPT_OUT": "YES",
    "ERROR_REPORTING": "NO",
}
FORBIDDEN_ENVIRONMENT = ("CONFIDENT_API_KEY",)


class RuntimePolicyError(RuntimeError):
    pass


def validate_installed_frameworks() -> str:
    try:
        deepteam_distribution = distribution("deepteam")
        installed_deepeval = version("deepeval")
    except PackageNotFoundError as error:
        raise RuntimePolicyError("Pinned DeepTeam runtime is not installed.") from error
    if installed_deepeval != DEEPEVAL_VERSION:
        raise RuntimePolicyError(
            "Installed DeepEval version does not match the reviewed worker pin."
        )
    direct_url = deepteam_distribution.read_text("direct_url.json")
    if not direct_url:
        raise RuntimePolicyError("DeepTeam installation provenance is unavailable.")
    try:
        commit = json.loads(direct_url)["vcs_info"]["commit_id"]
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise RuntimePolicyError("DeepTeam installation provenance is invalid.") from error
    if commit != DEEPTEAM_COMMIT:
        raise RuntimePolicyError(
            "Installed DeepTeam commit does not match the reviewed worker pin."
        )
    return commit


def configure_runtime_environment(
    environment: MutableMapping[str, str] | None = None,
) -> None:
    target = environment if environment is not None else os.environ
    imported_frameworks = {
        name.split(".", 1)[0]
        for name in sys.modules
        if name.split(".", 1)[0] in {"deepteam", "deepeval"}
    }
    policy_is_active = all(
        target.get(name) == expected
        for name, expected in REQUIRED_ENVIRONMENT.items()
    ) and not any(target.get(name) for name in FORBIDDEN_ENVIRONMENT)
    if environment is None and imported_frameworks and not policy_is_active:
        names = ", ".join(sorted(imported_frameworks))
        raise RuntimePolicyError(
            f"Runtime policy must be configured before importing: {names}."
        )
    for name in FORBIDDEN_ENVIRONMENT:
        if target.get(name):
            raise RuntimePolicyError(f"{name} must not be available to the worker.")
    target.update(REQUIRED_ENVIRONMENT)


def validate_runtime(
    environment: Mapping[str, str] | None = None,
    version_info: tuple[int, int] | None = None,
) -> None:
    current_version = version_info or (sys.version_info.major, sys.version_info.minor)
    if current_version != REQUIRED_PYTHON:
        raise RuntimePolicyError(
            "SecMate DeepTeam worker requires Python 3.11; "
            f"received {current_version[0]}.{current_version[1]}."
        )

    source = environment if environment is not None else os.environ
    for name, expected in REQUIRED_ENVIRONMENT.items():
        if source.get(name) != expected:
            raise RuntimePolicyError(f"{name} must be set to {expected!r}.")
    for name in FORBIDDEN_ENVIRONMENT:
        if source.get(name):
            raise RuntimePolicyError(f"{name} must not be available to the worker.")
