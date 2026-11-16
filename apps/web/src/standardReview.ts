import type { StandardReviewView } from "./modelConnectivityService";

export async function sha256Text(value: string) {
  const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return [...new Uint8Array(bytes)].map(value => value.toString(16).padStart(2, "0")).join("");
}

export function canonicalJson(value: unknown): string {
  return JSON.stringify(sorted(value)).replace(/[\u0080-\uFFFF]/g, character => {
    const code = character.charCodeAt(0);
    return `\\u${code.toString(16).padStart(4, "0")}`;
  });
}

export const canonicalSha256 = (value: unknown) => sha256Text(canonicalJson(value));

export async function validateStandardReview(runId: string, view: StandardReviewView) {
  if (view.run_id !== runId) throw new Error("Review response does not match the selected assessment.");
  if (view.status !== "COMPLETED") return view;
  const review = view.review;
  if (!review || !view.review_canonical || !view.review_sha256
      || await sha256Text(view.review_canonical) !== view.review_sha256
      || JSON.stringify(sorted(JSON.parse(view.review_canonical))) !== JSON.stringify(sorted(review))
      || review.run_id !== runId || review.review_id !== view.review_id
      || !["socmate-standard-review-v1", "socmate-standard-review-v2", "secmate-target-standard-review-v1"].includes(review.schema_version) || review.model !== "qwen/qwen3.8-27b"
      || review.model_profile_id !== "groq-qwen-critic" || !Array.isArray(review.recommendations) || review.recommendations.length > 2
      || (review.schema_version !== "socmate-standard-review-v1" && review.recommendations.length === 0)
      || ![review.input_sha256, review.source_audit_sha256, review.assessment_spec_sha256].every(value => /^[a-f0-9]{64}$/.test(value))
      || !review.source_path_id
      || new Set(review.recommendations.map(item => item.attack_profile_id)).size !== review.recommendations.length
      || review.recommendations.some(item => !item.attack_profile_id || !Number.isInteger(item.priority) || item.priority < 0 || item.priority > 100 || item.priority % 5 !== 0)) {
    throw new Error("Saved Standard review failed verification.");
  }
  return view;
}

function sorted(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sorted);
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([key, child]) => [key, sorted(child)]));
  return value;
}

export function operationKey(operation: string) {
  const storageKey = `secmate.standard.operation.${operation}`;
  let key = window.localStorage.getItem(storageKey);
  if (!key) { key = crypto.randomUUID(); window.localStorage.setItem(storageKey, key); }
  return { key, clear: () => window.localStorage.removeItem(storageKey) };
}
