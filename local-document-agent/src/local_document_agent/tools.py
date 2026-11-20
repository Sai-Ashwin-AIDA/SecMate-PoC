"""Exactly three real LangChain tools backed by confined local operations."""

import hashlib
import os
from pathlib import Path
from typing import Any, Callable

from langchain.tools import tool
from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, StructuredTool, ToolException
from pydantic import ValidationError

from .config import reject_tracing
from .context import ToolContext
from .contracts import (
    CreateArguments, CreateData, DocumentError, ReadArguments, ReadData,
    SearchArguments, SearchData, SearchHit, SearchIssue, StrictModel, ToolError,
    ToolName, ToolResult, failure,
)
from .filesystem import (
    FilesystemRoots, RAW_LIMIT, map_os_error, search_deadline, validate_output_name,
)
from .text import extract, normalize

SEARCH_BYTE_LIMIT = 16 * 1024 * 1024


def invalid_arguments(name: ToolName) -> str:
    return failure(name, ToolError(
        code="INVALID_ARGUMENTS",
        message="Arguments must match the tool schema exactly; no coercion or extra fields are allowed.",
    ))


class StrictStructuredTool(StructuredTool):
    """Validate the public invocation boundary without echoing rejected inputs."""

    @property
    def tool_call_schema(self) -> type[StrictModel]:
        # These three tools have no injected fields. LangChain's subset-schema
        # reconstruction drops extra="forbid"; expose the original strict model.
        return self.args_schema

    def invoke(
        self, input: str | dict[str, Any], config: RunnableConfig | None = None, **kwargs: Any
    ) -> Any:
        reject_tracing(os.environ)
        call = input if isinstance(input, dict) and input.get("type") == "tool_call" else None
        arguments = call.get("args") if call is not None else input
        try:
            if not isinstance(arguments, dict) or not isinstance(self.args_schema, type):
                raise ValueError("Object arguments required")
            self.args_schema.model_validate(arguments, strict=True)
            if call is not None and (
                call.get("name") != self.name
                or not isinstance(call.get("id"), str) or not 1 <= len(call["id"]) <= 128
            ):
                raise ValueError("Invalid tool call")
        except (ValidationError, ValueError):
            result = invalid_arguments(self.name)
            if call is not None and isinstance(call.get("id"), str) and call["id"]:
                return ToolMessage(
                    content=result, name=self.name, tool_call_id=call["id"], status="error"
                )
            return result
        return super().invoke(input, config=config, **kwargs)

    async def ainvoke(
        self, input: str | dict[str, Any], config: RunnableConfig | None = None, **kwargs: Any
    ) -> Any:
        # Deliberately sequential bounded local I/O; no background thread can outlive cancellation.
        return self.invoke(input, config=config, **kwargs)

    def run(self, tool_input: str | dict[str, Any], *args: Any, **kwargs: Any) -> Any:
        reject_tracing(os.environ)
        return super().run(tool_input, *args, **kwargs)

    async def arun(self, tool_input: str | dict[str, Any], *args: Any, **kwargs: Any) -> Any:
        reject_tracing(os.environ)
        # Do not use StructuredTool's executor fallback for bounded local writes.
        return self.run(tool_input, *args, **kwargs)


