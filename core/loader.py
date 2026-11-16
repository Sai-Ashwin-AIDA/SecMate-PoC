import json
import logging
import os
from typing import Optional
import yaml  # type: ignore[reportMissingModuleSource]
from pydantic import ValidationError  # type: ignore[reportMissingImports]

from core.models import AttackLibrary, AuditReport, TargetAgentProfile

logger = logging.getLogger("redteam_loader")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] [Loader]: %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def load_attack_library(file_path: str = "attack_library.yaml") -> AttackLibrary:
    if not os.path.exists(file_path):
        logger.error(f"Attack library file not found at path: {file_path}")
        raise FileNotFoundError(f"Configuration file '{file_path}' does not exist.")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw_data = yaml.safe_load(f)

        if not raw_data:
            logger.warning(f"File '{file_path}' is empty. Returning empty AttackLibrary.")
            return AttackLibrary(version="1.0", attack_vectors=[])

        library = AttackLibrary.model_validate(raw_data)
        logger.info(f"Loaded {len(library.attack_vectors)} attack vectors from '{file_path}'.")
        return library

    except yaml.YAMLError as e:
        logger.error(f"Malformed YAML in '{file_path}': {e}", exc_info=True)
        raise ValueError(f"Could not parse YAML from '{file_path}': {e}") from e
    except ValidationError as e:
        logger.error(f"Schema validation failed for '{file_path}': {e}", exc_info=True)
        raise ValueError(f"Attack library validation error: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error loading '{file_path}': {e}", exc_info=True)
        raise


def load_target_profile(file_path: str) -> TargetAgentProfile:
    if not os.path.exists(file_path):
        logger.error(f"Target profile file not found at path: {file_path}")
        raise FileNotFoundError(f"Target profile '{file_path}' does not exist.")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw_data = yaml.safe_load(f)

        if not raw_data or not isinstance(raw_data, dict):
            logger.error(f"Target profile '{file_path}' must be a non-empty dictionary.")
            raise ValueError(f"Invalid target profile structure in '{file_path}'.")

        profile = TargetAgentProfile.model_validate(raw_data)
        logger.info(
            f"Successfully loaded TargetAgentProfile '{profile.name}' with "
            f"{len(profile.tools)} tools and {len(profile.guardrails)} guardrails."
        )
        return profile

    except yaml.YAMLError as e:
        logger.error(f"Malformed YAML in target profile '{file_path}': {e}", exc_info=True)
        raise ValueError(f"Could not parse YAML from '{file_path}': {e}") from e
    except ValidationError as e:
        logger.error(f"Schema validation failed for target profile '{file_path}': {e}", exc_info=True)
        raise ValueError(f"Target profile validation error: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error loading target profile '{file_path}': {e}", exc_info=True)
        raise


def save_audit_report(report: AuditReport, output_directory: str = "reports") -> Optional[str]:
    try:
        os.makedirs(output_directory, exist_ok=True)
        filename = f"audit_{report.target_agent_name.lower().replace(' ', '_')}_{report.test_id.lower()}.json"
        full_path = os.path.join(output_directory, filename)

        with open(full_path, "w", encoding="utf-8") as f:
            json.dump(report.model_dump(mode="json"), f, indent=2)

        logger.info(f"Audit report successfully exported to '{full_path}'.")
        return full_path

    except Exception as e:
        logger.error(f"Failed to export audit report for test '{report.test_id}': {e}", exc_info=True)
        return None