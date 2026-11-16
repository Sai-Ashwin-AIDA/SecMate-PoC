import asyncio

import httpx
import pytest
from pydantic import BaseModel, model_validator

from secmate_worker.contracts import CampaignBudget, ProviderName, TokenUsage
from secmate_worker.execution_budget import (
    BudgetErrorCode,
    BudgetExceededError,
    CampaignBudgetManager,
)
from secmate_worker.model_clients import (
    ModelAttemptEvent,
    ModelClientSettings,
    ModelErrorCode,
    ModelRequestError,
    StructuredModelClients,
)


def campaign_budget(**overrides) -> CampaignBudget:
    values = {
        "max_paths": 2,
        "max_turns_per_path": 2,
        "max_provider_calls": 3,
        "max_concurrent_provider_calls": 1,
        "max_total_tokens": 10_000,
        "timeout_seconds": 60,
        "max_retries_per_call": 1,
    }
    values.update(overrides)
    return CampaignBudget(**values)


@pytest.mark.asyncio
async def test_path_and_turn_budgets_are_enforced():
    manager = CampaignBudgetManager(campaign_budget())

    await manager.reserve_path("path-1")
    assert await manager.record_turn("path-1") == 1
    assert await manager.record_turn("path-1") == 2

    with pytest.raises(BudgetExceededError) as turns_exhausted:
        await manager.record_turn("path-1")
    assert turns_exhausted.value.code == BudgetErrorCode.TURN_BUDGET_EXHAUSTED

    await manager.reserve_path("path-2")
    with pytest.raises(BudgetExceededError) as paths_exhausted:
        await manager.reserve_path("path-3")
    assert paths_exhausted.value.code == BudgetErrorCode.PATH_BUDGET_EXHAUSTED


@pytest.mark.asyncio
async def test_failed_calls_count_and_missing_usage_consumes_reservation():
    manager = CampaignBudgetManager(
        campaign_budget(max_provider_calls=1, max_total_tokens=100)
    )
    reservation = await manager.reserve_provider_call(
        ProviderName.GROQ,
        "model",
        estimated_tokens=30,
    )

    reservation.complete(usage=None, succeeded=False)
    snapshot = await manager.snapshot()

    assert snapshot.provider_calls_attempted == 1
    assert snapshot.provider_calls_failed == 1
    assert snapshot.provider_calls_succeeded == 0
    assert snapshot.tokens_consumed == 30
    assert snapshot.tokens_reserved == 0
    assert snapshot.calls_with_missing_usage == 1

    with pytest.raises(BudgetExceededError) as exhausted:
        await manager.reserve_provider_call(
            ProviderName.GROQ,
            "model",
            estimated_tokens=1,
        )
    assert exhausted.value.code == BudgetErrorCode.CALL_BUDGET_EXHAUSTED


@pytest.mark.asyncio
async def test_token_reservations_prevent_concurrent_overbooking():
    manager = CampaignBudgetManager(
        campaign_budget(
            max_concurrent_provider_calls=2,
            max_total_tokens=100,
        )
    )
    first = await manager.reserve_provider_call(
        ProviderName.GROQ,
        "model-a",
        estimated_tokens=60,
    )

    with pytest.raises(BudgetExceededError) as exhausted:
        await manager.reserve_provider_call(
            ProviderName.OPENROUTER,
            "model-b",
            estimated_tokens=50,
        )
    assert exhausted.value.code == BudgetErrorCode.TOKEN_BUDGET_EXHAUSTED

    first.complete(TokenUsage(total_tokens=40), succeeded=True)
    snapshot = await manager.snapshot()
    assert snapshot.tokens_consumed == 40
    assert snapshot.tokens_reserved == 0


