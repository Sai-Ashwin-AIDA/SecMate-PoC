import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";

export const PAGE_ERROR_EVENT = "secmate:page-error";

export class PageBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }

  componentDidCatch(error: unknown, _info: ErrorInfo) {
    // Observable local diagnostics without exporting exception text, component
    // stacks, chunk URLs, query parameters or user/model evidence.
    let cause = error;
    let code = "PAGE_RENDER";
    for (let depth = 0; depth < 4 && cause && typeof cause === "object"; depth += 1) {
      const detail = cause as { message?: unknown; cause?: unknown };
      if (typeof detail.message === "string" && /dynamically imported module|module script|loading chunk|chunkloaderror/i.test(detail.message)) {
        code = "CHUNK_LOAD";
        break;
      }
      cause = detail.cause;
    }
    const route = ["/dashboard", "/targets", "/assessments", "/assessments/chatmate", "/findings", "/reports", "/settings"].includes(window.location.pathname)
      ? window.location.pathname : "/unknown";
    window.dispatchEvent(new CustomEvent(PAGE_ERROR_EVENT, { detail: { code, route } }));
  }

  render() {
    return this.state.failed ? <section className="inline-error" role="alert">
      <h2>This page could not load</h2><p>Reload to try again. Saved runs are retained.</p>
      <button className="secondary-action" type="button" onClick={() => window.location.reload()}>Reload page</button>
    </section> : this.props.children;
  }
}
