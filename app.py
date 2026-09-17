import json
import logging
import os
from typing import Dict, List, Tuple
import streamlit as st
from dotenv import load_dotenv

from core.client import LLMClient
from core.engine import AuditOrchestrator
from core.loader import load_attack_library, load_target_profile, save_audit_report
from core.models import AuditReport, TargetAgentProfile

load_dotenv()

logger = logging.getLogger("redteam_app")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] [UI]: %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

st.set_page_config(
    page_title="AI Agent Red-Team Assessment",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown(
    """
    <style>
        .block-container { padding-top: 3rem; max-width: 1500px; }
        section[data-testid="stSidebar"] { min-width: 330px; }
        div[data-testid="stMetric"] { background: #111827; border: 1px solid #243044; border-radius: 12px; padding: 14px; }
        div[data-testid="stMetric"] label { color: #94a3b8 !important; }
        .app-card { border: 1px solid #263244; border-radius: 14px; padding: 18px 20px; background: #0f172a; min-height: 132px; }
        .app-card-title { color: #94a3b8; font-size: 0.82rem; text-transform: uppercase; letter-spacing: .08em; margin-bottom: 8px; }
        .app-card-main { color: #f8fafc; font-size: 1.25rem; font-weight: 700; margin-bottom: 8px; }
        .app-card-sub { color: #cbd5e1; font-size: 0.94rem; line-height: 1.35; }
        .severity-high { color: #f97316; font-weight: 800; }
        .severity-critical { color: #ef4444; font-weight: 800; }
        .severity-medium { color: #facc15; font-weight: 800; }
        .severity-low { color: #38bdf8; font-weight: 800; }
        .severity-none { color: #22c55e; font-weight: 800; }
        .small-muted { color: #94a3b8; font-size: 0.9rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

MODEL_OPTIONS = [
    "qwen/qwen3.8-27b",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "openai/gpt-4o-mini",
    "openai/gpt-4.1-mini",
    "Custom",
]

ENDPOINT_OPTIONS = {
    "Groq OpenAI-compatible": "https://api.groq.com/openai/v1",
    "OpenAI": "https://api.openai.com/v1",
    "Custom": "",
}

DEPTH_OPTIONS = {
    "Quick - 1 turn": 1,
    "Standard - 3 turns": 3,
    "Deep - 5 turns": 5,
}

if "audit_reports" not in st.session_state:
    st.session_state["audit_reports"] = []
if "is_running" not in st.session_state:
    st.session_state["is_running"] = False


def summarize_text(text: str, max_chars: int = 700) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "..."


def compact_text(text: str, max_chars: int = 110) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "..."


def card(title: str, main: str, sub: str = "") -> None:
    st.markdown(
        f"""
        <div class="app-card">
            <div class="app-card-title">{title}</div>
            <div class="app-card-main">{main}</div>
            <div class="app-card-sub">{sub}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def severity_class(severity: str) -> str:
    return f"severity-{severity.lower()}"


def get_model_choice(label: str, env_key: str, fallback: str) -> str:
    configured = os.getenv(env_key, fallback)
    default_index = MODEL_OPTIONS.index(configured) if configured in MODEL_OPTIONS else MODEL_OPTIONS.index("Custom")
    selected = st.selectbox(label, MODEL_OPTIONS, index=default_index)
    if selected == "Custom":
        return st.text_input(f"Custom {label}", value=configured if configured not in MODEL_OPTIONS else "").strip()
    return selected


def get_endpoint_choice() -> str:
    configured = os.getenv("LLM_BASE_URL", ENDPOINT_OPTIONS["Groq OpenAI-compatible"])
    matching_label = next((label for label, value in ENDPOINT_OPTIONS.items() if value == configured), "Custom")
    provider = st.selectbox("Provider Endpoint", list(ENDPOINT_OPTIONS.keys()), index=list(ENDPOINT_OPTIONS.keys()).index(matching_label))
    if provider == "Custom":
        return st.text_input("Custom Base URL", value=configured if configured not in ENDPOINT_OPTIONS.values() else "").strip()
    return ENDPOINT_OPTIONS[provider]


def load_profile_options(config_files: List[str]) -> Dict[str, Tuple[str, TargetAgentProfile]]:
    options = {}
    for config_file in config_files:
        try:
            profile = get_target_profile(os.path.join("configs", config_file))
            label = profile.name
            if label in options:
                label = f"{profile.name} #{len(options) + 1}"
            options[label] = (config_file, profile)
        except Exception as e:
            logger.error(f"Skipping invalid profile '{config_file}': {e}", exc_info=True)
    return options


def highest_severity(report: AuditReport) -> str:
    severity_rank = {
        "NONE": 0,
        "LOW": 1,
        "MEDIUM": 2,
        "HIGH": 3,
        "CRITICAL": 4,
    }
    severities = [trace.verdict.severity.value for trace in report.traces]
    if not severities:
        return "NONE"
    return max(severities, key=lambda value: severity_rank.get(value, 0))


def tool_call_count(report: AuditReport) -> int:
    return sum(len(trace.tool_calls_attempted) for trace in report.traces)


def fallback_probe_count(report: AuditReport) -> int:
    return sum(1 for trace in report.traces if trace.probe_source == "template_fallback")


def evaluation_failure_count(report: AuditReport) -> int:
    return sum(1 for trace in report.traces if trace.verdict.evaluation_failed)


def tool_policy_finding_count(report: AuditReport) -> int:
    return sum(len(trace.tool_policy_findings) for trace in report.traces)


def render_report_summary(report: AuditReport) -> None:
    if report.breached:
        st.error(f"Breach detected on turn {report.breach_turn}")
    else:
        st.success("Defended: boundaries maintained")

    s_col1, s_col2, s_col3, s_col4 = st.columns(4)
    s_col1.metric("Target", report.target_agent_name)
    s_col2.metric("Scenario", report.vector_tested.name)
    s_col3.metric("Turns", report.turns_executed)
    s_col4.metric("Highest Severity", highest_severity(report))

    t_col1, t_col2, t_col3, t_col4 = st.columns(4)
    t_col1.metric("Tool Calls Attempted", tool_call_count(report))
    t_col2.metric("Policy Findings", tool_policy_finding_count(report))
    t_col3.metric("Fallback Probes", fallback_probe_count(report))
    t_col4.metric("Judge Failures", evaluation_failure_count(report))
    st.caption(f"Test ID: {report.test_id}")

    violating_trace = next((trace for trace in report.traces if trace.verdict.violation_detected), None)
    if violating_trace and violating_trace.verdict.evidence_quote:
        st.warning(f"Evidence: {violating_trace.verdict.evidence_quote}")


@st.cache_resource
def get_attack_library():
    try:
        return load_attack_library("attack_library.yaml")
    except Exception as e:
        logger.error(f"Failed to load attack library: {e}", exc_info=True)
        raise


@st.cache_resource
def get_target_profile(profile_path: str):
    try:
        return load_target_profile(profile_path)
    except Exception as e:
        logger.error(f"Failed to load profile '{profile_path}': {e}", exc_info=True)
        raise


try:
    attack_lib = get_attack_library()
except Exception as e:
    st.error(f"Initialization failure: Could not load attack library. Details: {e}")
    st.stop()

config_files = []
if os.path.exists("configs"):
    config_files = sorted(f for f in os.listdir("configs") if f.endswith((".yaml", ".yml")))

if not config_files:
    logger.warning("No configuration files found in configs/ directory.")

profile_options = load_profile_options(config_files)

with st.sidebar:
    st.header("Assessment")

    selected_profile_label = st.selectbox(
        "Target Persona",
        list(profile_options.keys()),
        index=0 if profile_options else None
    )

    vector_options = {v.name: v for v in attack_lib.attack_vectors}
    chosen_vector_key = st.selectbox("Attack Scenario", list(vector_options.keys()))
    selected_vector = vector_options[chosen_vector_key]

    depth_label = st.radio("Assessment Depth", list(DEPTH_OPTIONS.keys()), index=1)
    max_turns = DEPTH_OPTIONS[depth_label]

    st.divider()

    with st.expander("Connection & Models", expanded=False):
        api_key_input = st.text_input(
            "API Key (Groq / OpenAI)",
            value=os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY") or "",
            type="password"
        )

        base_url_input = get_endpoint_choice()
        selected_model = get_model_choice("Model", "LLM_MODEL", "qwen/qwen3.8-27b")
        split_models = st.toggle("Use separate attacker/judge models", value=False)
        if split_models:
            attacker_model = get_model_choice("Attacker Model", "ATTACKER_MODEL", selected_model)
            judge_model = get_model_choice("Judge Model", "JUDGE_MODEL", selected_model)
        else:
            attacker_model = selected_model
            judge_model = selected_model

    st.divider()
    st.caption("Raw configuration filenames and full prompt recipes are hidden from the main demo view.")

st.title("AI Agent Red-Team Assessment")
st.caption("A stakeholder-friendly view of prompt-injection, data-leakage, and unsafe-tool-use resilience.")

if not selected_profile_label:
    st.warning("No configuration YAML files found in 'configs/' directory. Please add a target profile.")
    st.stop()

selected_config, target_profile = profile_options[selected_profile_label]

overview_cols = st.columns([1.1, 1.1, 0.8])
with overview_cols[0]:
    card("Target Persona", target_profile.name, compact_text(target_profile.description, 150))
with overview_cols[1]:
    card("Attack Scenario", selected_vector.name, compact_text(selected_vector.description, 150))
with overview_cols[2]:
    card("Assessment Depth", depth_label.split(" - ")[0], f"{max_turns} interaction turn{'s' if max_turns != 1 else ''}")

st.markdown("### Scenario Brief")
brief_cols = st.columns([1, 1, 1, 1])
brief_cols[0].markdown(f"**Category**\n\n{selected_vector.category}")
brief_cols[1].markdown(f"**Severity**\n\n<span class='{severity_class(selected_vector.severity.value)}'>{selected_vector.severity.value}</span>", unsafe_allow_html=True)
brief_cols[2].markdown(f"**Tools in Scope**\n\n{len(target_profile.tools)} simulated tools")
brief_cols[3].markdown(f"**Guardrails**\n\n{len(target_profile.guardrails)} active controls")

with st.expander("View persona guardrails and tool catalog", expanded=False):
    g_col, tool_col = st.columns(2)
    with g_col:
        st.markdown("**Guardrails**")
        for g in target_profile.guardrails:
            st.markdown(f"- {g}")
    with tool_col:
        st.markdown("**Tools**")
        if target_profile.tools:
            for tool in target_profile.tools:
                st.markdown(f"- `{tool.name}`")
        else:
            st.markdown("No tools registered.")

with st.expander("View technical scenario recipe", expanded=False):
    st.caption(f"Vector ID: {selected_vector.id} | Config: {selected_config}")
    st.write(selected_vector.recipe)

start_audit = st.button("Run Assessment", type="primary", disabled=st.session_state["is_running"])

if start_audit:
    if not api_key_input.strip():
        logger.error("User attempted execution without an API key.")
        st.error("Authentication Error: An API Key is required to execute the audit suite.")
        st.stop()

    if not base_url_input.strip() or not selected_model.strip() or not attacker_model.strip() or not judge_model.strip():
        st.error("Model configuration is incomplete. Choose a listed model or provide a custom model ID.")
        st.stop()

    st.session_state["is_running"] = True
    logger.info(f"Initiating audit for target '{target_profile.name}' with vector '{selected_vector.id}'.")

    try:
        target_client = LLMClient(
            api_key=api_key_input.strip(),
            base_url=base_url_input.strip(),
            model=selected_model.strip()
        )
        attacker_client = LLMClient(
            api_key=api_key_input.strip(),
            base_url=base_url_input.strip(),
            model=attacker_model.strip()
        )
        judge_client = LLMClient(
            api_key=api_key_input.strip(),
            base_url=base_url_input.strip(),
            model=judge_model.strip()
        )
        orchestrator = AuditOrchestrator(
            attacker_client=attacker_client,
            target_client=target_client,
            judge_client=judge_client,
        )

        status_container = st.status("Executing multi-turn red-team assessment...", expanded=True)

        with status_container:
            st.write(f"Session initialized against target: {target_profile.name}")
            st.write(f"Executing vector: {selected_vector.id} ({selected_vector.name})")

            report = orchestrator.execute_audit(
                profile=target_profile,
                vector=selected_vector,
                max_turns=max_turns
            )

            st.session_state["audit_reports"].insert(0, report)
            saved_path = save_audit_report(report)
            if saved_path:
                logger.info(f"Report exported to disk: {saved_path}")

            if report.breached:
                status_container.update(
                    label=f"BREACH DETECTED on Turn {report.breach_turn}",
                    state="error"
                )
            else:
                status_container.update(
                    label="DEFENDED: boundaries maintained across all interaction turns",
                    state="complete"
                )

    except Exception as e:
        logger.error(f"Audit campaign terminated unexpectedly: {e}", exc_info=True)
        st.error(f"Execution Error: The audit campaign encountered a failure: {e}")
    finally:
        st.session_state["is_running"] = False

st.divider()

if st.session_state["audit_reports"]:
    latest_report = st.session_state["audit_reports"][0]
    st.header("Latest Result")
    render_report_summary(latest_report)

    st.divider()
    st.header("Assessment History")

    summary_rows = []
    for report in st.session_state["audit_reports"]:
        summary_rows.append({
            "Test ID": report.test_id,
            "Target": report.target_agent_name,
            "Scenario": report.vector_tested.name,
            "Result": "BREACH" if report.breached else "DEFENDED",
            "Turns": report.turns_executed,
            "Severity": highest_severity(report),
            "Tool Calls": tool_call_count(report),
            "Policy Findings": tool_policy_finding_count(report),
            "Fallback Probes": fallback_probe_count(report),
            "Judge Failures": evaluation_failure_count(report),
        })
    st.dataframe(summary_rows, hide_index=True, use_container_width=True)

    for idx, report in enumerate(st.session_state["audit_reports"]):
        status_badge = "BREACH DETECTED" if report.breached else "DEFENDED"

        with st.expander(f"{report.target_agent_name} | {report.vector_tested.name} | {status_badge}", expanded=idx == 0):
            r_col1, r_col2, r_col3, r_col4 = st.columns(4)
            r_col1.metric("Result", status_badge)
            r_col2.metric("Turns", report.turns_executed)
            r_col3.metric("Severity", highest_severity(report))
            r_col4.metric("Policy Findings", tool_policy_finding_count(report))
            st.caption(f"Test ID: {report.test_id} | Vector: {report.vector_tested.id}")

            st.markdown("#### Assessment Timeline")
            for trace in report.traces:
                v = trace.verdict
                turn_status = "Evaluation Inconclusive" if v.evaluation_failed else "Violation Detected" if v.violation_detected else "Boundary Maintained"
                turn_col1, turn_col2, turn_col3 = st.columns([1, 2.5, 1])
                turn_col1.markdown(f"**Turn {trace.turn_number}**")
                turn_col2.markdown(f"**{turn_status}**")
                turn_col3.markdown(f"**Severity:** `{v.severity.value}`")

                st.caption(f"Probe source: {trace.probe_source}")

                if v.evaluation_failed:
                    st.warning(summarize_text(v.reasoning, 350))
                elif v.violation_detected:
                    st.error(summarize_text(v.reasoning, 350))
                    if v.status == "policy_override":
                        st.caption("Source: deterministic tool policy override")
                else:
                    st.success("Boundary Maintained")
                    st.markdown(f"**Reason:** {summarize_text(v.reasoning, 350)}")

                with st.expander(f"Turn {trace.turn_number} details", expanded=False):
                    d_col1, d_col2 = st.columns(2)
                    with d_col1:
                        st.markdown("**Red-team prompt**")
                        st.write(trace.probe)
                    with d_col2:
                        st.markdown(f"**{report.target_agent_name} response**")
                        st.write(trace.target_response)

                    if v.evidence_quote:
                        st.markdown(f"**Evidence:** {v.evidence_quote}")
                    st.markdown(f"**Full judge reasoning:** {v.reasoning}")

                    if trace.tool_calls_attempted:
                        st.markdown("**Raw tool calls**")
                        st.json(trace.tool_calls_attempted)

                    if trace.tool_policy_findings:
                        st.markdown("**Deterministic tool policy findings**")
                        st.json(trace.tool_policy_findings)

                st.divider()

            try:
                report_json = json.dumps(report.model_dump(mode="json"), indent=2)
                st.download_button(
                    label=f"Download Report ({report.test_id})",
                    data=report_json,
                    file_name=f"audit_{report.test_id}.json",
                    mime="application/json",
                    key=f"dl_{report.test_id}"
                )
            except Exception as e:
                logger.error(f"Failed to generate download payload for report '{report.test_id}': {e}", exc_info=True)
                st.warning("Could not serialize audit report for download.")
