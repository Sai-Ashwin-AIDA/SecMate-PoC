import type { ChatMateRunRecord, ChatMateCriticReview } from "./chatmateService";
import { chatMateCandidate, parseChatMateAudit } from "./chatmateProjections";
import { chatMateTextHash, parseChatMateCriticReview, legacyCriticWarning, effectiveCriticRecommendation } from "./chatmateCritic";
import { assessmentDisplayName, targetDisplayName } from "./displayLabels";
import type { StandardReview, StandardReviewView, LinkedAssessmentContext } from "./modelConnectivityService";
import { validateStandardReview } from "./standardReview";

export type ReportSource = "ChatMate" | "SocMate";
export type ReportSelection = { source: ReportSource; runId: string };
export type ReportOutcome = "Resisted" | "Compromised" | "Inconclusive" | "Failed" | "Cancelled" | "Unavailable";
export type ReportPathResult = { pathId: string; number: number; method: string; outcome: string;
  score?: number; confidence?: number; rationale: string; scoreNote?: string };
export type ManagementReportItem = ReportSelection & {
  method: string; target: string; completed: string | null; outcome: ReportOutcome;
  evidenceStatus: "Verified" | "Unavailable" | "Invalid";
  summary: string; originalAvailable: boolean; score?: number; confidence?: number;
  rationales: string[]; citations: string[]; actions: string[];
  pathResults?: ReportPathResult[];
  standardReview?: { status: "Verified" | "Unavailable" | "Invalid"; review?: StandardReview; sha256?: string; notice?: string };
  socmateLink?: Omit<LinkedAssessmentContext, "redacted_parent_context"> & { contextSha256: string };
  targetScope?: { id: string; version: string; risk: string };
  unsupported?: boolean;
  unsupportedReason?: string;
  exchanges: { label: string; prompt: string; response: string; tools?: string }[];
  appendix: Record<string, string | null>;
  lineage?: { parentRunId: string | null; reviewId: string | null; viaReviewId: string | null;
    profile: string; specId: string; specHash: string; context: Record<string, unknown> | null };
  critic?: { status: "Verified" | "Invalid" | "Unavailable"; review?: ChatMateCriticReview; notice?: string };
};
export type ReportNotes = { reviewer: string; date: string; decision: string; notes: string };
const contextFields = ["parent_run_id", "critic_review_id", "source_evaluation_id", "source_candidate_sha256",
  "source_correlation_sha256", "source_judge_sha256", "assessment_spec_sha256", "recommended_attack_profile_id",
  "objective", "expected_evidence", "recommendation_policy"];
const publicContext = (value: Record<string, unknown>) => Object.fromEntries(contextFields.filter((key) => Object.hasOwn(value, key)).map((key) => [key, value[key]]));
export const reportSelectionKey = (item: ReportSelection) => `${item.source}:${item.runId}`;
export const reportSummary: Record<ReportOutcome, string> = {
  Resisted: "No violation observed.", Compromised: "Potential violation observed.",
  Inconclusive: "Evidence inconclusive.", Failed: "Run did not complete.",
  Cancelled: "Run did not complete.", Unavailable: "Evidence unavailable.",
};

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Validation failed.");
  return value as Record<string, unknown>;
}
function list(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) throw new Error("Validation failed.");
  return value.map(object);
}
const text = (value: unknown, fallback = "") => typeof value === "string" ? value : fallback;
function outcome(status: unknown, result: unknown): ReportOutcome {
  if (status === "CANCELLED") return "Cancelled";
  if (status === "FAILED" || result === "ERROR") return "Failed";
  if (status !== "COMPLETED") return "Unavailable";
  if (result === "RESISTED") return "Resisted";
  if (result === "COMPROMISED") return "Compromised";
  if (result === "INCONCLUSIVE") return "Inconclusive";
  throw new Error("Validation failed.");
}
function missing(selection: ReportSelection, invalid = false): ManagementReportItem {
  return { ...selection, method: "—", target: selection.source, completed: null,
    outcome: "Unavailable", evidenceStatus: invalid ? "Invalid" : "Unavailable",
    summary: invalid ? "Validation failed." : "Evidence unavailable.", originalAvailable: false,
    rationales: [], citations: [], actions: [], exchanges: [], appendix: { "Run ID": selection.runId } };
}

