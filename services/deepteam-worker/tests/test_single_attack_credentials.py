import sys
from types import SimpleNamespace

import httpx
import pytest

from secmate_worker import single_attack
from secmate_worker.contracts import ModelRole
from secmate_worker.model_clients import ModelConfigurationError
from test_model_adapters import Reply, completion, configured_clients


@pytest.mark.parametrize("critic_key", ["synthetic-critic-key", ""])
def test_cli_propagates_dedicated_critic_key_without_attacker_fallback(monkeypatch, tmp_path, critic_key):
    observed = []

    async def handler(request):
        observed.append(request.headers["authorization"])
        return httpx.Response(200, json=completion('{"status":"ok"}'))

    class Runner:
        def __init__(self, settings):
            self.settings = settings

        async def run_single_attack(self, *args):
            clients = configured_clients(self.settings, transport=httpx.MockTransport(handler))
            try:
                await clients.groq_structured("synthetic", "test", Reply, role=ModelRole.ATTACK_CRITIC)
                await clients.groq_structured("synthetic", "test", Reply, role=ModelRole.ATTACKER)
            finally:
                await clients.close()
            return SimpleNamespace(final_status="RESISTED", summary=lambda: {})

        def persist(self, run, output):
            return tmp_path

    monkeypatch.setenv("GROQ_API_KEY", "synthetic-attacker-key")
    monkeypatch.setenv("GROQ_CRITIC_API_KEY", critic_key)
    monkeypatch.setattr(single_attack, "SecMateDeepTeamRunner", Runner)
    monkeypatch.setattr(sys, "argv", ["single_attack", "--allow-openrouter-data-collection", "--execution-mode", "ADAPTIVE", "--max-paths", "2"])
    if critic_key:
        single_attack.main()
        assert observed == ["Bearer synthetic-critic-key", "Bearer synthetic-attacker-key"]
    else:
        with pytest.raises(ModelConfigurationError):
            single_attack.main()
        assert observed == []
