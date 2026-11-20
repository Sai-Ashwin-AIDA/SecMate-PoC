"""Small terminal interface; no dummy or fallback production provider mode."""

import argparse
import asyncio
import sys
import unicodedata
from pathlib import Path
from typing import Callable

from .agent import DocumentAssistant, ToolActivity, TurnResult
from .config import ConfigurationError, load_configuration
from .contracts import DocumentError
from .filesystem import FilesystemRoots
from .prompts import TRANSMISSION_NOTICE
from .provider import create_provider


def safe_terminal(value: str) -> str:
    return "".join(
        character if character in "\n\t" or not unicodedata.category(character).startswith("C")
        else character.encode("unicode_escape").decode("ascii")
        for character in value
    )


def render_result(result: TurnResult, roots: FilesystemRoots, write: Callable[[str], None]) -> None:
    if result.answer:
        write(safe_terminal(result.answer))
    if result.error is not None:
        write(f"[{result.error.code}] {result.error.message}")
        write("Incomplete conversation turn was not retained.")
    if result.sources:
        write("Files read this turn:")
        for source in result.sources:
            write("  " + safe_terminal(source.reference()))
    if result.retained_sources:
        write("Earlier observed sources referenced:")
        for source in result.retained_sources:
            write("  " + safe_terminal(source.reference()))
    if result.created_files:
        write("Created:")
        for document in result.created_files:
            write("  " + safe_terminal(str(roots.output / document.path)))
            if document.not_sent:
                write("  Email draft — not sent")
    else:
        write("No file creation was observed.")
    for filename in result.uncertain_outputs:
        write("Possible partial file (not a confirmed creation): " + safe_terminal(str(roots.output / filename)))
    for source_id in result.unverified_source_ids:
        write(f"[{source_id}] is an unverified source reference.")


async def run_cli(
    assistant: DocumentAssistant, *,
    read: Callable[[str], str] = input,
    write: Callable[[str], None] = print,
) -> int:
    """Injectable terminal boundary; this function never fabricates model replies."""
    write(TRANSMISSION_NOTICE)
    write("Commands: /new, /help, /exit. Supported input: .txt, .md, plain-text .eml.")

    def activity(event: ToolActivity) -> None:
        write(safe_terminal(f"[tool] {event.name} → {event.summary}"))

    assistant.observer = activity
    while True:
        try:
            message = read("you> ")
        except (EOFError, KeyboardInterrupt):
            return 0
        if message == "/exit":
            return 0
        if message == "/new":
            assistant.new_session()
            write("New conversation. History cleared; local files are unchanged.")
        elif message == "/help":
            write("Chat to search/read documents and create reports or unsent drafts. /new resets; /exit exits.")
        elif message.startswith("/"):
            write("Unknown command. Use /help.")
        else:
            result = await assistant.chat(message)
            render_result(result, assistant.roots, write)


async def _start(app_root: Path) -> int:
    configuration = load_configuration(app_root)
    configuration.require_inference_ready()
    roots = FilesystemRoots(configuration.input_dir, configuration.output_dir)
    provider = create_provider(configuration)
    try:
        return await run_cli(DocumentAssistant(configuration, provider.model, roots=roots))
    finally:
        await provider.aclose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Personal local-document assistant; drafts are never sent.")
    parser.add_argument(
        "--app-root", type=Path, default=Path(__file__).resolve().parents[2],
        help="Application directory containing the explicit .env (defaults to this source installation).",
    )
    arguments = parser.parse_args(argv)
    try:
        return asyncio.run(_start(arguments.app_root))
    except (ConfigurationError, DocumentError) as error:
        print(f"Startup error: {error}", file=sys.stderr)
        return 2
    except OSError:
        print("Startup error: application configuration or local roots are unavailable.", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 0
    except Exception:
        print("Startup error: initialization or shutdown failed; no automatic fallback was attempted.", file=sys.stderr)
        return 2