async function normalizeChatMate(selection: ReportSelection, data: Record<string, unknown>): Promise<ManagementReportItem> {
  const run = data.run as ChatMateRunRecord;
  const selectedCandidate = chatMateCandidate(run);
  const result = outcome(run.status, run.final_status);
  const item: ManagementReportItem = { ...missing(selection), method: run.attack_method, target: "ChatMate",
    completed: run.completed_at, outcome: result, summary: reportSummary[result],
    appendix: { "Run ID": run.run_id, "Evaluation ID": run.evaluation_id,
       "Prompt SHA-256": run.selected_candidate_sha256, "Correlation SHA-256": run.manual_evidence?.correlation_sha256 ?? null,
       ...(selectedCandidate?.method_review ? { "Generation mode": selectedCandidate.generation_mode ?? null,
         "Requested method": selectedCandidate.attack_method, "Advisory method verdict": selectedCandidate.method_review.verdict,
         "Reviewer instruction version": selectedCandidate.method_review.reviewer_instruction_version,
         "Reviewer instruction SHA-256": selectedCandidate.method_review.reviewer_instruction_sha256 } : {}) } };
  if (data.audit == null) return ["Failed", "Cancelled", "Unavailable"].includes(result) ? item : { ...item, outcome: "Unavailable", summary: "Evidence unavailable." };
  const parsed = parseChatMateAudit(run, data.audit);
  item.evidenceStatus = "Verified";
  if (parsed.judge) {
    item.score = parsed.judge.deviation_score;
    item.confidence = parsed.judge.confidence;
    item.rationales = [parsed.judge.reasoning];
    item.citations = [...(parsed.judge.evidence_references ?? []), ...(parsed.judge.policy_references ?? [])];
  }
  const rawContext = run.follow_up_context;
  item.lineage = { parentRunId: run.parent_run_id ?? null, reviewId: run.critic_review_id ?? null,
    viaReviewId: run.follow_up_critic_review_id ?? null, profile: run.attack_profile_id,
    specId: text(run.candidate_batch?.assessment_spec.spec_id), specHash: text(run.candidate_batch?.provenance.assessment_spec_sha256),
    context: rawContext ? publicContext(rawContext) : null };
  if (run.parent_run_id) item.appendix["Recorded parent run"] = run.parent_run_id;
  if (data.original != null) {
    const original = object(data.original);
    const candidate = chatMateCandidate(run);
    if (original.run_id !== run.run_id || original.prompt !== candidate?.prompt
        || original.candidate_sha256 !== run.selected_candidate_sha256
        || original.correlation_sha256 !== run.manual_evidence?.correlation_sha256
        || await chatMateTextHash(text(original.prompt)) !== run.selected_candidate_sha256
        || (original.response_text !== null && (typeof original.response_text !== "string"
            || await chatMateTextHash(original.response_text) !== original.response_sha256))) throw new Error("Validation failed.");
    item.originalAvailable = true;
    item.exchanges = [{ label: "Selected exchange", prompt: text(original.prompt),
      response: original.response_text === null ? "Response could not be completed." : text(original.response_text) }];
    item.appendix["Response SHA-256"] = text(original.response_sha256) || null;
  }
  if (run.critic_status === "COMPLETED") {
    try {
      const review = await parseChatMateCriticReview(run, parsed.audit, data.critic);
      item.critic = { status: "Verified", review, notice: legacyCriticWarning(review) ?? undefined };
    } catch {
      item.critic = { status: "Invalid", notice: "Critic verification failed; Judge evidence remains independently verified." };
    }
  } else if (run.critic_status) {
    item.critic = { status: "Unavailable", notice: `Critic review ${run.critic_status.toLowerCase()}; no verified advisory available.` };
  }
  return item;
}

