from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeVar

from .contracts import CampaignBudget, ProviderName, TokenUsage


ResultT = TypeVar("ResultT")


class BudgetErrorCode(StrEnum):
    CAMPAIGN_CANCELLED = "CAMPAIGN_CANCELLED"
    DEADLINE_EXCEEDED = "DEADLINE_EXCEEDED"
    PATH_BUDGET_EXHAUSTED = "PATH_BUDGET_EXHAUSTED"
    TURN_BUDGET_EXHAUSTED = "TURN_BUDGET_EXHAUSTED"
    CALL_BUDGET_EXHAUSTED = "CALL_BUDGET_EXHAUSTED"
    TOKEN_BUDGET_EXHAUSTED = "TOKEN_BUDGET_EXHAUSTED"
    PATH_ALREADY_RESERVED = "PATH_ALREADY_RESERVED"
    UNKNOWN_PATH = "UNKNOWN_PATH"


class BudgetExceededError(RuntimeError):
    def __init__(self, code: BudgetErrorCode, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class BudgetSnapshot:
    max_paths: int
    paths_started: int
    max_turns_per_path: int
    turns_by_path: dict[str, int]
    max_provider_calls: int
    provider_calls_attempted: int
    provider_calls_succeeded: int
    provider_calls_failed: int
    max_concurrent_provider_calls: int
    provider_calls_in_flight: int
    max_total_tokens: int
    tokens_consumed: int
    tokens_reserved: int
    calls_with_missing_usage: int
    token_budget_overrun: bool
    cancelled: bool
    cancellation_reason: str | None
    deadline_seconds_remaining: float


class ProviderCallReservation:
    def __init__(
        self,
        manager: CampaignBudgetManager,
        provider: ProviderName,
        model: str,
        estimated_tokens: int,
    ):
        self._manager = manager
        self.provider = provider
        self.model = model
        self.estimated_tokens = estimated_tokens
        self._completed = False

    def complete(
        self,
        usage: TokenUsage | None,
        succeeded: bool,
    ) -> BudgetExceededError | None:
        if self._completed:
            return None
        result = self._manager._complete_provider_call(self, usage, succeeded)
        self._completed = True
        return result


class CampaignBudgetManager:
    def __init__(
        self,
        budget: CampaignBudget,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.budget = budget
        self._clock = clock
        self._deadline = clock() + budget.timeout_seconds
        self._lock = asyncio.Lock()
        self._provider_semaphore = asyncio.Semaphore(
            budget.max_concurrent_provider_calls
        )
        self._cancel_event = asyncio.Event()
        self._paths: dict[str, int] = {}
        self._provider_calls_attempted = 0
        self._provider_calls_succeeded = 0
        self._provider_calls_failed = 0
        self._provider_calls_in_flight = 0
        self._tokens_consumed = 0
        self._tokens_reserved = 0
        self._calls_with_missing_usage = 0
        self._token_budget_overrun = False
        self._cancelled = False
        self._cancellation_reason: str | None = None

    async def reserve_path(self, path_id: str) -> None:
        async with self._lock:
            self._raise_if_stopped()
            if path_id in self._paths:
                raise BudgetExceededError(
                    BudgetErrorCode.PATH_ALREADY_RESERVED,
                    f"Attack path {path_id!r} was already reserved.",
                )
            if len(self._paths) >= self.budget.max_paths:
                raise BudgetExceededError(
                    BudgetErrorCode.PATH_BUDGET_EXHAUSTED,
                    "Campaign path budget is exhausted.",
                )
            self._paths[path_id] = 0

    async def record_turn(self, path_id: str) -> int:
        async with self._lock:
            self._raise_if_stopped()
            if path_id not in self._paths:
                raise BudgetExceededError(
                    BudgetErrorCode.UNKNOWN_PATH,
                    f"Attack path {path_id!r} is not reserved.",
                )
            current = self._paths[path_id]
            if current >= self.budget.max_turns_per_path:
                raise BudgetExceededError(
                    BudgetErrorCode.TURN_BUDGET_EXHAUSTED,
                    f"Turn budget is exhausted for path {path_id!r}.",
                )
            current += 1
            self._paths[path_id] = current
            return current

    async def reserve_provider_call(
        self,
        provider: ProviderName,
        model: str,
        estimated_tokens: int,
    ) -> ProviderCallReservation:
        if estimated_tokens < 1:
            raise ValueError("estimated_tokens must be positive")

        await self._acquire_provider_capacity()
        try:
            async with self._lock:
                self._raise_if_stopped()
                if self._provider_calls_attempted >= self.budget.max_provider_calls:
                    raise BudgetExceededError(
                        BudgetErrorCode.CALL_BUDGET_EXHAUSTED,
                        "Campaign provider-call budget is exhausted.",
                    )
                projected_tokens = (
                    self._tokens_consumed
                    + self._tokens_reserved
                    + estimated_tokens
                )
                if projected_tokens > self.budget.max_total_tokens:
                    raise BudgetExceededError(
                        BudgetErrorCode.TOKEN_BUDGET_EXHAUSTED,
                        "Campaign token budget cannot reserve this provider call.",
                    )
                self._provider_calls_attempted += 1
                self._provider_calls_in_flight += 1
                self._tokens_reserved += estimated_tokens
                return ProviderCallReservation(
                    manager=self,
                    provider=provider,
                    model=model,
                    estimated_tokens=estimated_tokens,
                )
        except BaseException:
            self._provider_semaphore.release()
            raise

    async def run_provider_operation(
        self,
        operation_factory: Callable[[], Awaitable[ResultT]],
    ) -> ResultT:
        async with self._lock:
            self._raise_if_stopped()
            remaining = self._remaining_seconds()

        operation_task = asyncio.create_task(operation_factory())
        cancellation_task = asyncio.create_task(self._cancel_event.wait())
        try:
            done, _ = await asyncio.wait(
                {operation_task, cancellation_task},
                timeout=remaining,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if cancellation_task in done and cancellation_task.result():
                await self._cancel_task(operation_task)
                raise BudgetExceededError(
                    BudgetErrorCode.CAMPAIGN_CANCELLED,
                    f"Campaign is cancelled: {self._cancellation_reason}.",
                )
            if operation_task not in done:
                await self._cancel_task(operation_task)
                raise BudgetExceededError(
                    BudgetErrorCode.DEADLINE_EXCEEDED,
                    "Campaign deadline expired during provider execution.",
                )
            return await operation_task
        except asyncio.CancelledError:
            await self._cancel_task(operation_task)
            raise
        finally:
            if not cancellation_task.done():
                cancellation_task.cancel()

    async def cancel(self, reason: str) -> None:
        async with self._lock:
            self._cancelled = True
            self._cancellation_reason = reason.strip() or "unspecified"
            self._cancel_event.set()

    async def ensure_active(self) -> None:
        async with self._lock:
            self._raise_if_stopped()

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self._remaining_seconds())

    async def snapshot(self) -> BudgetSnapshot:
        async with self._lock:
            return BudgetSnapshot(
                max_paths=self.budget.max_paths,
                paths_started=len(self._paths),
                max_turns_per_path=self.budget.max_turns_per_path,
                turns_by_path=dict(self._paths),
                max_provider_calls=self.budget.max_provider_calls,
                provider_calls_attempted=self._provider_calls_attempted,
                provider_calls_succeeded=self._provider_calls_succeeded,
                provider_calls_failed=self._provider_calls_failed,
                max_concurrent_provider_calls=(
                    self.budget.max_concurrent_provider_calls
                ),
                provider_calls_in_flight=self._provider_calls_in_flight,
                max_total_tokens=self.budget.max_total_tokens,
                tokens_consumed=self._tokens_consumed,
                tokens_reserved=self._tokens_reserved,
                calls_with_missing_usage=self._calls_with_missing_usage,
                token_budget_overrun=self._token_budget_overrun,
                cancelled=self._cancelled,
                cancellation_reason=self._cancellation_reason,
                deadline_seconds_remaining=max(0, self._remaining_seconds()),
            )

    async def _acquire_provider_capacity(self) -> None:
        async with self._lock:
            self._raise_if_stopped()
            remaining = self._remaining_seconds()

        capacity_task = asyncio.create_task(self._provider_semaphore.acquire())
        cancellation_task = asyncio.create_task(self._cancel_event.wait())
        try:
            done, _ = await asyncio.wait(
                {capacity_task, cancellation_task},
                timeout=remaining,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if cancellation_task in done and cancellation_task.result():
                if capacity_task in done and capacity_task.result():
                    self._provider_semaphore.release()
                else:
                    await self._cancel_task(capacity_task)
                raise BudgetExceededError(
                    BudgetErrorCode.CAMPAIGN_CANCELLED,
                    f"Campaign is cancelled: {self._cancellation_reason}.",
                )
            if capacity_task not in done:
                await self._cancel_task(capacity_task)
                raise BudgetExceededError(
                    BudgetErrorCode.DEADLINE_EXCEEDED,
                    "Campaign deadline expired while waiting for provider capacity.",
                )
            capacity_task.result()
        except asyncio.CancelledError:
            if capacity_task.done() and not capacity_task.cancelled():
                self._provider_semaphore.release()
            else:
                await self._cancel_task(capacity_task)
            raise
        finally:
            if not cancellation_task.done():
                cancellation_task.cancel()

    def _complete_provider_call(
        self,
        reservation: ProviderCallReservation,
        usage: TokenUsage | None,
        succeeded: bool,
    ) -> BudgetExceededError | None:
        self._provider_calls_in_flight -= 1
        self._tokens_reserved -= reservation.estimated_tokens
        actual_tokens = self._actual_or_reserved_tokens(reservation, usage)
        self._tokens_consumed += actual_tokens
        if usage is None or usage.total_tokens is None:
            self._calls_with_missing_usage += 1
        committed_tokens = self._tokens_consumed + self._tokens_reserved
        if committed_tokens > self.budget.max_total_tokens:
            self._token_budget_overrun = True
            self._cancelled = True
            self._cancellation_reason = "token budget overrun"
            self._cancel_event.set()
            self._provider_calls_failed += 1
            self._provider_semaphore.release()
            return BudgetExceededError(
                BudgetErrorCode.TOKEN_BUDGET_EXHAUSTED,
                "Provider usage exceeded the campaign token commitment.",
            )
        if succeeded:
            self._provider_calls_succeeded += 1
        else:
            self._provider_calls_failed += 1
        self._provider_semaphore.release()
        return None

    @staticmethod
    def _actual_or_reserved_tokens(
        reservation: ProviderCallReservation,
        usage: TokenUsage | None,
    ) -> int:
        if usage is None:
            return reservation.estimated_tokens
        if usage.total_tokens is not None:
            return usage.total_tokens
        if usage.prompt_tokens is not None and usage.completion_tokens is not None:
            return usage.prompt_tokens + usage.completion_tokens
        return reservation.estimated_tokens

    def _raise_if_stopped(self) -> None:
        if self._cancelled:
            raise BudgetExceededError(
                BudgetErrorCode.CAMPAIGN_CANCELLED,
                f"Campaign is cancelled: {self._cancellation_reason}.",
            )
        if self._clock() >= self._deadline:
            raise BudgetExceededError(
                BudgetErrorCode.DEADLINE_EXCEEDED,
                "Campaign deadline is exhausted.",
            )

    def _remaining_seconds(self) -> float:
        return max(0, self._deadline - self._clock())

    @staticmethod
    async def _cancel_task(task: asyncio.Task) -> None:
        if not task.done():
            task.cancel()
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except BaseException:
                break
        if task.done() and not task.cancelled():
            try:
                task.result()
            except BaseException:
                pass
