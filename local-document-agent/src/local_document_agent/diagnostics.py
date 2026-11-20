"""Bounded local diagnostics: deliberately no payload/message/body logging API."""

import json
import logging
import platform
import re
import traceback
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import __version__
from .filesystem import check_components


class DiagnosticStartupError(ValueError):
    pass


class SafeRotatingHandler(RotatingFileHandler):
    def handleError(self, record: logging.LogRecord) -> None:
        # Never dump raw logging internals/records on stderr.
        raise OSError("Diagnostic log write failed.")


class DiagnosticLog:
    """1 MiB current log plus three backups; credentials and content never enter."""

    def __init__(self, app_root: Path, *, max_bytes: int = 1024 * 1024) -> None:
        self.failed = False
        try:
            root = app_root.resolve(strict=True)
            check_components(root)
            directory = root / ".logs"
            if directory.exists() or directory.is_symlink():
                check_components(directory)
            directory.mkdir(exist_ok=True)
            self.path = directory / "errors.log"
            for candidate in [self.path, *(directory / f"errors.log.{index}" for index in range(1, 4))]:
                if candidate.exists() or candidate.is_symlink():
                    check_components(candidate)
            handler = SafeRotatingHandler(
                self.path, maxBytes=max_bytes, backupCount=3, encoding="utf-8",
            )
            handler.setFormatter(logging.Formatter("%(message)s"))
            self._logger = logging.Logger("local_document_agent.diagnostics", logging.WARNING)
            self._logger.propagate = False
            self._logger.addHandler(handler)
            self._handler = handler
        except Exception:
            raise DiagnosticStartupError("Cannot open the app-local diagnostic log; check .logs permissions.") from None

    def record(
        self, phase: str, code: str, *, session_id: str | None = None,
        tool: str | None = None, exception: BaseException | None = None,
    ) -> None:
        """Only allowlisted metadata. Never pass exception prose, locals, or source lines."""
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "application_version": __version__,
            "python_version": platform.python_version(),
            "phase": phase if phase in ("startup", "turn", "tool", "shutdown", "cli") else "unknown",
            "code": code if re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", code) else "UNCLASSIFIED_ERROR",
        }
        if session_id and re.fullmatch(r"[a-f0-9]{32}", session_id):
            event["session_id"] = session_id
        if tool:
            event["tool"] = tool if tool in ("search_documents", "read_document", "create_document") else "unknown"
        if exception is not None:
            kind = type(exception).__name__
            event["exception_type"] = kind if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,79}", kind) else "Exception"
            event["frames"] = [
                {"file": Path(frame.filename).name, "line": frame.lineno, "function": frame.name}
                for frame in traceback.extract_tb(exception.__traceback__)[-8:]
            ]
        try:
            self._logger.warning(json.dumps(event, ensure_ascii=True, separators=(",", ":")))
            self._handler.flush()
        except (OSError, ValueError):
            self.failed = True

    def close(self) -> None:
        try:
            self._handler.close()
        except (OSError, ValueError):
            self.failed = True