function validateSocAudit(runId: string, result: unknown, value: unknown) {
  const audit = object(value);
  if (audit.run_id !== runId) throw new Error("Validation failed.");
  const parts = ["manifest", "evidence", "summary"].map((key) => object(audit[key]));
  if (!text(parts[0].run_id) || parts.some((part) => part.run_id !== parts[0].run_id)
      || parts[2].final_status !== result) throw new Error("Validation failed.");
  // Native DeepTeam output need not have a top-level run_id. Match its path
  // identities to the canonical evidence, as the API's verified reader does.
  const risk = object(audit.deepteam_risk);
  if (risk.run_id != null && risk.run_id !== parts[0].run_id) throw new Error("Validation failed.");
  const ids = list(parts[1].paths).map(path => path.path_id);
  if (ids.some(id => typeof id !== "string" || !id) || new Set(ids).size !== ids.length
      || !equalPathIds(ids, list(risk.paths).map(path => path.path_id))) throw new Error("Validation failed.");
  return audit;
}
const equalPathIds = (left: unknown[], right: unknown[]) => left.length === right.length && left.every((id, index) => id === right[index]);
async function normalizeSocMate(selection: ReportSelection, data: Record<string, unknown>): Promise<ManagementReportItem> {
  const run = object(data.run);
  const result = outcome(run.status, run.final_status);
  const targetId = text(run.target_profile_id, "synthetic-socmate-tier1");
  const item: ManagementReportItem = { ...missing(selection), method: assessmentDisplayName(text(run.attack)),
    target: targetDisplayName(targetId), completed: text(run.completed_at) || null,
    outcome: result, summary: reportSummary[result], appendix: { "Run ID": selection.runId,
      "Completed": text(run.completed_at) || null,
      "Scenario": text(run.scenario), "Scenario version": text(run.scenario_version),
      "Target profile": targetId, "Target version": text(run.target_profile_version),
      "Method ID": text(run.attack_profile_id), "Risk ID": text(run.vulnerability_profile_id),
       "Coverage": run.execution_mode === "ADAPTIVE" ? "Expanded" : "Standard",
      "Path limit": run.max_paths == null ? null : String(run.max_paths),
      "Token budget": run.max_total_tokens == null ? null : String(run.max_total_tokens),
       "Vulnerability": text(run.vulnerability),
       "Selection admission": text(run.selection_admission) || null,
       "Execution capability": text(run.execution_capability) || null,
       "Capability code": text(run.execution_capability_code) || null } };
  if (run.execution_capability === "UNSUPPORTED") {
    item.unsupported = true;
    item.unsupportedReason = text(run.execution_capability_reason, text(run.error_message, "The selected combination is unsupported for this target."));
    item.summary = item.unsupportedReason;
  }
  if (data.audit == null) return ["Failed", "Cancelled", "Unavailable"].includes(result) ? item : { ...item, outcome: "Unavailable", summary: "Evidence unavailable." };
  const audit = validateSocAudit(selection.runId, run.final_status, data.audit);
  const provenance = object(object(audit.manifest).execution_provenance ?? {});
  if (item.unsupported) item.appendix["Execution mode"] = "Not executed / unsupported";
  else if (provenance.execution_mode === "BASELINE_UNENHANCED"
      && provenance.enhancement_applied === false) {
    item.appendix["Execution mode"] = "Baseline / unenhanced";
  } else item.appendix["Execution mode"] = "DeepTeam transformed";
  const summary = object(audit.summary);
  const budget = object(summary.budget ?? {});
  item.appendix["AI requests"] = typeof budget.provider_calls_attempted === "number" ? String(budget.provider_calls_attempted) : null;
  item.appendix["Captured turns"] = typeof summary.turns === "number" ? String(summary.turns) : null;
  const evidence = object(audit.evidence);
  const paths = list(evidence.paths);
  const reviews = list(evidence.review_results);
  if (!paths.length) throw new Error("Validation failed.");
  if (new Set(reviews.map(review => review.path_id)).size !== reviews.length) throw new Error("Validation failed.");
  item.pathResults = [];
  for (const review of reviews) {
    if (!paths.some((path) => path.path_id === review.path_id)) throw new Error("Validation failed.");
    if (review.target_evaluation != null) {
      const judge = object(review.target_evaluation);
      if (typeof judge.deviation_score !== "number" || !Number.isInteger(judge.deviation_score)
          || judge.deviation_score < 0 || judge.deviation_score > 100 || typeof judge.confidence !== "number"
          || !Number.isFinite(judge.confidence) || judge.confidence < 0 || judge.confidence > 1) throw new Error("Validation failed.");
      // Multiple paths have independent rubrics; never average or invent a shared score.
      if (reviews.length === 1) { item.score = judge.deviation_score; item.confidence = judge.confidence; }
      if (text(judge.reasoning)) item.rationales.push(text(judge.reasoning));
      for (const field of ["evidence_references", "policy_references"]) {
        if (Array.isArray(judge[field])) item.citations.push(...judge[field].filter((ref): ref is string => typeof ref === "string"));
      }
    }
    if (text(review.reason)) item.rationales.push(text(review.reason));
  }
  item.pathResults = paths.map((path, index) => {
    const review = reviews.find(value => value.path_id === path.path_id);
    const judge = review?.target_evaluation == null ? null : object(review.target_evaluation);
    return { pathId: text(path.path_id), number: index + 1, method: assessmentDisplayName(text(path.attack_method, item.method)),
      outcome: item.unsupported ? "Not evaluated" : text(path.status, text(review?.decision, "Not recorded")),
      ...(judge ? { score: judge.deviation_score as number, confidence: judge.confidence as number } : {}),
      rationale: text(judge?.reasoning, text(review?.reason)),
      ...(!judge ? { scoreNote: item.unsupported
        ? "Unsupported capability: no Judge score or confidence was recorded."
        : "No Judge score was recorded for this path. Its outcome may be determined by policy checks or incomplete evaluation." } : {}) };
  });
  // A single score is meaningful only for a single path, never an average or
  // the score of whichever path happened to finish last.
  if (paths.length !== 1) { delete item.score; delete item.confidence; }
  item.evidenceStatus = "Verified";
  item.targetScope = { id: text(run.target_profile_id), version: text(run.target_profile_version), risk: text(run.vulnerability_profile_id) };
  if (data.standard_review != null) {
    try {
      const view = await validateStandardReview(selection.runId, data.standard_review as StandardReviewView);
      if (view.status === "COMPLETED" && view.review) {
        if (view.review_id !== run.critic_review_id || view.review_sha256 !== run.critic_review_sha256) throw new Error("Review snapshot mismatch");
        item.standardReview = { status: "Verified", review: view.review, sha256: view.review_sha256 };
      } else item.standardReview = { status: "Unavailable", notice: view.message ?? `Review ${view.status.toLowerCase()}.` };
    } catch {
      item.standardReview = { status: "Invalid", notice: "Standard advisory verification failed. The assessment evidence remains independently verified." };
    }
  }
  if (run.linked_context != null) {
    const context = object(run.linked_context);
    const contextHash = text(object(object(audit.manifest).prompt_provenance_hashes).linked_context_sha256);
    if (!/^[a-f0-9]{64}$/.test(contextHash) || !["socmate-linked-assessment-v1", "secmate-target-linked-assessment-v1"].includes(text(context.schema_version))
        || context.parent_run_id === selection.runId || context.target_profile_id !== run.target_profile_id
        || context.target_profile_version !== run.target_profile_version || context.vulnerability_profile_id !== run.vulnerability_profile_id
        || context.attack_profile_id !== run.attack_profile_id
        || context.schema_version === "secmate-target-linked-assessment-v1" && (context.scenario_id !== run.scenario
          || context.scenario_version !== run.scenario_version || !/^[a-f0-9]{64}$/.test(text(context.redacted_parent_context_sha256)))) throw new Error("Linked scope validation failed.");
    const { redacted_parent_context: _unused, ...metadata } = context;
    item.socmateLink = { ...metadata, contextSha256: contextHash } as ManagementReportItem["socmateLink"];
    item.appendix["Parent assessment"] = text(context.parent_run_id);
    item.appendix["Parent path"] = text(context.parent_path_id);
    item.appendix["Source Standard review"] = text(context.review_id);
    item.appendix["Linked context SHA-256"] = contextHash;
  }
  if (data.original != null) {
    const original = validateSocAudit(selection.runId, run.final_status, data.original);
    const originalPaths = list(object(original.evidence).paths);
    if (originalPaths.length !== paths.length || originalPaths.some((path, index) => path.path_id !== paths[index].path_id)) throw new Error("Validation failed.");
    item.exchanges = originalPaths.flatMap((path, pathIndex) => list(path.turns).map((turn, turnIndex) => ({
      label: `Path ${pathIndex + 1} · Turn ${turnIndex + 1}`,
      prompt: text(turn.probe), response: text(turn.target_response),
      ...([turn.tool_attempts, turn.retrieval_evidence, turn.retrieval_decisions].some(Boolean) ? {
        tools: JSON.stringify({ tool_attempts: turn.tool_attempts, retrieval_evidence: turn.retrieval_evidence, retrieval_decisions: turn.retrieval_decisions }, null, 2),
      } : {}),
    })));
    item.originalAvailable = true;
  }
  return item;
}

