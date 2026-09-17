from enum import Enum
import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator  # type: ignore[import-not-found]


logger = logging.getLogger("redteam_models")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] [Models]: %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)



class SeverityLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    NONE = "NONE"

    @classmethod
    def from_string(cls, value: str) -> "SeverityLevel":
        try:
            cleaned = value.strip().upper() if isinstance(value, str) else "NONE"
            return cls(cleaned)
        except ValueError:
            logger.warning(f"Unrecognized severity level '{value}'. Falling back to SeverityLevel.MEDIUM")
            return cls.MEDIUM


class AttackVector(BaseModel):
    id: str = Field(..., description="Unique vector ID, e.g., VEC-ROLE-001")
    name: str = Field(..., description="Human-readable vector name")
    category: str = Field(..., description="OWASP/MITRE category")
    severity: SeverityLevel = Field(default=SeverityLevel.MEDIUM)
    description: str = Field(..., description="Operational objective of the vector")
    recipe: str = Field(..., description="Prompt-framing instructions for the attacker")

    @field_validator("severity", mode="before")
    @classmethod
    def validate_severity(cls, v: Any) -> SeverityLevel:
        if isinstance(v, SeverityLevel):
            return v
        return SeverityLevel.from_string(str(v))


class AttackLibrary(BaseModel):
    version: str = Field(default="1.0")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    attack_vectors: List[AttackVector] = Field(default_factory=list)

    @field_validator("attack_vectors", mode="before")
    @classmethod
    def validate_vectors(cls, v: Any) -> List[Any]:
        if not isinstance(v, list):
            logger.error(f"Expected list for 'attack_vectors', got {type(v).__name__}. Resetting to empty list.")
            return []
        return v



class ToolParameter(BaseModel):
    name: str
    type: str = "string"
    description: str = ""
    required: bool = True

    @field_validator("name", mode="before")
    @classmethod
    def clean_name(cls, v: str) -> str:
        return v.strip().replace(" ", "_") if isinstance(v, str) else str(v)


class ToolDefinition(BaseModel):
    name: str
    description: str = ""
    parameters: List[ToolParameter] = Field(default_factory=list)

    def to_openai_tool(self) -> Dict[str, Any]:
    
        try:
            properties = {}
            required_params = []

            for p in self.parameters:
                properties[p.name] = {
                    "type": p.type,
                    "description": p.description
                }
                if p.required:
                    required_params.append(p.name)

            return {
                "type": "function",
                "function": {
                    "name": self.name.strip().replace(" ", "_"),
                    "description": self.description,
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required_params
                    }
                }
            }
        except Exception as e:
            logger.error(f"Failed to serialize tool '{self.name}' to function schema: {e}", exc_info=True)
            return {
                "type": "function",
                "function": {
                    "name": self.name,
                    "description": self.description,
                    "parameters": {"type": "object", "properties": {}}
                }
            }


class TargetAgentProfile(BaseModel):
    name: str = Field(..., description="Target system identifier")
    description: str = Field(default="", description="Role and context of the target")
    system_prompt: str = Field(default="", description="Primary system directive")
    guardrails: List[str] = Field(default_factory=list, description="Explicit boundaries to enforce")
    tools: List[ToolDefinition] = Field(default_factory=list, description="Available executable tools")

    @field_validator("guardrails", mode="before")
    @classmethod
    def ensure_guardrails_list(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            return [v.strip()]
        if isinstance(v, list):
            return [str(item).strip() for item in v if item]
        return []



class EvaluationVerdict(BaseModel):
    violation_detected: bool = Field(default=False)
    severity: SeverityLevel = Field(default=SeverityLevel.NONE)
    evidence_quote: Optional[str] = Field(
        default=None,
        description="Exact quote from target text or tool arguments indicating violation"
    )
    reasoning: str = Field(default="No reasoning provided by evaluator.")
    evaluation_failed: bool = Field(default=False, description="True when the judge could not produce a reliable verdict")
    status: str = Field(default="completed", description="completed, policy_override, or evaluation_failed")

    @field_validator("severity", mode="before")
    @classmethod
    def validate_eval_severity(cls, v: Any) -> SeverityLevel:
        if isinstance(v, SeverityLevel):
            return v
        return SeverityLevel.from_string(str(v))


class TurnTrace(BaseModel):
    turn_number: int = Field(..., ge=1)
    probe: str = Field(..., description="Prompt sent by the red team agent")
    probe_source: str = Field(default="llm", description="llm or template_fallback")
    target_response: str = Field(default="", description="Text response from the target agent")
    tool_calls_attempted: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Intercepted tool executions with parameters"
    )
    tool_policy_findings: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Deterministic policy findings for intercepted tool calls"
    )
    verdict: EvaluationVerdict


class AuditReport(BaseModel):
    test_id: str
    target_agent_name: str
    vector_tested: AttackVector
    turns_executed: int = Field(default=0, ge=0)
    breached: bool = Field(default=False)
    breach_turn: Optional[int] = Field(default=None)
    traces: List[TurnTrace] = Field(default_factory=list)

    def log_summary(self) -> None:
        status = "BREACHED" if self.breached else "DEFENDED"
        logger.info(
            f"Audit Test '{self.test_id}' for Target '{self.target_agent_name}' | "
            f"Vector: {self.vector_tested.id} ({self.vector_tested.name}) | "
            f"Result: {status} | Turns: {self.turns_executed}"
        )
