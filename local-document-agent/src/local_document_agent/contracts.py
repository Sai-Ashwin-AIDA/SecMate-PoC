"""Strict arguments and bounded, typed tool results; no runtime configuration."""

from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class SearchArguments(StrictModel):
    query: str = Field(min_length=1, max_length=200, description="Literal substring to find.")
    scope: Literal["filename", "text", "both"] = Field(description="Search relative paths, text, or both.")
    offset: int = Field(ge=0, le=999, description="Zero-based result offset.")
    limit: int = Field(ge=1, le=20, description="Maximum results returned.")

    @field_validator("query")
    @classmethod
    def meaningful_query(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Query must not be blank.")
        return value


class ReadArguments(StrictModel):
    path: str = Field(min_length=1, max_length=240, description="Input-relative path using /.")
    start_line: int = Field(ge=1, le=1_000_000, description="First normalized line, one-based.")
    max_lines: int = Field(ge=1, le=200, description="Maximum normalized lines to read.")


class CreateArguments(StrictModel):
    filename: str = Field(min_length=1, max_length=80, description="New flat .txt or .md basename.")
    kind: Literal["report", "email_draft"] = Field(description="Report or local unsent email draft.")
    content: str = Field(min_length=1, max_length=24_000, description="Text to save, not instructions to execute.")
    source_ids: list[Annotated[str, Field(pattern=r"^R[1-9][0-9]{0,8}$")]] = Field(
        max_length=20, description="Unique source IDs returned by successful reads; [] is allowed."
    )

    @field_validator("content")
    @classmethod
    def meaningful_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Content must not be blank.")
        return value

    @field_validator("source_ids")
    @classmethod
    def unique_sources(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("Source IDs must be unique.")
        return value


ErrorCode = Literal[
    "INVALID_ARGUMENTS", "UNKNOWN_TOOL", "INVALID_PATH", "OUTSIDE_ROOT",
    "REPARSE_POINT", "NOT_REGULAR_FILE", "UNSUPPORTED_TYPE", "NOT_FOUND",
    "PERMISSION_DENIED", "FILE_TOO_LARGE", "EXTRACTED_TEXT_TOO_LARGE",
    "DECODE_ERROR", "MALFORMED_EMAIL", "HTML_ONLY_EMAIL", "NO_READABLE_CONTENT",
    "INVALID_RANGE", "RANGE_TOO_LARGE", "SEARCH_LIMIT", "SEARCH_TIMEOUT",
    "UNKNOWN_SOURCE", "FILE_EXISTS", "WRITE_FAILED", "IO_ERROR", "LIMIT_EXCEEDED",
]
ToolName = Literal["search_documents", "read_document", "create_document"]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class ToolError(StrictModel):
    code: ErrorCode
    message: str = Field(max_length=300)


class SearchIssue(StrictModel):
    path: str = Field(max_length=240)
    code: ErrorCode


class SearchHit(StrictModel):
    path: str = Field(max_length=240)
    matched_in: list[Literal["filename", "text"]] = Field(min_length=1, max_length=2)
    snippet: str | None = Field(max_length=160)
    snippet_line: int | None = Field(ge=1)
    snippet_truncated: bool


class SearchData(StrictModel):
    query: str = Field(max_length=200)
    scope: Literal["filename", "text", "both"]
    results: list[SearchHit] = Field(max_length=20)
    returned: int = Field(ge=0, le=20)
    offset: int = Field(ge=0, le=999)
    has_more: bool
    partial: bool
    inspected_file_count: int = Field(ge=0, le=1000)
    skipped_count: int = Field(ge=0, le=1000)
    issues: list[SearchIssue] = Field(max_length=20)
    issues_truncated: bool


class ReadData(StrictModel):
    path: str = Field(max_length=240)
    kind: Literal["text", "markdown", "email"]
    representation: Literal["normalized_text", "extracted_email"]
    sha256: Digest
    source_id: str = Field(pattern=r"^R[1-9][0-9]{0,8}$")
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=0)
    total_lines: int = Field(ge=0)
    text: str = Field(max_length=12_000)
    has_more: bool
    next_start_line: int | None = Field(ge=1)
    complete_document: bool


class CreateData(StrictModel):
    path: str = Field(max_length=80)
    kind: Literal["report", "email_draft"]
    bytes_written: int = Field(ge=1, le=65_536)
    sha256: Digest
    source_ids: list[str] = Field(max_length=20)
    not_sent: Literal[True] | None


T = TypeVar("T", SearchData, ReadData, CreateData)


class ToolResult(StrictModel, Generic[T]):
    ok: bool
    tool: ToolName
    data: T | None
    warnings: list[Annotated[str, Field(max_length=300)]] = Field(max_length=20)
    error: ToolError | None

    @model_validator(mode="after")
    def consistent_status(self) -> "ToolResult[T]":
        if self.ok != (self.data is not None and self.error is None):
            raise ValueError("Success requires data and no error.")
        if not self.ok and (self.data is not None or self.error is None):
            raise ValueError("Failure requires an error and no data.")
        expected = {
            "search_documents": SearchData,
            "read_document": ReadData,
            "create_document": CreateData,
        }
        if self.data is not None and not isinstance(self.data, expected[self.tool]):
            raise ValueError("Result data must match its tool name.")
        return self


class DocumentError(Exception):
    """An intentionally sanitized operation failure."""

    def __init__(self, code: ErrorCode, message: str, *, possible_output: str | None = None) -> None:
        self.error = ToolError(code=code, message=message)
        self.possible_output = possible_output
        super().__init__(message)


def failure(tool: ToolName, error: ToolError, warnings: list[str] | None = None) -> str:
    return ToolResult[ReadData](
        ok=False, tool=tool, data=None, warnings=warnings or [], error=error
    ).model_dump_json()
