from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel

from .contracts import ModelRole
from .model_clients import ModelCallMetadata, StructuredModelClients
from .runtime_policy import configure_runtime_environment, validate_runtime


configure_runtime_environment()
validate_runtime()

from deepeval.models import DeepEvalBaseLLM  # noqa: E402


MetadataSink = Callable[[ModelCallMetadata], None]


class _SecMateDeepEvalModel(DeepEvalBaseLLM):
    def __init__(
        self,
        clients: StructuredModelClients,
        model_id: str,
        metadata_sink: MetadataSink | None = None,
        system_instruction: str | None = None,
        profile_id: str | None = None,
        role: ModelRole | None = None,
        structured_response_mode: Literal["AUTO", "TEXT_JSON"] = "AUTO",
    ):
        self.clients = clients
        self.model_id = model_id
        self.metadata_sink = metadata_sink
        self.system_instruction = system_instruction
        self.profile_id = profile_id
        self.role = role
        self.structured_response_mode = structured_response_mode
        super().__init__(model_name=model_id)

    def load_model(self) -> str:
        return self.model_id

    def get_model_name(self) -> str:
        raise NotImplementedError

    def generate(self, prompt: str, schema: type[BaseModel] | None = None) -> Any:
        raise RuntimeError(
            "Synchronous model generation is disabled; use a_generate with "
            "RedTeamer.a_red_team()."
        )

    def _record(self, metadata: ModelCallMetadata) -> None:
        if self.metadata_sink is not None:
            try:
                self.metadata_sink(metadata)
            except Exception:
                # Evidence sinks cannot turn a completed provider call into a retry.
                return


class GroqDeepEvalModel(_SecMateDeepEvalModel):
    def get_model_name(self) -> str:
        return f"groq/{self.model_id}"

    async def a_generate(
        self,
        prompt: str,
        schema: type[BaseModel] | None = None,
    ) -> Any:
        if schema is None:
            result = await self.clients.groq_text(
                self.model_id,
                prompt,
                system_instruction=self.system_instruction,
                role=self.role,
                profile_id=self.profile_id,
            )
        else:
            options = {"structured_response_mode": self.structured_response_mode} if self.structured_response_mode != "AUTO" else {}
            result = await self.clients.groq_structured(
                self.model_id,
                prompt,
                schema,
                system_instruction=self.system_instruction,
                role=self.role,
                profile_id=self.profile_id,
                **options,
            )
        self._record(result.metadata)
        return result.output


class OpenRouterDeepEvalModel(_SecMateDeepEvalModel):
    def get_model_name(self) -> str:
        return f"openrouter/{self.model_id}"

    async def a_generate(
        self,
        prompt: str,
        schema: type[BaseModel] | None = None,
    ) -> Any:
        if schema is None:
            result = await self.clients.openrouter_text(
                self.model_id,
                prompt,
                system_instruction=self.system_instruction,
                role=self.role,
                profile_id=self.profile_id,
            )
        else:
            result = await self.clients.openrouter_structured(
                self.model_id,
                prompt,
                schema,
                system_instruction=self.system_instruction,
                role=self.role,
                profile_id=self.profile_id,
            )
        self._record(result.metadata)
        return result.output
