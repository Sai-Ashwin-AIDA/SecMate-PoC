import json

import httpx
import pytest
from secmate_worker.model_profiles import OPENROUTER_NEMOTRON_EVALUATOR, OPENROUTER_NEMOTRON_TARGET
from secmate_worker.target_profiles import SOCMATE_PROFILE
from secmate_worker.model_clients import ModelClientSettings
from test_model_adapters import Reply, completion, configured_clients


def test_active_judge_and_target_are_only_nemotron_35_super_vl():
    assert OPENROUTER_NEMOTRON_EVALUATOR.model == OPENROUTER_NEMOTRON_TARGET.model == "nvidia/nemotron-3.5-super-vl:free"
    assert OPENROUTER_NEMOTRON_EVALUATOR.profile_id == "openrouter-nemotron-35-super-vl-judge"
    assert SOCMATE_PROFILE.model == OPENROUTER_NEMOTRON_TARGET.model
    assert SOCMATE_PROFILE.model_profile_id == OPENROUTER_NEMOTRON_TARGET.profile_id


@pytest.mark.asyncio
async def test_nemotron_35_uses_strict_schema_without_an_extra_request():
    payloads = []
    async def handler(request):
        payloads.append(json.loads(request.content))
        return httpx.Response(200, json=completion('{"status":"READY"}'))
    clients = configured_clients(ModelClientSettings("", "fake", openrouter_allow_data_collection=True), transport=httpx.MockTransport(handler))
    try:
        result = await clients.openrouter_structured(OPENROUTER_NEMOTRON_EVALUATOR.model, "Synthetic check", Reply)
        assert result.output.status == "READY"
        assert len(payloads) == 1
        assert payloads[0]["response_format"]["type"] == "json_schema"
        assert payloads[0]["response_format"]["json_schema"]["schema"]["additionalProperties"] is False
        assert payloads[0]["model"] == "nvidia/nemotron-3.5-super-vl:free"
    finally:
        await clients.close()
