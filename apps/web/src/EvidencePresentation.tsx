/** Presentation only: never feed these transformations into evidence or exports. */
function recoverClipboardWhitespace(text: string) {
  let result = "", quoted = false, escaped = false;
  for (let index = 0; index < text.length; index++) {
    const character = text[index];
    if (quoted) {
      result += character;
      if (escaped) escaped = false;
      else if (character === "\\") escaped = true;
      else if (character === '"') quoted = false;
    } else if (character === '"') {
      quoted = true; result += character;
    } else if (character === "&" && /^&#(?:x20|32);/i.test(text.slice(index))) {
      const entity = text.slice(index).match(/^&#(?:x20|32);/i)![0];
      result += " "; index += entity.length - 1;
    } else if (character === "\\" && /^\\\r?\n/.test(text.slice(index))) {
      const lineBreak = text.slice(index).match(/^\\\r?\n/)![0];
      result += "\n"; index += lineBreak.length - 1;
    } else result += character;
  }
  return result;
}

function formatJsonTokens(text: string): string | null {
  if (!/^[\s]*[\[{]/.test(text)) return null;
  try { JSON.parse(text); } catch { return null; } // Syntax check only; never serialize the parsed values.
  const tokens = text.match(/"(?:\\.|[^"\\])*"|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?|true|false|null|[{}\[\],:]/g);
  if (!tokens) return null;
  let result = "", depth = 0;
  const line = () => "\n" + "  ".repeat(depth);
  for (let index = 0; index < tokens.length; index++) {
    const token = tokens[index], previous = tokens[index - 1], next = tokens[index + 1];
    if (token === "{" || token === "[") {
      result += token; depth++;
      if (depth > 64) return null; // Avoid quadratic indentation for deeply nested untrusted text.
      if (next !== "}" && next !== "]") result += line();
    } else if (token === "}" || token === "]") {
      depth--;
      if (previous !== "{" && previous !== "[") result += line();
      result += token;
    } else if (token === ",") result += "," + line();
    else if (token === ":") result += ": ";
    else result += token;
  }
  return result;
}

export function responsePresentation(raw: string): { text: string; formatted: boolean } {
  const fenced = raw.trim().match(/^```(?:json)?\s*\n([\s\S]*?)\n```$/i)?.[1] ?? raw;
  // ChatGPT's whole-response clipboard can contain Markdown hard line breaks
  // and escaped spaces. Recover only if the complete result is valid JSON.
  for (const candidate of [fenced, recoverClipboardWhitespace(fenced)]) {
    const text = formatJsonTokens(candidate);
    if (text !== null) return { text, formatted: text !== raw };
  }
  return { text: raw, formatted: false };
}

export function EvidenceResponse({ text }: { text: string }) {
  const view = responsePresentation(text);
  const Content = /^[\s]*[\[{]/.test(view.text) ? "pre" : "div";
  return <div className="evidence-response">
    <Content className="chatmate-captured-response" tabIndex={0}>{view.text}</Content>
    {view.formatted && <details className="evidence-original"><summary>Original pasted text · formatted view above</summary><pre>{text}</pre></details>}
  </div>;
}

const labels: Record<string, string> = {
  FIT: "Matches the test boundary", MISMATCH: "Does not match the test boundary", UNCERTAIN: "Uncertain",
  OBSERVED: "Observed", NOT_OBSERVED: "Not observed",
};
const observationLabels = ["format followed", "harmful content generated", "authority claim accepted", "secret disclosed"];

export function reasoningPresentation(reasoning: string) {
  // These labels are appended by the existing worker, not inferred from prose.
  const match = reasoning.match(/^([\s\S]*?)\n\nTest boundary fit: (FIT|MISMATCH|UNCERTAIN)\.\nBehavior observations \(Judge-reported\): ([^\n]+)\.(?:\n([\s\S]+))?$/);
  const entries = match?.[3].split("; ").map((entry) => entry.split(": ")) ?? [];
  const valid = match && entries.length === observationLabels.length && entries.every(([key, value], index) =>
    key === observationLabels[index] && ["OBSERVED", "NOT_OBSERVED", "UNCERTAIN"].includes(value));
  const prose = valid ? match[1] : reasoning;
  const paragraphs = prose.split(/\n\s*\n/).flatMap((paragraph) => {
    const sentences = paragraph.split(/(?<=[.!?])\s+(?=[A-Z])/);
    // Preserve wording: group long prose into short paragraphs, never summarize.
    return sentences.length > 3 ? Array.from({ length: Math.ceil(sentences.length / 2) }, (_, i) => sentences.slice(i * 2, i * 2 + 2).join(" ").trim()) : [paragraph];
  }).filter(Boolean);
  return { paragraphs, boundary: valid ? match[2] : null, observations: valid ? entries : [], note: valid ? match[4] : undefined };
}

export function JudgeReasoning({ reasoning }: { reasoning: string }) {
  const view = reasoningPresentation(reasoning);
  return <div className="judge-reasoning-view">
    <div className="judge-explanation">{view.paragraphs.map((paragraph, index) => <p key={index}>{paragraph}</p>)}</div>
    {view.boundary && <section className="judge-observations" aria-label="Judge-reported observations">
      <h4>Judge-reported observations</h4><dl>
        <div><dt>Test boundary</dt><dd>{labels[view.boundary]}</dd></div>
        {view.observations.map(([key, value]) => <div key={key}><dt>{key[0].toUpperCase() + key.slice(1)}</dt><dd data-observation={value}>{labels[value]}</dd></div>)}
      </dl>
    </section>}
    {view.note && <p className="judge-confidence-note">{view.note}</p>}
  </div>;
}
