import { useState } from "react";

const PREVIEW_LENGTH = 600;

export function ChatMatePromptPreview({ prompt, compare }: { prompt: string; compare: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const shortened = prompt.length > PREVIEW_LENGTH && !compare && !expanded;
  return <details open={compare}>
    <summary>{shortened ? "Attack prompt preview" : "Exact attack prompt"}</summary>
    <pre>{shortened ? `${prompt.slice(0, PREVIEW_LENGTH)}…` : prompt}</pre>
    {shortened && <small>Preview · {PREVIEW_LENGTH} of {prompt.length.toLocaleString()} characters</small>}
    {prompt.length > PREVIEW_LENGTH && !compare && <button className="chatmate-tertiary-action" type="button" onClick={() => setExpanded((value) => !value)}>{expanded ? "Show preview" : "Show full prompt"}</button>}
  </details>;
}
