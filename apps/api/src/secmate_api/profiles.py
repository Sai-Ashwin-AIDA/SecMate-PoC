from .contracts import ModelProfile


MODEL_PROFILES = [
    ModelProfile(
        id="groq-qwen-attacker",
        role="ATTACKER",
        provider="GROQ",
        name="Qwen 3.8 Attack Planner",
        model="qwen/qwen3.8-27b",
        description="Use this profile to generate assessment tests.",
        capabilities=["structured_output", "reasoning"],
    ),
    ModelProfile(
        id="groq-qwen-critic",
        role="ATTACK_CRITIC",
        provider="GROQ",
        name="Qwen 3.8 Attack Critic",
        model="qwen/qwen3.8-27b",
        description="Use this profile to review test quality and choose the next method.",
        capabilities=["structured_output", "reasoning"],
    ),
    ModelProfile(
        id="openrouter-nemotron-35-super-vl-judge",
        role="OUTCOME_JUDGE",
        provider="OPENROUTER",
        name="Nemotron 3.5 Super VL Judge",
        model="nvidia/nemotron-3.5-super-vl:free",
        description="Use this profile to review captured evidence.",
        capabilities=["structured_output"],
    ),
    ModelProfile(
        id="openrouter-nemotron-35-super-vl-target",
        role="TARGET",
        provider="OPENROUTER",
        name="Nemotron 3.5 Super VL Target",
        model="nvidia/nemotron-3.5-super-vl:free",
        description="Use this profile when testing tool-use controls.",
        capabilities=["tool_calling", "text"],
    ),
]


MODEL_PROFILES_BY_ID = {profile.id: profile for profile in MODEL_PROFILES}
# Compatibility URLs resolve to the current model, never a retired route.
MODEL_PROFILES_BY_ID.update({
    "openrouter-nemotron-judge": MODEL_PROFILES_BY_ID["openrouter-nemotron-35-super-vl-judge"],
    "openrouter-nemotron-target": MODEL_PROFILES_BY_ID["openrouter-nemotron-35-super-vl-target"],
})
