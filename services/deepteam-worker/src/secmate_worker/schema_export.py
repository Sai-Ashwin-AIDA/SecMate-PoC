import argparse
import json
from pathlib import Path
from typing import Any

from .contracts import (
    CONTRACT_SCHEMA_VERSION,
    AssessmentSpec,
    AttackCriticReview,
    AttackPath,
    Campaign,
    ChatMateCandidateBatch,
    EvidenceBundle,
    ManualChatMateEvaluationInput,
    PathReviewResult,
    RunManifest,
    TargetEvaluation,
)
from .critic_contracts import ManualChatMateCriticInput, ManualChatMateCriticOutput, ChatMateCriticReview, ChatMateCriticFailure, FollowUpContext


EXPORTED_CONTRACTS = {
    "ManualChatMateCriticInput": ManualChatMateCriticInput,
    "ManualChatMateCriticOutput": ManualChatMateCriticOutput,
    "ChatMateCriticReview": ChatMateCriticReview,
    "ChatMateCriticFailure": ChatMateCriticFailure,
    "FollowUpContext": FollowUpContext,
    "AssessmentSpec": AssessmentSpec,
    "Campaign": Campaign,
    "ChatMateCandidateBatch": ChatMateCandidateBatch,
    "AttackPath": AttackPath,
    "TargetEvaluation": TargetEvaluation,
    "AttackCriticReview": AttackCriticReview,
    "PathReviewResult": PathReviewResult,
    "EvidenceBundle": EvidenceBundle,
    "ManualChatMateEvaluationInput": ManualChatMateEvaluationInput,
    "RunManifest": RunManifest,
}


def schema_bundle() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": (
            "https://secmate.internal/schemas/deepteam-worker/"
            f"v{CONTRACT_SCHEMA_VERSION}/bundle.json"
        ),
        "title": "SecMate DeepTeam Worker Contracts",
        "version": CONTRACT_SCHEMA_VERSION,
        "contracts": {
            name: contract.model_json_schema(mode="validation")
            for name, contract in EXPORTED_CONTRACTS.items()
        },
    }


def write_schema_bundle(destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(schema_bundle(), indent=2, sort_keys=True) + "\n",
        encoding="ascii",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Export versioned worker JSON Schemas.")
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    write_schema_bundle(args.destination)
    print(f"Exported SecMate worker schemas to {args.destination}")


if __name__ == "__main__":
    main()
