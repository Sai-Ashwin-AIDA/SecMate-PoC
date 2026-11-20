"""Small explicit source ledger and per-operation context; no conversation loop."""

import json
import os
import time
from dataclasses import dataclass, field

from .contracts import CreateData, DocumentError, ReadData, StrictModel


class Source(StrictModel):
    source_id: str
    path: str
    sha256: str
    start_line: int
    end_line: int
    representation: str

    def reference(self) -> str:
        label = "extracted email lines" if self.representation == "extracted_email" else "lines"
        # JSON quoting keeps unusual but valid filenames readable and unambiguous.
        return (
            f"[{self.source_id}] input/{json.dumps(self.path, ensure_ascii=False)}"
            f", {label} {self.start_line}–{self.end_line}"
        )


@dataclass
class SourceLedger:
    """Bounded metadata; the controller owns active/retained-turn eviction."""

    capacity: int = 32
    _next_id: int = 1
    _sources: dict[str, Source] = field(default_factory=dict)
    _identities: dict[str, str] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if type(self.capacity) is not int or not 1 <= self.capacity <= 192:
            raise ValueError("Ledger capacity must be 1–192.")

    def register(
        self, *, path: str, sha256: str, start: int, end: int, representation: str,
        identity: str | None = None,
    ) -> tuple[Source, bool]:
        if len(self._sources) >= self.capacity:
            raise DocumentError("LIMIT_EXCEEDED", "The active source ledger is full.")
        identity = os.path.normcase(path) if identity is None else identity
        changed = any(
            self._identities[s.source_id] == identity and s.sha256 != sha256
            for s in self._sources.values()
        )
        source = Source(
            source_id=f"R{self._next_id}", path=path, sha256=sha256,
            start_line=start, end_line=end, representation=representation,
        )
        self._next_id += 1
        self._sources[source.source_id] = source
        self._identities[source.source_id] = identity
        return source, changed

    def require(self, source_ids: list[str]) -> list[Source]:
        if any(source_id not in self._sources for source_id in source_ids):
            raise DocumentError("UNKNOWN_SOURCE", "A source ID is unknown or no longer retained.")
        return [self._sources[source_id] for source_id in source_ids]

    def discard(self, source_ids: list[str]) -> None:
        for source_id in source_ids:
            self._sources.pop(source_id, None)
            self._identities.pop(source_id, None)

    def snapshot(self) -> tuple[Source, ...]:
        return tuple(self._sources.values())


@dataclass
class ToolContext:
    ledger: SourceLedger = field(default_factory=SourceLedger)
    deadline: float | None = None
    reads: list[ReadData] = field(default_factory=list)
    created: list[CreateData] = field(default_factory=list)
    uncertain_outputs: list[str] = field(default_factory=list)

    def check_deadline(self) -> None:
        if self.deadline is not None and time.monotonic() >= self.deadline:
            raise DocumentError("LIMIT_EXCEEDED", "The operation deadline has expired.")
