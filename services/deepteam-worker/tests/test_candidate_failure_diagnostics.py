"""The two-call baseline must retain safe, stage-specific failures."""
import json
import pytest
from pydantic import PydanticInvalidForJsonSchema
from secmate_worker import chatmate_candidates as module
from secmate_worker.model_clients import ModelClientSettings, ModelRequestError, ModelErrorCode
from secmate_worker.contracts import ProviderName
from secmate_worker.execution_budget import BudgetExceededError, BudgetErrorCode
from test_chatmate_candidates import FakeDeepTeamModel, generator


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,category,code", [
    ("preparation", "ADAPTER_RUNTIME", "GENERATION_CHECK_ERROR"),
    ("schema", "SCHEMA_PREPARATION", "GENERATION_CHECK_ERROR"),
    ("malformed", "VERDICT_VALIDATION", "GENERATION_CHECK_ERROR"),
    ("network", "PROVIDER", "NETWORK_ERROR"),
    ("authentication", "PROVIDER", "AUTHENTICATION"),
    ("budget", "BUDGET", "BUDGET_EXHAUSTED"),
])
async def test_failed_generation_is_bounded_safe_and_never_publishes(monkeypatch, kind, category, code):
    closed = []
    secret = "synthetic-private-output-do-not-persist"
    class Clients:
        def __init__(self, *args, **kwargs):
            pass
        async def close(self):
            closed.append(True)
    class Model(FakeDeepTeamModel):
        async def a_generate(self, prompt, schema=None):
            if kind == "preparation":
                raise AttributeError(secret)
            if kind == "schema":
                raise PydanticInvalidForJsonSchema(secret)
            if kind == "malformed":
                return {"private": secret}
            if kind == "budget":
                raise BudgetExceededError(BudgetErrorCode.TOKEN_BUDGET_EXHAUSTED, secret)
            raise ModelRequestError(secret, provider=ProviderName.GROQ,
                code=ModelErrorCode.NETWORK_ERROR if kind == "network" else ModelErrorCode.AUTHENTICATION, retryable=False)
    original = module.ChatMateCandidateGenerator
    monkeypatch.setattr(module, "StructuredModelClients", Clients)
    monkeypatch.setattr(module, "ChatMateCandidateGenerator", lambda simulator: original(Model()))
    with pytest.raises(module.ChatMateCandidateGenerationError) as caught:
        await module.ChatMateCandidateGenerationRunner(ModelClientSettings("fake", "")).generate("prompt-probing-v1")
    payload = caught.value.failure_payload
    assert payload["error"]["code"] == code
    assert payload["error"]["category"] == category
    assert payload["error"]["stage"] == "PROMPT_GENERATION"
    assert payload["candidate_checks"] == []
    assert payload["budget"]["provider_calls_attempted"] == 0
    assert "batch" not in payload and secret not in json.dumps(payload)
    assert closed == [True]


@pytest.mark.asyncio
async def test_initialization_failure_remains_safe_without_source_provenance(monkeypatch):
    def fail(*args, **kwargs):
        raise TypeError("synthetic-private-detail")
    monkeypatch.setattr(module, "StructuredModelClients", fail)
    monkeypatch.setattr(module, "_worker_source_hash", lambda: None)
    with pytest.raises(module.ChatMateCandidateGenerationError) as caught:
        await module.ChatMateCandidateGenerationRunner(ModelClientSettings("fake", "")).generate("prompt-injection-v1")
    payload = caught.value.failure_payload
    assert payload["error"]["stage"] == "INITIALIZATION"
    assert payload["error"]["worker_source_sha256"] is None
    assert "synthetic-private" not in json.dumps(payload)