export async function loadManagementReport(selections: ReportSelection[], signal?: AbortSignal): Promise<ManagementReportItem[]> {
  const unique = [...new Map(selections.map((item) => [reportSelectionKey(item), item])).values()];
  const results: ManagementReportItem[] = [];
  // Bounded sequential reads preserve selection order and avoid unbounded fanout.
  for (const selection of unique) {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    let invalid = false;
    try {
      const resource = selection.source === "ChatMate" ? "chatmate-runs" : "deepteam-runs";
      const base = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";
      const response = await fetch(`${base}/${resource}/${encodeURIComponent(selection.runId)}/report-data`, { signal, cache: "no-store" });
      invalid = response.status === 409 || response.status === 503;
      if (!response.ok) throw new Error("Evidence unavailable.");
      invalid = true;
      const data = object(await response.json());
      const sourceMatches = data.source === selection.source
        || selection.source === "SocMate" && data.source === "Synthetic ChatMate";
      if (!sourceMatches || object(data.run).run_id !== selection.runId) throw new Error("Validation failed.");
      results.push(selection.source === "ChatMate" ? await normalizeChatMate(selection, data) : await normalizeSocMate(selection, data));
    } catch (error) {
      if (signal?.aborted) throw error;
      results.push(missing(selection, invalid));
    }
  }
  return results;
}

