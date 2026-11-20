"""Explicit, bounded live demonstrations using fictional inputs, never model fakes."""

import argparse
import asyncio
import hashlib
import json
import uuid
from pathlib import Path

from local_document_agent.agent import DocumentAssistant
from local_document_agent.cli import render_result
from local_document_agent.config import ConfigurationError, load_configuration
from local_document_agent.diagnostics import DiagnosticLog
from local_document_agent.filesystem import FilesystemRoots
from local_document_agent.prompts import TRANSMISSION_NOTICE
from local_document_agent.provider import create_provider

APP_ROOT = Path(__file__).resolve().parents[1]


async def run() -> int:
    # Deliberately use only this app's private file, not ambient/parent keys.
    configuration = load_configuration(APP_ROOT, environment={})
    configuration.require_inference_ready()
    log = DiagnosticLog(APP_ROOT)
    directory = APP_ROOT / ".cache" / f"live-demo-{uuid.uuid4().hex}"
    source, output = directory / "input", directory / "output"
    source.mkdir(parents=True)
    output.mkdir()
    for example in (APP_ROOT / "examples" / "input").iterdir():
        with (source / example.name).open("xb") as stream:
            stream.write(example.read_bytes())
    configuration = configuration.model_copy(update={"input_dir": source, "output_dir": output})
    try:
        provider = create_provider(configuration)
    except Exception:
        log.close()
        raise
    roots = FilesystemRoots(source, output)
    assistant = DocumentAssistant(
        configuration, provider.model, roots=roots, diagnostics=log,
        observer=lambda event: print(f"[tool] {event.name} -> {event.summary}"),
    )
    demos = [
        ("summary", "Summarize launch-notes.md and list the open decisions. Include source references.",
         {"launch-notes.md"}, None),
        ("email_reply",
         "Read vendor-request.eml and draft a polite reply confirming Tuesday, 24 November 2026. "
         "Do not invent a meeting time. Save it as vendor-reply.md. Do not send it. Include source references.",
         {"vendor-request.eml"}, "vendor-reply.md"),
        ("report",
         "Create a short launch status report from launch-notes.md and budget.txt. "
         "Save launch-status.md with a source list.",
         {"launch-notes.md", "budget.txt"}, "launch-status.md"),
    ]
    outcomes = []
    stop = False
    print(TRANSMISSION_NOTICE)
    print("Only fictional example documents are used. Three turns; configured limits apply; no retries.")
    try:
        for name, prompt, required, expected_file in demos:
            if stop:
                outcomes.append({"task": name, "status": "not_run_after_error"})
                continue
            assistant.new_session()
            print("\nyou> " + prompt)
            result = await assistant.chat(prompt)
            render_result(result, roots, print)
            reads = {item.path for item in result.sources}
            created = {item.path: item for item in result.created_files}
            file_verified = expected_file is None
            if expected_file in created:
                actual = (output / expected_file).read_bytes()
                file_verified = hashlib.sha256(actual).hexdigest() == created[expected_file].sha256
                if name == "email_reply":
                    file_verified = file_verified and actual.startswith("EMAIL DRAFT — NOT SENT".encode("utf-8"))
            citations = all(f"[{item.source_id}]" in result.answer for item in result.sources) if name == "summary" else True
            observed_ok = (
                result.status == "completed" and required <= reads and file_verified
                and not result.unverified_source_ids and citations
            )
            outcomes.append({
                "task": name, "status": result.status, "observed_workflow_ok": observed_ok,
                "read_paths": sorted(reads), "created_paths": sorted(created),
                "observed_tool_calls": len(result.tool_events),
                "error_code": result.error.code if result.error else None,
                "uncertain_outputs": list(result.uncertain_outputs),
            })
            stop = result.status != "completed"
    finally:
        try:
            await provider.aclose()
        except Exception as error:
            log.record("shutdown", "PROVIDER_CLOSE_ERROR", exception=error)
            raise
        finally:
            log.close()
            # No key, model prose, prompts, headers, bodies or raw provider errors.
            with (directory / "outcomes.json").open("x", encoding="utf-8") as stream:
                json.dump(outcomes, stream, indent=2)
            print("\nObserved-outcome record: " + str(directory / "outcomes.json"))
    return 0 if len(outcomes) == 3 and all(item.get("observed_workflow_ok") for item in outcomes) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Live document-agent demonstrations with fictional local files.")
    parser.add_argument("--run-live", action="store_true", help="Explicitly authorize these inference requests.")
    arguments = parser.parse_args()
    if not arguments.run_live:
        parser.error("Pass --run-live only after private key setup and transmission consent.")
    try:
        return asyncio.run(run())
    except ConfigurationError as error:
        log = DiagnosticLog(APP_ROOT)
        log.record("startup", "CONFIGURATION_ERROR", exception=error)
        log.close()
        print("Configuration not ready: " + str(error))
        return 2
    except KeyboardInterrupt:
        print("Live demonstrations interrupted.")
        return 1
    except Exception as error:
        try:
            log = DiagnosticLog(APP_ROOT)
            log.record("cli", "LIVE_DEMO_ERROR", exception=error)
            log.close()
        except Exception:
            print("Diagnostic logging is unavailable.")
        print("Live demonstration failed; inspect .logs/errors.log for sanitized diagnostics.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
