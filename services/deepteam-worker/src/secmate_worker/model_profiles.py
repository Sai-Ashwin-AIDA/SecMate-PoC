from dataclasses import dataclass

from .contracts import ModelRole, ProviderName


@dataclass(frozen=True)
class RuntimeModelProfile:
    profile_id: str
    role: ModelRole
    provider: ProviderName
    model: str


GROQ_QWEN_ATTACKER = RuntimeModelProfile(
    profile_id="groq-qwen-attacker",
    role=ModelRole.ATTACKER,
    provider=ProviderName.GROQ,
    model="qwen/qwen3.8-27b",
)
GROQ_QWEN_CRITIC = RuntimeModelProfile(
    profile_id="groq-qwen-critic",
    role=ModelRole.ATTACK_CRITIC,
    provider=ProviderName.GROQ,
    model="qwen/qwen3.8-27b",
)
OPENROUTER_NEMOTRON_EVALUATOR = RuntimeModelProfile(
    profile_id="openrouter-nemotron-35-super-vl-judge",
    role=ModelRole.TARGET_EVALUATOR,
    provider=ProviderName.OPENROUTER,
    model="nvidia/nemotron-3.5-super-vl:free",
)
GROQ_QWEN_NATIVE_EVALUATOR = RuntimeModelProfile(
    profile_id="groq-qwen-native-evaluator",
    role=ModelRole.DEEPTEAM_EVALUATOR,
    provider=ProviderName.GROQ,
    model="qwen/qwen3.8-27b",
)
OPENROUTER_NEMOTRON_TARGET = RuntimeModelProfile(
    profile_id="openrouter-nemotron-35-super-vl-target",
    role=ModelRole.TARGET,
    provider=ProviderName.OPENROUTER,
    model="nvidia/nemotron-3.5-super-vl:free",
)
LOCAL_SOCMATE_VULN_TARGET = RuntimeModelProfile(
    profile_id="local-socmate-vuln-target",
    role=ModelRole.TARGET,
    provider=ProviderName.LOCAL,
    model="deterministic-socmate-vuln-v1",
)

MODEL_PROFILES = (
    GROQ_QWEN_ATTACKER,
    GROQ_QWEN_CRITIC,
    GROQ_QWEN_NATIVE_EVALUATOR,
    OPENROUTER_NEMOTRON_EVALUATOR,
    OPENROUTER_NEMOTRON_TARGET,
    LOCAL_SOCMATE_VULN_TARGET,
)