@pytest.mark.asyncio
async def test_provider_concurrency_limit_blocks_until_capacity_is_released():
    manager = CampaignBudgetManager(
        campaign_budget(max_concurrent_provider_calls=1)
    )
    first = await manager.reserve_provider_call(
        ProviderName.GROQ,
        "model-a",
        estimated_tokens=10,
    )
    waiting = asyncio.create_task(
        manager.reserve_provider_call(
            ProviderName.OPENROUTER,
            "model-b",
            estimated_tokens=10,
        )
    )
    await asyncio.sleep(0)
    assert waiting.done() is False

    first.complete(TokenUsage(total_tokens=5), succeeded=True)
    second = await asyncio.wait_for(waiting, timeout=1)
    second.complete(TokenUsage(total_tokens=5), succeeded=True)

    snapshot = await manager.snapshot()
    assert snapshot.provider_calls_attempted == 2
    assert snapshot.provider_calls_succeeded == 2
    assert snapshot.provider_calls_in_flight == 0


@pytest.mark.asyncio
async def test_cancellation_and_deadline_prevent_new_work():
    now = [100.0]
    manager = CampaignBudgetManager(
        campaign_budget(timeout_seconds=10),
        clock=lambda: now[0],
    )
    await manager.cancel("operator request")

    with pytest.raises(BudgetExceededError) as cancelled:
        await manager.reserve_path("path-1")
    assert cancelled.value.code == BudgetErrorCode.CAMPAIGN_CANCELLED

    deadline_manager = CampaignBudgetManager(
        campaign_budget(timeout_seconds=10),
        clock=lambda: now[0],
    )
    now[0] = 110.0
    with pytest.raises(BudgetExceededError) as deadline:
        await deadline_manager.reserve_provider_call(
            ProviderName.GROQ,
            "model",
            estimated_tokens=1,
        )
    assert deadline.value.code == BudgetErrorCode.DEADLINE_EXCEEDED


@pytest.mark.asyncio
async def test_provider_client_stops_before_network_when_call_budget_is_exhausted():
    request_count = 0
    events: list[ModelAttemptEvent] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "READY"}}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
            },
        )

    manager = CampaignBudgetManager(campaign_budget(max_provider_calls=1))
    clients = StructuredModelClients(
        ModelClientSettings(groq_api_key="test-groq", openrouter_api_key=""),
        transport=httpx.MockTransport(handler),
        event_sink=events.append,
        budget_manager=manager,
    )

    assert (await clients.groq_text("model", "prompt")).output == "READY"
    with pytest.raises(ModelRequestError) as exhausted:
        await clients.groq_text("model", "prompt")

    assert exhausted.value.code == ModelErrorCode.BUDGET_EXHAUSTED
    assert exhausted.value.retryable is False
    assert request_count == 1
    assert len(events) == 2
    assert events[1].error_code == ModelErrorCode.BUDGET_EXHAUSTED


@pytest.mark.asyncio
async def test_provider_client_stops_before_network_when_tokens_cannot_be_reserved():
    request_count = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(200)

    manager = CampaignBudgetManager(campaign_budget(max_total_tokens=10))
    clients = StructuredModelClients(
        ModelClientSettings(groq_api_key="test-groq", openrouter_api_key=""),
        transport=httpx.MockTransport(handler),
        budget_manager=manager,
    )

    with pytest.raises(ModelRequestError) as exhausted:
        await clients.groq_text("model", "prompt")

    assert exhausted.value.code == ModelErrorCode.BUDGET_EXHAUSTED
    assert request_count == 0


@pytest.mark.asyncio
async def test_actual_usage_reconciles_the_token_reservation():
    manager = CampaignBudgetManager(campaign_budget(max_total_tokens=100))
    reservation = await manager.reserve_provider_call(
        ProviderName.GROQ,
        "model",
        estimated_tokens=80,
    )

    reservation.complete(TokenUsage(total_tokens=12), succeeded=True)
    snapshot = await manager.snapshot()

    assert snapshot.tokens_consumed == 12
    assert snapshot.tokens_reserved == 0
    assert snapshot.provider_calls_succeeded == 1


@pytest.mark.asyncio
async def test_cancellation_stops_an_active_provider_call_and_reconciles_budget():
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        started.set()
        try:
            await asyncio.sleep(60)
        finally:
            cancelled.set()
        return httpx.Response(200)

    manager = CampaignBudgetManager(campaign_budget())
    clients = StructuredModelClients(
        ModelClientSettings(groq_api_key="test-groq", openrouter_api_key=""),
        budget_manager=manager,
        transport=httpx.MockTransport(handler),
    )
    call = asyncio.create_task(clients.groq_text("model", "prompt"))
    await asyncio.wait_for(started.wait(), timeout=1)

    await manager.cancel("operator request")

    with pytest.raises(ModelRequestError) as stopped:
        await asyncio.wait_for(call, timeout=1)
    assert stopped.value.code == ModelErrorCode.CAMPAIGN_CANCELLED
    assert cancelled.is_set()
    snapshot = await manager.snapshot()
    assert snapshot.provider_calls_in_flight == 0
    assert snapshot.tokens_reserved == 0
    assert snapshot.provider_calls_failed == 1