export function managementReportBundle(title: string, generatedAt: string, items: ManagementReportItem[], notes: ReportNotes) {
  const selected = items.map((item) => item.lineage?.context ? { ...item, lineage: { ...item.lineage, context: publicContext(item.lineage.context) } } : item);
  const structure = assessmentChains(selected);
  const socmate = linkedSocmateChains(selected);
  return { exportType: "SECMATE_MANAGEMENT_REPORT", schemaVersion: selected.some(item => item.standardReview || item.socmateLink) ? "1.2" : "1.1", title, generatedAt,
    order: "SELECTION", chainOrder: "PARENT_BEFORE_FOLLOW_UP", items: selected,
    chains: structure.chains.map((chain) => ({ ...chain, stages: chain.stages.map((stage) => ({ source: stage.source, runId: stage.runId })) })),
    linkedSocmateAssessments: socmate.chains.map(chain => ({ ...chain, stages: chain.stages.map(stage => ({ source: stage.source, runId: stage.runId })) })),
    independentItems: socmate.independentItems.map((item) => ({ source: item.source, runId: item.runId })), review: notes };
}

export function linkedSocmateChains(items: ManagementReportItem[]) {
  const socmate = items.filter(item => item.source === "SocMate"), byId = new Map(socmate.map(item => [item.runId, item]));
  const parents = new Map<string, string>(), notices = new Map<string, string>();
  for (const child of socmate) {
    const link = child.socmateLink;
    if (!link) continue;
    const parent = byId.get(link.parent_run_id), review = parent?.standardReview;
    if (!parent) { notices.set(child.runId, "Parent not selected; linked provenance is only partially verified."); continue; }
    const valid = child.evidenceStatus === "Verified" && parent.evidenceStatus === "Verified" && review?.status === "Verified"
      && review.sha256 === link.review_sha256 && review.review?.review_id === link.review_id
      && review.review.source_audit_sha256 === link.source_audit_sha256 && review.review.assessment_spec_sha256 === link.assessment_spec_sha256
      && review.review.source_path_id === link.parent_path_id
      && Boolean(parent.targetScope?.id && child.targetScope?.id && parent.targetScope?.version && child.targetScope?.version && parent.targetScope?.risk && child.targetScope?.risk)
      && parent.targetScope?.id === child.targetScope?.id && parent.targetScope?.version === child.targetScope?.version && parent.targetScope?.risk === child.targetScope?.risk
      && review.review.recommendations.some(item => item.attack_profile_id === link.attack_profile_id && item.priority === link.priority);
    if (valid) parents.set(child.runId, parent.runId);
    else notices.set(child.runId, "Lineage conflict: linked recommendation, scope or evidence does not match.");
  }
  for (const item of socmate) {
    const seen = new Set<string>(); let id: string | undefined = item.runId;
    while (id && parents.has(id)) {
      if (seen.has(id)) { for (const cyclic of seen) { parents.delete(cyclic); notices.set(cyclic, "Lineage conflict: cyclic linked assessments."); } break; }
      seen.add(id); id = parents.get(id);
    }
  }
  const participating = new Set([...socmate.filter(item => item.socmateLink).map(item => item.runId), ...parents.values()]);
  const groups = new Map<string, { rootRunId: string; status: "Verified" | "Partial" | "Conflict"; notice?: string; stages: ManagementReportItem[] }>();
  for (const item of socmate.filter(item => participating.has(item.runId))) {
    let root = item.runId; while (parents.has(root)) root = parents.get(root)!;
    if (!groups.has(root)) groups.set(root, { rootRunId: root, status: "Verified", stages: [] });
    const group = groups.get(root)!; group.stages.push(item);
    if (notices.has(item.runId)) { group.notice = notices.get(item.runId); group.status = group.notice!.startsWith("Lineage conflict") ? "Conflict" : "Partial"; }
  }
  const depth = (item: ManagementReportItem) => { let count = 0, id = item.runId; while (parents.has(id)) { count++; id = parents.get(id)!; } return count; };
  for (const group of groups.values()) group.stages.sort((a, b) => depth(a) - depth(b));
  return { chains: [...groups.values()], independentItems: socmate.filter(item => !participating.has(item.runId)) };
}

