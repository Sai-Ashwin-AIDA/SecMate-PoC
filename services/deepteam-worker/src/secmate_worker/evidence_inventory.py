"""Target-neutral evidence namespaces and citation selection; no verdict policy.

Stdlib-only so adapters/contracts can reuse this without a domain import cycle.
"""
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Citations:
    valid: tuple[str, ...]
    invalid: tuple[str, ...]


def select_citations(references: Iterable[str], allowed: Iterable[str]) -> Citations:
    references, allowed = set(references), set(allowed)
    if any(not isinstance(value, str) for value in references | allowed):
        raise ValueError("Citation identifiers must be strings")
    return Citations(tuple(sorted(references & allowed)), tuple(sorted(references - allowed)))


@dataclass(frozen=True)
class EvidenceInventory:
    turn_ids: frozenset[str]
    tool_ids: frozenset[str]
    retrieval_ids: frozenset[str]
    decision_ids: frozenset[str]
    manual_ids: frozenset[str]
    phase5_ids: frozenset[str]
    policy_ids: frozenset[str]

    @property
    def automatic_ids(self) -> frozenset[str]:
        # Preserve the general evaluator's existing four evidence classes.
        return self.turn_ids | self.tool_ids | self.retrieval_ids | self.decision_ids | self.phase5_ids

    @property
    def all_ids(self) -> frozenset[str]:
        return self.automatic_ids | self.manual_ids

    @classmethod
    def from_identifiers(cls, *, turn_ids=(), tool_ids=(), retrieval_ids=(), decision_ids=(), manual_ids=(), phase5_ids=(), policy_ids=()):
        groups = [tuple(group) for group in (turn_ids, tool_ids, retrieval_ids, decision_ids, manual_ids, phase5_ids, policy_ids)]
        if any(not isinstance(value, str) or not value.strip() for group in groups for value in group):
            raise ValueError("Evidence identifiers must be nonblank strings")
        evidence = [value for group in groups[:6] for value in group]
        if len(evidence) != len(set(evidence)):
            raise ValueError("Ambiguous duplicate evidence identifiers")
        if len(groups[6]) != len(set(groups[6])):
            raise ValueError("Duplicate policy identifiers")
        # Policies are a separate namespace; they never authorize evidence IDs.
        return cls(*(frozenset(group) for group in groups))

    @classmethod
    def from_turns(cls, turns, *, policy_ids=()):
        turns = tuple(turns)
        return cls.from_identifiers(
            turn_ids=(turn.turn_id for turn in turns),
            tool_ids=(item.evidence_id for turn in turns for item in turn.tool_attempts),
            retrieval_ids=(item.evidence_id for turn in turns for item in turn.retrieval_evidence),
            decision_ids=(item.evidence_id for turn in turns for item in turn.retrieval_decisions),
            manual_ids=(item.evidence_id for turn in turns for item in turn.manual_collection),
            policy_ids=policy_ids,
        )

    @classmethod
    def from_path(cls, path, *, policy_ids=()):
        if any(
            assessment.parent_path_id != path.path_id
            for assessment in path.phase5_assessments
        ):
            raise ValueError("Phase 5 evidence does not match its parent path")
        turn_ids = {turn.turn_id for turn in path.turns}
        if any(
            getattr(assessment, "parent_turn_id", None) is not None
            and assessment.parent_turn_id not in turn_ids
            for assessment in path.phase5_assessments
        ):
            raise ValueError("Phase 5 evidence does not match its parent turn")
        return cls.from_identifiers(
            turn_ids=turn_ids,
            tool_ids=(item.evidence_id for turn in path.turns for item in turn.tool_attempts),
            retrieval_ids=(item.evidence_id for turn in path.turns for item in turn.retrieval_evidence),
            decision_ids=(item.evidence_id for turn in path.turns for item in turn.retrieval_decisions),
            manual_ids=(item.evidence_id for turn in path.turns for item in turn.manual_collection),
            phase5_ids=(item.evidence_id for assessment in path.phase5_assessments for item in [assessment, *assessment.tools]),
            policy_ids=policy_ids,
        )