@pytest.mark.asyncio
async def test_cancellation_wakes_provider_capacity_waiters():
    manager = CampaignBudgetManager(
        campaign_budget(max_concurrent_provider_calls=1)
    )
    first = await manager.reserve_provider_call(
        ProviderName.GROQ,
        "model-a",
        estimated_tokens=10,
    )
    waiting = asyncio.create_task(
        manager.reserve_provider_call(
            ProviderName.OPENROUTER,
            "model-b",
            estimated_tokens=10,
        )
    )
    await asyncio.sleep(0)

    await manager.cancel("operator request")

    with pytest.raises(BudgetExceededError) as stopped:
        await asyncio.wait_for(waiting, timeout=1)
    assert stopped.value.code == BudgetErrorCode.CAMPAIGN_CANCELLED
    first.complete(None, succeeded=False)


@pytest.mark.asyncio
async def test_external_waiter_cancellation_does_not_leak_provider_capacity():
    manager = CampaignBudgetManager(
        campaign_budget(max_concurrent_provider_calls=1)
    )
    first = await manager.reserve_provider_call(
        ProviderName.GROQ,
        "model-a",
        estimated_tokens=10,
    )
    waiting = asyncio.create_task(
        manager.reserve_provider_call(
            ProviderName.OPENROUTER,
            "model-b",
            estimated_tokens=10,
        )
    )
    await asyncio.sleep(0)
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting

    first.complete(None, succeeded=False)
    next_reservation = await asyncio.wait_for(
        manager.reserve_provider_call(
            ProviderName.GROQ,
            "model-c",
            estimated_tokens=10,
        ),
        timeout=1,
    )
    next_reservation.complete(TokenUsage(total_tokens=1), succeeded=True)


@pytest.mark.asyncio
async def test_repeated_cancellation_waits_for_provider_cleanup_without_leaking():
    started = asyncio.Event()
    unwinding = asyncio.Event()
    allow_cleanup = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        started.set()
        try:
            await asyncio.sleep(60)
        finally:
            unwinding.set()
            await allow_cleanup.wait()
        return httpx.Response(200)

    manager = CampaignBudgetManager(campaign_budget())
    clients = StructuredModelClients(
        ModelClientSettings(groq_api_key="test-groq", openrouter_api_key=""),
        budget_manager=manager,
        transport=httpx.MockTransport(handler),
    )
    call = asyncio.create_task(clients.groq_text("model", "prompt"))
    await asyncio.wait_for(started.wait(), timeout=1)
    call.cancel()
    await asyncio.wait_for(unwinding.wait(), timeout=1)
    call.cancel()
    await asyncio.sleep(0)
    assert call.done() is False

    allow_cleanup.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(call, timeout=1)

    snapshot = await manager.snapshot()
    assert snapshot.provider_calls_in_flight == 0
    assert snapshot.tokens_reserved == 0
    next_reservation = await asyncio.wait_for(
        manager.reserve_provider_call(
            ProviderName.GROQ,
            "model-next",
            estimated_tokens=10,
        ),
        timeout=1,
    )
    next_reservation.complete(TokenUsage(total_tokens=1), succeeded=True)


@pytest.mark.asyncio
async def test_deadline_cancels_an_active_provider_call():
    started = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        started.set()
        await asyncio.sleep(60)
        return httpx.Response(200)

    manager = CampaignBudgetManager(campaign_budget(timeout_seconds=1))
    clients = StructuredModelClients(
        ModelClientSettings(groq_api_key="test-groq", openrouter_api_key=""),
        budget_manager=manager,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ModelRequestError) as stopped:
        await clients.groq_text("model", "prompt")

    assert started.is_set()
    assert stopped.value.code == ModelErrorCode.DEADLINE_EXCEEDED
    snapshot = await manager.snapshot()
    assert snapshot.provider_calls_in_flight == 0
    assert snapshot.provider_calls_failed == 1