export type AssessmentChain = { rootRunId: string; status: "Verified" | "Partial" | "Conflict";
  notice?: string; stages: ManagementReportItem[]; transitions: { parentRunId: string; childRunId: string; criticReviewId: string; policyAdjusted: boolean }[] };

function linked(parent: ManagementReportItem, child: ManagementReportItem) {
  const p = parent.lineage, c = child.lineage, context = c?.context, review = parent.critic?.review;
  if (!p || !c || !context || !review || parent.critic?.status !== "Verified"
      || parent.evidenceStatus !== "Verified" || child.evidenceStatus !== "Verified") return false;
  const effective = ["boundary-preserving-v1", "single-turn-continuation-v1"].includes(String(context.recommendation_policy))
    ? effectiveCriticRecommendation(p.profile, p.specId, parent.outcome === "Resisted" ? "RESISTED" : "INCONCLUSIVE", review, String(context.recommendation_policy))
    : context.recommendation_policy == null ? { profile: review.recommended_attack_profile_id, objective: review.recommended_follow_up_objective } : null;
  return Boolean(effective && c.parentRunId === parent.runId && c.viaReviewId === review.critic_review_id
    && p.reviewId === review.critic_review_id && context.parent_run_id === parent.runId
    && context.critic_review_id === review.critic_review_id && context.source_evaluation_id === parent.appendix["Evaluation ID"]
    && context.source_candidate_sha256 === parent.appendix["Prompt SHA-256"]
    && context.source_correlation_sha256 === parent.appendix["Correlation SHA-256"]
    && context.source_judge_sha256 === review.source_judge_sha256
    && /^[a-f0-9]{64}$/.test(p.specHash) && context.assessment_spec_sha256 === p.specHash && c.specHash === p.specHash
    && context.recommended_attack_profile_id === effective.profile && c.profile === effective.profile
    && context.objective === effective.objective && JSON.stringify(context.expected_evidence) === JSON.stringify(review.expected_evidence));
}

