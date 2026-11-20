"""Separate one-worker loopback HTTP command; help never loads configuration."""

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Authenticated Harbor-only local document agent HTTP service.")
    parser.add_argument("--app-root", type=Path, default=Path(__file__).resolve().parents[2],
                        help="Explicit app-local configuration directory.")
    parser.add_argument("--port", type=int, default=7310, help="Loopback TCP port (default: 7310).")
    arguments = parser.parse_args(argv)
    if not 1 <= arguments.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    from .config import ConfigurationError
    from .diagnostics import DiagnosticLog, DiagnosticStartupError
    from .http_config import load_adapter_settings

    diagnostics = None
    try:
        settings = load_adapter_settings(arguments.app_root)
        import uvicorn
        from .http_adapter import create_app

        diagnostics = DiagnosticLog(arguments.app_root)
        app = create_app(settings, diagnostics=diagnostics)
        # No request/header/body logs or raw exception traces in server logs.
        uvicorn.run(
            app, host="127.0.0.1", port=arguments.port, workers=1, reload=False,
            access_log=False, log_config=None, log_level="critical",
            timeout_graceful_shutdown=10,
        )
        return 1 if app.state.runs.shutdown_timed_out else 0
    except (ConfigurationError, DiagnosticStartupError, OSError, ValueError):
        print("HTTP startup failed: require a distinct adapter token, valid app-local settings, and an available loopback port.", file=sys.stderr)
        return 2
    finally:
        if diagnostics:
            if diagnostics.failed:
                print("Warning: sanitized diagnostics could not be saved.", file=sys.stderr)
            diagnostics.close()


if __name__ == "__main__":
    raise SystemExit(main())