def test_token_overrun_is_recorded_and_fails_closed():
    manager = CampaignBudgetManager(campaign_budget(max_total_tokens=100))

    async def exercise():
        reservation = await manager.reserve_provider_call(
            ProviderName.GROQ,
            "model",
            estimated_tokens=80,
        )
        error = reservation.complete(TokenUsage(total_tokens=120), succeeded=True)
        snapshot = await manager.snapshot()
        return error, snapshot

    error, snapshot = asyncio.run(exercise())

    assert error is not None
    assert error.code == BudgetErrorCode.TOKEN_BUDGET_EXHAUSTED
    assert snapshot.token_budget_overrun is True
    assert snapshot.tokens_consumed == 120
    assert snapshot.cancelled is True
    assert snapshot.provider_calls_succeeded == 0
    assert snapshot.provider_calls_failed == 1


def test_concurrent_token_commitment_overrun_cancels_remaining_work():
    manager = CampaignBudgetManager(
        campaign_budget(
            max_concurrent_provider_calls=2,
            max_total_tokens=100,
        )
    )

    async def exercise():
        first = await manager.reserve_provider_call(
            ProviderName.GROQ,
            "model-a",
            estimated_tokens=50,
        )
        second = await manager.reserve_provider_call(
            ProviderName.OPENROUTER,
            "model-b",
            estimated_tokens=50,
        )
        error = first.complete(TokenUsage(total_tokens=80), succeeded=True)
        snapshot = await manager.snapshot()
        second.complete(None, succeeded=False)
        return error, snapshot

    error, snapshot = asyncio.run(exercise())

    assert error is not None
    assert error.code == BudgetErrorCode.TOKEN_BUDGET_EXHAUSTED
    assert snapshot.tokens_consumed == 80
    assert snapshot.tokens_reserved == 50
    assert snapshot.token_budget_overrun is True
    assert snapshot.cancelled is True
    assert snapshot.provider_calls_succeeded == 0
    assert snapshot.provider_calls_failed == 1


@pytest.mark.asyncio
async def test_client_never_exceeds_configured_network_concurrency():
    active = 0
    maximum_active = 0
    release = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal active, maximum_active
        active += 1
        maximum_active = max(maximum_active, active)
        try:
            await release.wait()
        finally:
            active -= 1
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "READY"}}],
                "usage": {"total_tokens": 1},
            },
        )

    manager = CampaignBudgetManager(
        campaign_budget(max_concurrent_provider_calls=1)
    )
    clients = StructuredModelClients(
        ModelClientSettings(groq_api_key="test-groq", openrouter_api_key=""),
        budget_manager=manager,
        transport=httpx.MockTransport(handler),
    )
    first = asyncio.create_task(clients.groq_text("model", "first"))
    second = asyncio.create_task(clients.groq_text("model", "second"))
    while maximum_active == 0:
        await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert maximum_active == 1

    release.set()
    await asyncio.gather(first, second)
    assert maximum_active == 1


@pytest.mark.asyncio
async def test_deadline_is_rechecked_after_response_processing():
    now = [100.0]

    class DelayedReply(BaseModel):
        status: str

        @model_validator(mode="after")
        def advance_clock(self):
            now[0] = 111.0
            return self

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"status":"READY"}'}}],
                "usage": {"total_tokens": 3},
            },
        )

    manager = CampaignBudgetManager(
        campaign_budget(timeout_seconds=10),
        clock=lambda: now[0],
    )
    clients = StructuredModelClients(
        ModelClientSettings(groq_api_key="test-groq", openrouter_api_key=""),
        budget_manager=manager,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ModelRequestError) as expired:
        await clients.groq_structured("model", "prompt", DelayedReply)

    assert expired.value.code == ModelErrorCode.DEADLINE_EXCEEDED
    snapshot = await manager.snapshot()
    assert snapshot.provider_calls_failed == 1
    assert snapshot.provider_calls_in_flight == 0