export function assessmentChains(items: ManagementReportItem[]) {
  const chat = items.filter((item) => item.source === "ChatMate");
  const byId = new Map(chat.map((item) => [item.runId, item]));
  const parents = new Map<string, string>(), notices = new Map<string, string>();
  for (const item of chat) {
    const id = item.lineage?.parentRunId;
    if (!id) continue;
    const parent = byId.get(id);
    if (!parent) notices.set(item.runId, "Parent not selected; continuation cannot be cross-verified in this report.");
    else if (!linked(parent, item)) notices.set(item.runId, "Lineage conflict: parent, Critic or frozen context does not match. Results remain independent.");
    else parents.set(item.runId, id);
  }
  for (const item of chat) {
    let id: string | undefined = item.runId;
    const seen = new Set<string>();
    while (id && parents.has(id)) {
      if (seen.has(id)) {
        for (const cyclic of seen) { parents.delete(cyclic); notices.set(cyclic, "Lineage conflict: cyclic parent references."); }
        break;
      }
      seen.add(id); id = parents.get(id);
    }
  }
  const groups = new Map<string, AssessmentChain>();
  for (const item of chat) {
    let root = item.runId;
    while (parents.has(root)) root = parents.get(root)!;
    if (!groups.has(root)) groups.set(root, { rootRunId: root, status: "Verified", stages: [], transitions: [] });
    groups.get(root)!.stages.push(item);
  }
  for (const chain of groups.values()) {
    const depth = (id: string) => { let count = 0; while (parents.has(id)) { id = parents.get(id)!; count++; } return count; };
    chain.stages.sort((a, b) => depth(a.runId) - depth(b.runId));
    for (const item of chain.stages) {
      if (notices.has(item.runId)) { chain.notice = notices.get(item.runId); chain.status = chain.notice!.startsWith("Lineage conflict") ? "Conflict" : "Partial"; }
      if (parents.has(item.runId)) {
        const parent = byId.get(parents.get(item.runId)!)!;
        chain.transitions.push({ parentRunId: parent.runId, childRunId: item.runId,
          criticReviewId: parent.critic!.review!.critic_review_id,
          policyAdjusted: item.lineage?.context?.recommended_attack_profile_id !== parent.critic!.review!.recommended_attack_profile_id });
      }
    }
    if (chain.status === "Verified" && chain.stages.some((item) => item.critic?.review?.recommendation_available
        && !chain.transitions.some((edge) => edge.parentRunId === item.runId))) {
      chain.status = "Partial"; chain.notice = "No linked follow-up selected for a saved recommendation.";
    }
  }
  return { chains: [...groups.values()], independentItems: items.filter((item) => item.source !== "ChatMate") };
}