class DocumentOperations:
    """Host operations shared by tool wrappers; no provider or conversation state."""

    def __init__(self, roots: FilesystemRoots, context: ToolContext) -> None:
        self.roots = roots
        self.context = context

    def search(self, arguments: SearchArguments) -> tuple[SearchData, list[str]]:
        check = search_deadline(self.context.check_deadline)
        inventory = self.roots.inventory(check)
        hits: list[SearchHit] = []
        issues = list(inventory.issues)
        skipped = len(issues)
        inspected = 0
        byte_count = 0
        partial = bool(issues)
        warnings: list[str] = []
        query = arguments.query.casefold()
        for index, relative in enumerate(inventory.files):
            check()
            filename_match = arguments.scope != "text" and query in relative.casefold()
            matched: list[str] = ["filename"] if filename_match else []
            snippet = None
            line_number = None
            truncated = False
            if arguments.scope != "filename":
                try:
                    candidate = self.roots.input_path(relative)
                    size = candidate.stat().st_size
                    if size > RAW_LIMIT:
                        raise DocumentError("FILE_TOO_LARGE", "The raw file exceeds 256 KiB.")
                    if byte_count + size > SEARCH_BYTE_LIMIT:
                        partial = True
                        skipped += len(inventory.files) - index
                        warnings.append("Aggregate search byte limit reached; remaining files were not inspected.")
                        break
                    # Charge attempted reads conservatively even when extraction fails.
                    remaining = SEARCH_BYTE_LIMIT - byte_count
                    byte_count += size
                    raw = self.roots.read_bytes(relative, check, byte_budget=remaining)
                    byte_count += max(0, len(raw) - size)
                    inspected += 1
                    extracted = extract(raw, Path(relative).suffix)
                    folded = extracted.text.casefold()
                    position = folded.find(query)
                    if position >= 0:
                        matched.append("text")
                        cursor = 0
                        for number, line in enumerate(extracted.text.splitlines(keepends=True), 1):
                            cursor += len(line.casefold())
                            if cursor > position:
                                clean_line = line.rstrip("\r\n")
                                snippet = clean_line[:160]
                                line_number = number
                                truncated = len(clean_line) > 160
                                break
                    if extracted.warnings:
                        # Counts only; no attachment contents or personal header logging.
                        warnings.extend(extracted.warnings)
                except DocumentError as error:
                    if error.error.code in ("SEARCH_TIMEOUT", "LIMIT_EXCEEDED"):
                        raise
                    if error.error.code == "SEARCH_LIMIT":
                        partial = True
                        skipped += len(inventory.files) - index
                        warnings.append("Aggregate search byte limit reached; remaining files were not inspected.")
                        break
                    skipped += 1
                    partial = True
                    issues.append(SearchIssue(path=relative, code=error.error.code))
                except OSError as error:
                    skipped += 1
                    partial = True
                    issues.append(SearchIssue(path=relative, code=map_os_error(error).error.code))
            if matched:
                hits.append(SearchHit(
                    path=relative, matched_in=matched, snippet=snippet,
                    snippet_line=line_number, snippet_truncated=truncated,
                ))
        check()
        issues.sort(key=lambda issue: (issue.path.casefold(), issue.path, issue.code))
        page = hits[arguments.offset:arguments.offset + arguments.limit]
        return SearchData(
            query=arguments.query, scope=arguments.scope, results=page, returned=len(page),
            offset=arguments.offset, has_more=len(hits) > arguments.offset + len(page),
            partial=partial, inspected_file_count=inspected, skipped_count=skipped,
            issues=issues[:20], issues_truncated=len(issues) > 20,
        ), list(dict.fromkeys(warnings))[:20]

    def read(self, arguments: ReadArguments) -> tuple[ReadData, list[str]]:
        raw = self.roots.read_bytes(arguments.path, self.context.check_deadline)
        extracted = extract(raw, Path(arguments.path).suffix)
        lines = extracted.text.splitlines()
        total = len(lines)
        if arguments.start_line > max(total, 1):
            raise DocumentError("INVALID_RANGE", "The requested starting line is beyond the document.")
        end = min(total, arguments.start_line - 1 + arguments.max_lines)
        text = "\n".join(lines[arguments.start_line - 1:end])
        if len(text) > 12_000:
            raise DocumentError("RANGE_TOO_LARGE", "The range exceeds 12000 characters; request fewer lines.")
        self.context.check_deadline()
        source, changed = self.context.ledger.register(
            path=arguments.path, sha256=hashlib.sha256(raw).hexdigest(),
            start=arguments.start_line, end=end, representation=extracted.representation,
            identity=os.path.normcase(str(self.roots.input_path(arguments.path))),
        )
        result = ReadData(
            path=arguments.path, kind=extracted.kind, representation=extracted.representation,
            sha256=source.sha256, source_id=source.source_id,
            start_line=arguments.start_line, end_line=end, total_lines=total, text=text,
            has_more=end < total, next_start_line=end + 1 if end < total else None,
            complete_document=arguments.start_line == 1 and end == total,
        )
        self.context.reads.append(result)
        warnings = list(extracted.warnings)
        if changed:
            warnings.append("Different versions of this input path have been read; source hashes differ.")
        return result, warnings

    def create(self, arguments: CreateArguments) -> tuple[CreateData, list[str]]:
        validate_output_name(arguments.filename)
        sources = self.context.ledger.require(arguments.source_ids)
        if len(self.context.created) >= 32:
            raise DocumentError("LIMIT_EXCEEDED", "The active context has reached 32 created files.")
        content = normalize(arguments.content)
        if arguments.kind == "email_draft":
            content = "EMAIL DRAFT — NOT SENT\n\n" + content
        if sources:
            content += (
                "\n\n---\nSource files read\n"
                "Observed read ranges; not independent verification of every claim.\n"
                + "\n".join(source.reference() for source in sources)
            )
        try:
            data = content.encode("utf-8", errors="strict")
        except UnicodeError:
            raise DocumentError("DECODE_ERROR", "Output must be valid UTF-8 text.") from None
        count, digest = self.roots.create_bytes(
            arguments.filename, data, self.context.check_deadline
        )
        result = CreateData(
            path=arguments.filename, kind=arguments.kind, bytes_written=count, sha256=digest,
            source_ids=arguments.source_ids,
            not_sent=True if arguments.kind == "email_draft" else None,
        )
        self.context.created.append(result)
        return result, []


def build_tools(roots: FilesystemRoots, context: ToolContext | None = None) -> tuple[BaseTool, ...]:
    """Create only search/read/create LangChain tools; never load configuration."""
    reject_tracing(os.environ)
    operations = DocumentOperations(roots, context if context is not None else ToolContext())

    def run(name: ToolName, schema: type[StrictModel], values: dict[str, Any], function: Callable) -> str:
        try:
            arguments = schema.model_validate(values, strict=True)
            data, warnings = function(arguments)
            return ToolResult(
                ok=True, tool=name, data=data, warnings=warnings, error=None
            ).model_dump_json()
        except ValidationError:
            raise ToolException(invalid_arguments(name)) from None
        except DocumentError as error:
            warnings = []
            if error.possible_output is not None:
                operations.context.uncertain_outputs.append(error.possible_output)
                warnings.append(f"Possible partial output: output/{error.possible_output}; not a successful creation.")
            raise ToolException(failure(name, error.error, warnings)) from None
        except OSError as error:
            raise ToolException(failure(name, map_os_error(error).error)) from None

    @tool(args_schema=SearchArguments)
    def search_documents(query: str, scope: str, offset: int, limit: int) -> str:
        """Search supported input files by literal filename/text; results are discovery, not read citations."""
        return run("search_documents", SearchArguments, {
            "query": query, "scope": scope, "offset": offset, "limit": limit,
        }, operations.search)

    @tool(args_schema=ReadArguments)
    def read_document(path: str, start_line: int, max_lines: int) -> str:
        """Read bounded normalized lines from an input document and register an observed source reference."""
        return run("read_document", ReadArguments, {
            "path": path, "start_line": start_line, "max_lines": max_lines,
        }, operations.read)

    @tool(args_schema=CreateArguments)
    def create_document(filename: str, kind: str, content: str, source_ids: list[str]) -> str:
        """Create a new local report or unsent email draft; never overwrite an existing file."""
        return run("create_document", CreateArguments, {
            "filename": filename, "kind": kind, "content": content, "source_ids": source_ids,
        }, operations.create)

    return tuple(
        StrictStructuredTool(
            name=wrapped.name, description=wrapped.description, func=wrapped.func,
            args_schema=wrapped.args_schema,
            handle_tool_error=lambda error: str(error),
            handle_validation_error=lambda error, name=wrapped.name: invalid_arguments(name),
        )
        for wrapped in (search_documents, read_document, create_document)
    )
