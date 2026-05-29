"""
AI Underwriting System — Underwriter UI

Run with:
    uv run streamlit run streamlit_app.py
"""
from __future__ import annotations

import os
import threading
import time
import uuid

import httpx
import streamlit as st
from underwriting.platform.cost_tracking.dashboard import main as _cost_dashboard_main

API_BASE = os.getenv("API_BASE", "http://localhost:8081/api/v1")
TIMEOUT = 300  # seconds — pipeline can take 2-3 minutes


st.set_page_config(
    page_title="AI Underwriting System",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    #root > div:first-child .block-container { padding-top: 0.5rem; }
    h1 { text-align: center; margin-top: 0; }
    #MainMenu { visibility: hidden; display: none; }
    footer { visibility: hidden; }
    header[data-testid="stHeader"] { background: transparent; }
    [data-testid="stToolbar"] { display: none; }
</style>
<h1 style="margin-top:0;">AI Underwriting System</h1>
<p style="text-align:center; margin-top:-0.5rem;">Enterprise Multi-Agent AI Platform</p>
<hr/>
<script>
window.addEventListener('keydown', function(e) {
    if (!e.ctrlKey && !e.metaKey && !e.altKey &&
        (e.key === 'c' || e.key === 'C' || e.key === 'r' || e.key === 'R')) {
        var tag = document.activeElement ? document.activeElement.tagName : '';
        if (tag !== 'INPUT' && tag !== 'TEXTAREA') { e.stopPropagation(); }
    }
}, true);
</script>
""", unsafe_allow_html=True)


# ── Shared helpers ────────────────────────────────────────────────────────────

def _risk_colour(decision: str) -> str:
    return {"ACCEPT": "green", "REFER": "orange", "DECLINE": "red"}.get(decision, "gray")


def _status_colour(status: str) -> str:
    return {
        "COMPLETED": "green", "DECLINED": "red",
        "AWAITING_SENIOR_REVIEW": "orange", "GOVERNANCE_REJECTED": "red",
        "RUNNING": "blue", "AWAITING_HUMAN": "orange",
        "INGESTED": "green", "INGESTION_FAILED": "red",
    }.get(status, "gray")


def _fmt_currency(amount, currency="NZD") -> str:
    try:
        return f"{currency} {float(amount):,.2f}"
    except Exception:
        return str(amount)


def _show_risk_assessment(ra: dict) -> None:
    col1, col2, col3 = st.columns(3)
    decision = ra.get("risk_decision", "?")
    col1.metric("Risk Decision", decision)
    col2.metric("Risk Score", f"{ra.get('risk_score', 0):.2f}")
    col3.metric("Confidence", f"{ra.get('confidence_score', 0):.2f}")
    if ra.get("pre_screen_triggered"):
        st.warning(f"**Pre-screen rule fired:** {ra.get('pre_screen_rule')}")
    if ra.get("signal_conflict"):
        st.info(f"**Signal conflict:** {ra.get('signal_conflict_explanation')}")
    st.write("**Primary risk factors:**")
    for f in ra.get("primary_risk_factors", []):
        st.write(f"- {f}")
    st.write("**Mitigating factors:**")
    for f in ra.get("mitigating_factors", []):
        st.write(f"- {f}")
    st.write("**Decision rationale:**")
    st.write(ra.get("decision_rationale", ""))
    if ra.get("escalation_reason"):
        st.error(f"**Escalation reason:** {ra.get('escalation_reason')}")


def _show_claim_profile(cp: dict) -> None:
    col1, col2, col3 = st.columns(3)
    col1.metric("Source", cp.get("source", "?"))
    col2.metric("Claims (3yr)", cp.get("total_claims_3yr", 0))
    col3.metric("Claims (5yr)", cp.get("total_claims_5yr", 0))
    col4, col5, col6 = st.columns(3)
    col4.metric("Incurred 3yr", _fmt_currency(cp.get("total_incurred_3yr", 0)))
    col5.metric("Largest Loss", _fmt_currency(cp.get("largest_single_loss", 0)))
    col6.metric("Data Quality", cp.get("data_quality", "?"))
    if cp.get("risk_flags"):
        st.write("**Risk flags:**", ", ".join(cp["risk_flags"]))
    st.write(f"**Trend:** {cp.get('claim_frequency_trend', '?')}  |  "
             f"**Most common cause:** {cp.get('most_common_cause', 'N/A')}")


def _show_hazard_score(hs: dict) -> None:
    col1, col2 = st.columns(2)
    col1.metric("Overall Hazard", hs.get("overall_hazard_level", "?"))
    col2.metric("Hazard Score", f"{hs.get('overall_hazard_score', 0):.2f}")
    cols = st.columns(4)
    cols[0].metric("Flood", hs.get("flood_risk", "?"))
    cols[1].metric("Fire", hs.get("fire_risk", "?"))
    cols[2].metric("Structural", hs.get("structural_risk", "?"))
    cols[3].metric("Environmental", hs.get("environmental_risk", "?"))
    if hs.get("key_hazard_factors"):
        st.write("**Key hazard factors:**")
        for f in hs["key_hazard_factors"]:
            st.write(f"- {f}")
    if hs.get("data_gaps"):
        st.write("**Data gaps:**", ", ".join(hs["data_gaps"]))


def _show_pricing(po: dict) -> None:
    currency = po.get("premium_currency", "NZD")
    col1, col2, col3 = st.columns(3)
    col1.metric("Base Premium", _fmt_currency(po.get("base_premium", 0), currency))
    col2.metric("Final Premium", _fmt_currency(po.get("final_premium", 0), currency))
    col3.metric("Excess", _fmt_currency(po.get("excess_recommended", 0), currency))
    if po.get("risk_loadings"):
        st.write("**Risk loadings:**")
        for l in po["risk_loadings"]:
            st.write(f"- {l['reason']}: +{_fmt_currency(l['amount'], currency)}")
    if po.get("discounts"):
        st.write("**Discounts:**")
        for d in po["discounts"]:
            st.write(f"- {d['reason']}: -{_fmt_currency(d['amount'], currency)}")
    if po.get("payment_options"):
        st.write("**Payment options:**")
        for opt in po["payment_options"]:
            st.write(f"- {opt['frequency']}: {_fmt_currency(opt['instalment_amount'], currency)}")
    if po.get("policy_conditions"):
        st.write("**Policy conditions:**")
        for c in po["policy_conditions"]:
            st.write(f"- {c}")
    st.write(f"**Rationale:** {po.get('premium_rationale', '')}")


def _show_governance(gd: dict) -> None:
    outcome = gd.get("governance_outcome", "?")
    colour = {"APPROVED": "green", "REJECTED": "red"}.get(outcome, "orange")
    st.markdown(f"### Outcome: :{colour}[**{outcome}**]")
    col1, col2 = st.columns(2)
    col1.metric("Checks Passed", len(gd.get("checks_passed", [])))
    col2.metric("Checks Failed", len(gd.get("checks_failed", [])))
    if gd.get("checks_failed"):
        st.write("**Failed checks:**")
        for f in gd["checks_failed"]:
            st.error(f"**{f['check_name']}:** {f['explanation']}")
    if gd.get("referral_reason"):
        st.warning(f"**Referral reason:** {gd['referral_reason']}")
    if gd.get("governance_notes"):
        with st.expander("Governance notes"):
            for n in gd["governance_notes"]:
                st.write(f"- {n}")


# ── Agent progress pills ──────────────────────────────────────────────────────

_AGENT_PILLS = [
    ("📄 Document Ingestion", "#1565C0"),
    ("📋 Claims History",     "#6A1B9A"),
    ("🌍 Hazard Evaluation",  "#E65100"),
    ("⚖️ Underwriting Risk",  "#B71C1C"),
    ("💰 Pricing",            "#1B5E20"),
    ("🛡️ Governance",        "#00695C"),
]

_STEP_TO_ACTIVE: dict[str, list[int]] = {
    "document_ingestion": [0],
    "parallel_analysis":  [1, 2],
    "underwriting_risk":  [3],
    "pricing":            [4],
    "governance":         [5],
}


def _render_pipeline_progress(active: int | list[int], final: bool = False) -> str:
    active_set: set[int] = set(active) if isinstance(active, list) else {active}
    pills = []
    for i, (name, color) in enumerate(_AGENT_PILLS):
        if final:
            completed_count = active if isinstance(active, int) else max(active_set) + 1
            if i < completed_count:
                style = f"background:{color};color:white;opacity:0.65;"
                label = f"✓ {name}"
            else:
                style = "background:#e0e0e0;color:#aaa;"
                label = name
        else:
            min_active = min(active_set) if active_set else 0
            if i < min_active:
                style = f"background:{color};color:white;opacity:0.65;"
                label = f"✓ {name}"
            elif i in active_set:
                style = (
                    f"background:{color};color:white;opacity:1;"
                    f"box-shadow:0 0 12px {color}90;font-size:0.95rem;"
                )
                label = f"⟳ {name}"
            else:
                style = "background:#e0e0e0;color:#aaa;"
                label = name
        pills.append(
            f'<span style="{style}padding:5px 14px;border-radius:20px;'
            f'font-weight:600;display:inline-block;margin:2px;">{label}</span>'
        )
    return (
        '<div style="display:flex;flex-wrap:wrap;gap:4px;margin:10px 0;">'
        + "".join(pills) + "</div>"
    )


# ── Page functions ────────────────────────────────────────────────────────────

def page_how_it_works():
    st.subheader("How This System Works")
    st.markdown("This is an AI-powered insurance underwriting system. It automates the full process of evaluating a broker's insurance submission — a task that traditionally takes an underwriter hours to complete manually.")

    st.divider()
    st.subheader("The Process")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("#### Step 1 — Submit")
        st.markdown("Go to **Submit Document**. Paste the broker's insurance document, choose class of business and jurisdiction, and click **Run Full Pipeline**.")
    with col2:
        st.markdown("#### Step 2 — Review the AI Decision")
        st.markdown("When complete, the system shows the outcome. Auto-approve, auto-decline, or refer to a human underwriter.")
    with col3:
        st.markdown("#### Step 3 — Human Decision (if referred)")
        st.markdown("Go to **Underwriter Queue**. Review the AI's assessment, apply your judgement, and submit your decision.")

    st.divider()
    st.subheader("Is a Human Always Involved?")
    st.info("""
**No — only for referred cases.** Here is how the routing works:

- **Auto-Approve** — AI returns ACCEPT with confidence ≥ 70%. Pricing and governance run automatically. Status: ✅ COMPLETED.
- **Human Review (Refer)** — Confidence below 70%, or a business rule flags the case. Sent to Underwriter Queue.
- **Auto-Decline** — Hard rules breached (extreme hazard + high claims, fraud flag). Immediate decline, no pricing.
""")

    st.divider()
    st.subheader("Outcome Status — What Each One Means")
    st.markdown("""
| Status | What it means | Your next action |
|---|---|---|
| ✅ **COMPLETED** | Pipeline fully processed — risk accepted, priced, and governance approved | Nothing required |
| ⚠️ **Awaiting Underwriter Decision** | AI referred the case — needs your review and decision | Go to **Underwriter Queue** |
| ❌ **DECLINED** | Risk automatically declined by business rules or AI assessment | Nothing required — case is closed |
| ❌ **FAILED** | A technical error occurred during processing | Re-submit the document |
""")

    st.divider()
    st.subheader("The 6 AI Agents — What Runs Behind the Scenes")
    st.markdown("""
| # | Agent | Model | What it does |
|---|---|---|---|
| 1 | **Document Ingestion** | Claude Haiku | Reads the broker document and extracts structured fields |
| 2 | **Claims History** | Claude Haiku | Finds this customer's past claims or finds similar claims as a market benchmark |
| 3 | **Hazard Evaluation** | Claude Sonnet | Scores flood, fire, seismic and environmental risk for the property location |
| 4 | **Underwriting Risk** | Claude Sonnet | Combines all outputs and decides Accept / Decline / Refer |
| 5 | **Pricing** | Claude Haiku | Calculates the premium using market rate tables with risk loadings and discounts |
| 6 | **Governance** | Claude Sonnet | Final check — verifies consistency, compliance, and fraud signals |
""")

    st.divider()
    st.subheader("Sample Documents — What to Expect")
    with st.expander("referral_large_claim.txt — Single large loss Refer", expanded=False):
        st.markdown("**Insured:** Tauranga Cold Chain Holdings Ltd — 1 claim of NZD 1,050,000. Referred due to claim severity. Post-claim remediation evidence available for underwriter review.")
    with st.expander("referral_more_claims.txt — High frequency Refer", expanded=False):
        st.markdown("**Insured:** Central Plains Logistics Ltd — 3 claims in last 3 years. Referred due to elevated claim frequency. Remedial works completed.")
    with st.expander("referral_hazard_zone.txt — Hazard zone Refer", expanded=False):
        st.markdown("**Insured:** Wellington coastal property — HIGH seismic zone + coastal exposure pushes confidence below auto-approve threshold.")
    with st.expander("clean_auto_approve.txt — Auto approve case", expanded=False):
        st.markdown("**Insured:** Clean risk with no claims, low hazard, complete fields. AI accepts with high confidence and auto-approves without human review.")
    with st.expander("decline_missing_fields.txt — Missing fields Decline", expanded=False):
        st.markdown("**Insured:** Metro Storage Solutions Ltd — Sum insured, year built, floor area, NZBN missing. Pipeline stops after ingestion. Resubmit with complete document.")
    with st.expander("decline_prompt_injection.txt — Prompt injection Decline", expanded=False):
        st.markdown("Document contains deliberate prompt injection attacks. Ingestion agent detects and flags. Pipeline stops immediately.")


def page_submit_document():
    st.title("Submit Broker Document")
    st.caption("Paste the broker document text below. The AI pipeline will extract, analyse, and return a risk decision.")

    for _k, _v in [
        ("pipeline_running", False),
        ("pipeline_result", None),
        ("pipeline_error", None),
        ("pipeline_params", None),
        ("pipeline_submission_id", None),
        ("form_version", 0),
        ("pipeline_result_shown", False),
    ]:
        if _k not in st.session_state:
            st.session_state[_k] = _v

    # Clear stale results when user navigates back after already viewing them
    if (
        not st.session_state.pipeline_running
        and st.session_state.pipeline_result_shown
    ):
        st.session_state.pipeline_result = None
        st.session_state.pipeline_error = None
        st.session_state.pipeline_result_shown = False

    running = st.session_state.pipeline_running
    top_status = st.empty()
    top_progress = st.empty()

    if running:
        st.info("🔒  Form locked — pipeline is running. Please wait...")
        submitted = False
        class_of_business = document_content = jurisdiction = None
    else:
        fv = st.session_state.form_version
        with st.form(f"submit_form_{fv}"):
            col1, col2 = st.columns(2)
            class_of_business = col1.selectbox(
                "Class of Business", ["Property", "Liability", "Marine", "Motor", "Specialty"],
            )
            jurisdiction = col2.selectbox("Jurisdiction", ["NZ", "AU"])
            document_content = st.text_area(
                "Broker Document (paste full text)", height=300,
                placeholder="Paste the broker submission document here...",
            )
            submitted = st.form_submit_button("Run Full Pipeline", type="primary", use_container_width=True)

    if submitted:
        if not document_content.strip():
            top_status.error("⚠️ Please paste a broker document before submitting.")
            st.stop()
        st.session_state.pipeline_running = True
        st.session_state.pipeline_submission_id = str(uuid.uuid4())
        st.session_state.pipeline_params = {
            "submission_id": st.session_state.pipeline_submission_id,
            "class_of_business": class_of_business.lower(),
            "jurisdiction": jurisdiction,
            "document_content": document_content,
        }
        st.session_state.pipeline_result = None
        st.session_state.pipeline_error = None
        st.rerun()

    if st.session_state.pipeline_running and st.session_state.pipeline_params:
        params = st.session_state.pipeline_params
        client_sid = st.session_state.pipeline_submission_id
        top_status.info("🚀  Pipeline started — please wait 1–3 minutes. Do not close this page.")
        top_progress.progress(2)

        result_holder: dict = {}

        def _call_api():
            try:
                resp = httpx.post(f"{API_BASE}/submissions/pipeline", json=params, timeout=TIMEOUT)
                if not resp.is_success:
                    try:
                        detail = resp.json().get("detail", resp.text[:500])
                    except Exception:
                        detail = resp.text[:500]
                    result_holder["error"] = f"HTTP {resp.status_code}: {detail}"
                    return
                result_holder["data"] = resp.json()
            except Exception as e:
                result_holder["error"] = str(e)

        thread = threading.Thread(target=_call_api, daemon=True)
        thread.start()

        tick = 0
        last_active: list[int] = [0]
        while thread.is_alive():
            try:
                pr = httpx.get(f"{API_BASE}/submissions/{client_sid}/progress", timeout=2)
                if pr.is_success:
                    step = pr.json().get("step")
                    if step and step in _STEP_TO_ACTIVE:
                        last_active = _STEP_TO_ACTIVE[step]
            except Exception:
                pass
            pct = min(2 + tick * 3, 92)
            top_status.markdown(_render_pipeline_progress(last_active), unsafe_allow_html=True)
            top_progress.progress(pct)
            time.sleep(1)
            tick += 1

        thread.join()
        st.session_state.pipeline_running = False
        st.session_state.pipeline_params = None
        st.session_state.form_version += 1

        if "error" in result_holder:
            st.session_state.pipeline_error = result_holder["error"]
        else:
            st.session_state.pipeline_result = result_holder["data"]
        st.rerun()

    if st.session_state.pipeline_error:
        top_status.error(f"❌  Pipeline failed: {st.session_state.pipeline_error}")

    if st.session_state.pipeline_result:
        result = st.session_state.pipeline_result
        wf_status = result.get("workflow_status", "?")
        policy_number = result.get("submission_ref", "")
        decline_reason = result.get("decline_reason")

        missing_fields = result.get("missing_critical_fields", [])
        injection_snippets = result.get("injection_snippets", [])
        is_early_decline = bool(missing_fields or injection_snippets)

        if is_early_decline:
            top_status.markdown(
                _render_pipeline_progress([0], final=False), unsafe_allow_html=True
            )
        else:
            agents_ran = 4
            if result.get("pricing_output"):
                agents_ran = 5
            if result.get("governance_decision"):
                agents_ran = 6
            top_status.markdown(_render_pipeline_progress(agents_ran, final=True), unsafe_allow_html=True)
        top_progress.progress(100)

        pn = f"  |  Reference: **{policy_number}**" if policy_number else ""
        if wf_status == "COMPLETED":
            top_status.success(f"✅  Pipeline complete — Risk approved and fully processed.{pn}")
        elif is_early_decline:
            top_status.error(f"❌  Submission Declined.{pn}")
        elif wf_status == "DECLINED":
            top_status.error(f"❌  Risk Declined — See Risk Assessment below for reasons.{pn}")
        elif wf_status in ("AWAITING_HUMAN", "RUNNING"):
            top_status.warning(
                f"⏳  **Awaiting Human Review** — This submission has been referred to the underwriter queue. "
                f"Go to **Underwriter Queue** in the left sidebar to review and submit your decision.{pn}"
            )
        elif wf_status == "AWAITING_SENIOR_REVIEW":
            top_status.warning(f"⚠️  Escalated to Senior Review — A senior underwriter must give final approval.{pn}")
        else:
            top_status.info(f"Status: {wf_status}{pn}")

        st.divider()

        if is_early_decline:
            with st.expander("🔵 1. Document Ingestion", expanded=True):
                if missing_fields:
                    st.error("**Critical fields missing from the document:**")
                    for f in missing_fields:
                        st.markdown(f"- `{f}`")
                if injection_snippets:
                    st.error("**Prompt injection detected in the document:**")
                    for snippet in injection_snippets:
                        st.code(snippet)
                    st.warning(
                        "Please remove any instruction-like text from your submission "
                        "and resubmit a clean broker document."
                    )
        else:
            with st.expander("🔵 1. Document Ingestion", expanded=False):
                ing = result.get("ingestion", {})
                st.metric("Extraction Confidence", ing.get("extraction_confidence", "?").upper())
                if ing.get("anomalies"):
                    st.write("**Anomalies detected:**")
                    for a in ing["anomalies"]:
                        st.warning(a)
                if ing.get("missing_required_fields"):
                    st.warning(f"Missing fields: {', '.join(ing['missing_required_fields'])}")
                if not ing.get("anomalies") and not ing.get("missing_required_fields"):
                    st.success("No anomalies or missing fields detected.")

            if result.get("claim_profile"):
                with st.expander("🟣 2. Claims History", expanded=False):
                    _show_claim_profile(result["claim_profile"])

            if result.get("hazard_score"):
                with st.expander("🟠 3. Hazard Evaluation", expanded=False):
                    _show_hazard_score(result["hazard_score"])

            if result.get("risk_assessment"):
                with st.expander("🔴 4. Risk Assessment", expanded=True):
                    _show_risk_assessment(result["risk_assessment"])

            if wf_status in ("AWAITING_HUMAN", "RUNNING"):
                st.markdown("""
<div style="background:#FFF8E1;border-left:6px solid #FF8F00;
            padding:18px 22px;border-radius:6px;margin:16px 0;">
  <h3 style="margin:0 0 8px 0;color:#E65100;">⏳ Awaiting Human Review</h3>
  <p style="margin:0;color:#333;">
    The AI risk assessment is complete and this submission has been placed in the
    <strong>underwriter queue</strong>. Pricing and governance will run automatically
    once you submit your decision.
  </p>
  <p style="margin:10px 0 0 0;color:#333;">
    👉 Go to <strong>Underwriter Queue</strong> in the left sidebar to review and decide.
  </p>
</div>
""", unsafe_allow_html=True)

            if result.get("pricing_output"):
                with st.expander("🟢 5. Pricing", expanded=True):
                    _show_pricing(result["pricing_output"])

            if result.get("governance_decision"):
                with st.expander("🩵 6. Governance Decision", expanded=True):
                    _show_governance(result["governance_decision"])

        st.session_state.pipeline_result_shown = True
        st.divider()
        if st.button("Submit Another Document", use_container_width=False):
            st.session_state.pipeline_result = None
            st.session_state.pipeline_error = None
            st.session_state.pipeline_result_shown = False
            st.rerun()


def page_underwriter_queue():
    st.title("Underwriter Review Queue")

    for _k, _v in [
        ("dec_running_id", None),
        ("dec_params", None),
        ("dec_result", None),
        ("dec_submission_ref", None),
        ("queue_page", 1),
    ]:
        if _k not in st.session_state:
            st.session_state[_k] = _v

    top_status = st.empty()
    top_progress = st.empty()

    # ── Decision processing (same pattern as Submit Document) ─────────────────
    if st.session_state.dec_running_id:
        queue_id = st.session_state.dec_running_id
        params = st.session_state.dec_params

        top_status.info("🚀  Processing your decision — please wait. Do not close this page.")
        top_progress.progress(2)

        result_holder: dict = {}

        def _call_decision():
            try:
                r = httpx.post(
                    f"{API_BASE}/queue/{queue_id}/decision",
                    json=params,
                    timeout=TIMEOUT,
                )
                if not r.is_success:
                    try:
                        detail = r.json().get("detail", r.text[:300])
                    except Exception:
                        detail = r.text[:300]
                    result_holder["error"] = f"HTTP {r.status_code}: {detail}"
                else:
                    result_holder["data"] = r.json()
            except Exception as e:
                result_holder["error"] = str(e)

        thread = threading.Thread(target=_call_decision, daemon=True)
        thread.start()

        tick = 0
        while thread.is_alive():
            # First ~20 ticks show Pricing active, then Governance
            active = [4] if tick < 20 else [5]
            pct = min(5 + tick * 4, 92)
            top_status.markdown(_render_pipeline_progress(active), unsafe_allow_html=True)
            top_progress.progress(pct)
            time.sleep(1)
            tick += 1

        thread.join()
        st.session_state.dec_running_id = None
        st.session_state.dec_params = None

        if "error" in result_holder:
            st.session_state.dec_result = {"error": result_holder["error"]}
        else:
            st.session_state.dec_result = {"data": result_holder["data"]}

        st.session_state.queue_page = 1
        st.rerun()

    # ── Decision result ───────────────────────────────────────────────────────
    if st.session_state.dec_result:
        res = st.session_state.dec_result

        if "error" in res:
            top_status.markdown(
                _render_pipeline_progress([4], final=False), unsafe_allow_html=True
            )
            top_progress.progress(100)
            st.error(f"❌  Decision failed: {res['error']}")
        else:
            final = res["data"]
            wf = final.get("workflow_status", "")
            pol = st.session_state.dec_submission_ref or final.get("submission_id", "")[:8]

            top_status.markdown(_render_pipeline_progress(6, final=True), unsafe_allow_html=True)
            top_progress.progress(100)

            if wf == "COMPLETED":
                st.success(f"✅  Decision submitted — Policy **{pol}** is fully processed.")
            elif wf == "AWAITING_SENIOR_REVIEW":
                st.warning(f"⚠️  Policy **{pol}** escalated to Senior Underwriter for final approval.")
            elif wf == "DECLINED":
                st.error(f"❌  Policy **{pol}** declined.")
            else:
                st.info(f"Decision submitted — Policy **{pol}** — Status: {wf}")

            st.divider()

            if final.get("pricing_output"):
                with st.expander("💰 5. Pricing", expanded=True):
                    _show_pricing(final["pricing_output"])
            if final.get("governance_decision"):
                with st.expander("🛡️ 6. Governance Decision", expanded=True):
                    _show_governance(final["governance_decision"])

        st.divider()
        if st.button("← Back to Queue", use_container_width=False):
            st.session_state.dec_result = None
            st.rerun()
        return

    # ── Queue list ────────────────────────────────────────────────────────────
    if "queue_page" not in st.session_state:
        st.session_state.queue_page = 1

    col_refresh, _ = st.columns([1, 5])
    if col_refresh.button("Refresh"):
        st.session_state.queue_page = 1
        st.rerun()

    try:
        r = httpx.get(f"{API_BASE}/queue", params={"page": st.session_state.queue_page}, timeout=10)
        r.raise_for_status()
        payload = r.json()
    except Exception as e:
        st.error(f"Could not load queue: {e}")
        return

    queue_items = payload.get("items", [])
    total = payload.get("total", 0)
    total_pages = payload.get("total_pages", 1)
    page = payload.get("page", 1)

    if total == 0:
        st.info("No submissions pending review.")
        return

    st.write(f"**{total} item(s) pending review** — Page {page} of {total_pages}")

    for item in queue_items:
        ra = item.get("risk_assessment") or {}
        decision = ra.get("risk_decision", "?")
        score = ra.get("risk_score", 0)
        colour = _risk_colour(decision)
        priority_icon = "🔴" if item["priority"] == "HIGH" else "🟡"

        with st.expander(
            f"{priority_icon} {item.get('submission_ref', item['submission_id'][:8])} — "
            f":{colour}[{decision}] (score {score:.2f}) — "
            f"SLA: {item['sla_deadline'][:10]}",
            expanded=False,
        ):
            extracted = item.get("extracted_data") or {}

            st.subheader("Submission Details")
            col1, col2, col3 = st.columns(3)
            col1.write(f"**Insured:** {extracted.get('insured_name', 'N/A')}")
            col2.write(f"**Class:** {item.get('class_of_business', 'N/A')}")
            col3.write(f"**Jurisdiction:** {item.get('jurisdiction', 'N/A')}")
            col4, col5 = st.columns(2)
            col4.write(f"**Risk address:** {extracted.get('risk_address', 'N/A')}")
            col5.write(f"**Sum insured:** {extracted.get('sum_insured_currency', '')} {extracted.get('sum_insured', 'N/A')}")

            with st.expander("Risk Assessment (AI)", expanded=True):
                _show_risk_assessment(ra)

            st.subheader("Your Decision")

            with st.form(key=f"decision_{item['queue_id']}"):
                underwriter_id = st.text_input("Underwriter ID", value="UW-001")
                action = st.selectbox(
                    "Action",
                    ["APPROVE", "APPROVE_WITH_CONDITIONS", "OVERRIDE", "DECLINE",
                     "REQUEST_MORE_DOCUMENTS", "REQUEST_MORE_CLAIMS_DATA", "ESCALATE_TO_SENIOR"],
                )
                col_a, col_b = st.columns(2)
                override_score = col_a.number_input(
                    "Override risk score (optional)", min_value=0.0, max_value=1.0,
                    value=float(score), step=0.01,
                )
                override_reason = col_b.text_input("Override reason", placeholder="Required if overriding AI score")
                conditions_raw = st.text_area("Conditions (one per line)", height=80,
                    placeholder="e.g. Annual risk survey required within 90 days")
                exclusions_raw = st.text_area("Exclusions (one per line)", height=60,
                    placeholder="e.g. Flood damage excluded")
                notes = st.text_area("Notes", height=60)
                decide = st.form_submit_button("Submit Decision", type="primary", use_container_width=True)

            if decide:
                conditions = [c.strip() for c in conditions_raw.splitlines() if c.strip()]
                exclusions = [e.strip() for e in exclusions_raw.splitlines() if e.strip()]
                st.session_state.dec_running_id = item["queue_id"]
                st.session_state.dec_submission_ref = item.get("submission_ref") or item["submission_id"][:8]
                st.session_state.dec_params = {
                    "underwriter_id": underwriter_id,
                    "action": action,
                    "override_risk_score": override_score if override_reason else None,
                    "override_reason": override_reason or None,
                    "conditions": conditions,
                    "exclusions": exclusions,
                    "notes": notes,
                }
                st.rerun()

    # ── Page navigation ───────────────────────────────────────────────────────
    if total_pages > 1:
        st.divider()
        nav_cols = st.columns([1, 2, 1])
        if nav_cols[0].button("← Previous", disabled=(page <= 1)):
            st.session_state.queue_page = page - 1
            st.rerun()
        nav_cols[1].markdown(
            f"<div style='text-align:center;padding-top:6px;'>Page {page} of {total_pages}</div>",
            unsafe_allow_html=True,
        )
        if nav_cols[2].button("Next →", disabled=(page >= total_pages)):
            st.session_state.queue_page = page + 1
            st.rerun()


def page_cost_dashboard():
    _cost_dashboard_main()


def page_submission_lookup():
    st.subheader("Submission Lookup")
    st.caption("Enter the policy number shown after submitting a document (e.g. P0001234PPY)")

    policy_input = st.text_input("Policy Number", placeholder="e.g. P0001234PPY")

    if st.button("Lookup", type="primary") and policy_input.strip():
        try:
            resp = httpx.get(f"{API_BASE}/submissions/{policy_input.strip()}", timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                st.error(f"No submission found for policy number: {policy_input.strip()}")
            else:
                st.error(f"API error: {e.response.text[:300]}")
            st.stop()
        except Exception as e:
            st.error(f"Connection error: {e}")
            st.stop()

        wf_status = data.get("status", "?")
        colour = _status_colour(wf_status)
        col1, col2, col3 = st.columns(3)
        col1.metric("Policy Number", data.get("submission_ref", "N/A"))
        col2.metric("Class of Business", (data.get("class_of_business") or "N/A").title())
        col3.metric("Jurisdiction", data.get("jurisdiction", "N/A"))
        st.markdown(f"**Status:** :{colour}[**{wf_status}**]")
        st.write(f"**Received:** {data.get('received_at', 'N/A')}")
        st.write(f"**Extraction confidence:** {(data.get('extraction_confidence') or 'N/A').upper()}")
        if data.get("anomalies"):
            st.warning(f"Anomalies: {', '.join(data['anomalies'])}")
        if data.get("missing_required_fields"):
            st.warning(f"Missing fields: {', '.join(data['missing_required_fields'])}")
        if data.get("extracted_data"):
            with st.expander("Extracted Data", expanded=False):
                st.json(data["extracted_data"])


# ── Audit Trail page ─────────────────────────────────────────────────────────

_AUDIT_COLOURS = {
    "DOCUMENT_INGESTED":        "#1565C0",
    "CLAIMS_PROFILE_GENERATED": "#6A1B9A",
    "HAZARD_EVALUATED":         "#E65100",
    "RISK_ASSESSED":            "#B71C1C",
    "RISK_ASSESSED_PRE_SCREEN": "#B71C1C",
    "UNDERWRITER_DECISION":     "#F57F17",
    "PRICING_CALCULATED":       "#1B5E20",
    "GOVERNANCE_DECISION":      "#00695C",
}

_DECISION_COLOURS = {
    "ACCEPT": "green", "DECLINE": "red", "REFER": "orange",
    "APPROVED": "green", "REJECTED": "red", "REFER_TO_SENIOR_UNDERWRITER": "orange",
    "APPROVE": "green", "OVERRIDE": "orange",
    "high": "green", "medium": "orange", "low": "red",
    "LOW": "green", "MODERATE": "orange", "HIGH": "red", "EXTREME": "red",
    "CUSTOMER_HISTORY": "green", "BENCHMARK": "blue",
}


def page_audit_trail():
    st.title("Audit Trail")
    st.caption(
        "Immutable decision log — every agent decision for a submission, "
        "hash-chained for tamper detection."
    )

    policy_input = st.text_input("Policy Number or Submission ID", placeholder="e.g. P0001234PPY")

    if not (st.button("Load Audit Trail", type="primary") and policy_input.strip()):
        return

    # Resolve policy number → submission ID via the submissions API
    try:
        resp = httpx.get(f"{API_BASE}/submissions/{policy_input.strip()}", timeout=10)
        if resp.status_code == 404:
            st.error(f"No submission found for: {policy_input.strip()}")
            return
        resp.raise_for_status()
        sub_data = resp.json()
        submission_id = sub_data.get("submission_id") or sub_data.get("id")
        policy_ref = sub_data.get("submission_ref", policy_input.strip())
    except Exception as e:
        st.error(f"Could not resolve submission: {e}")
        return

    # Fetch audit entries via API
    try:
        audit_resp = httpx.get(f"{API_BASE}/audit/{submission_id}", timeout=10)
        audit_resp.raise_for_status()
        entries = audit_resp.json()
    except Exception as e:
        st.error(f"Could not load audit trail: {e}")
        return

    if not entries:
        st.warning("No audit entries found for this submission yet.")
        return

    st.divider()
    st.subheader(f"Audit Trail — {policy_ref}")
    st.write(f"**{len(entries)} agent decision(s) recorded**")

    # Hash chain verification
    chain_ok = True
    for i, entry in enumerate(entries):
        if i == 0:
            continue
        if entry.get("previous_hash") != entries[i - 1].get("entry_hash"):
            chain_ok = False
            break

    if chain_ok:
        st.success("Hash chain intact — audit trail has not been tampered with.")
    else:
        st.error("Hash chain broken — one or more entries may have been modified.")

    st.divider()

    for entry in entries:
        event = entry.get("event_type", "?")
        agent = entry.get("agent_name", "?")
        decision = entry.get("decision_value", "")
        ts = entry.get("timestamp", "")[:19].replace("T", " ")
        conf = entry.get("confidence_score")
        colour = _AUDIT_COLOURS.get(event, "#555")
        dec_colour = _DECISION_COLOURS.get(decision, "gray")

        header = (
            f'<span style="background:{colour};color:white;padding:3px 10px;'
            f'border-radius:12px;font-size:0.85rem;font-weight:600;">{event}</span>'
            f'&nbsp;&nbsp;<b>{agent}</b>'
            f'&nbsp;&nbsp;:{dec_colour}[**{decision}**]'
            + (f"&nbsp;&nbsp;conf: **{conf:.2f}**" if conf else "")
            + f"&nbsp;&nbsp;<small style='color:#888;'>{ts}</small>"
        )

        with st.expander(f"{event} — {agent} — {decision}", expanded=False):
            st.markdown(header, unsafe_allow_html=True)
            cols = st.columns(2)
            cols[0].write(f"**Event:** {event}")
            cols[0].write(f"**Agent:** {agent}")
            cols[0].write(f"**Decision:** {decision}")
            cols[1].write(f"**Confidence:** {f'{conf:.2f}' if conf else 'N/A'}")
            cols[1].write(f"**Timestamp:** {ts}")
            if entry.get("underwriter_id"):
                cols[1].write(f"**Underwriter:** {entry['underwriter_id']}")
            if entry.get("decision_rationale"):
                st.write(f"**Rationale:** {entry['decision_rationale']}")
            if entry.get("override_reason"):
                st.warning(f"**Override reason:** {entry['override_reason']}")
            st.caption(f"Entry hash: `{entry.get('entry_hash', 'N/A')}`")
            st.caption(f"Previous hash: `{entry.get('previous_hash', 'N/A') or 'first entry'}`")
            if entry.get("parsed_output"):
                with st.expander("Full agent output (JSON)", expanded=False):
                    st.json(entry["parsed_output"])


# ── Navigation ────────────────────────────────────────────────────────────────


pg = st.navigation([
    st.Page(page_how_it_works,      title="How It Works",           icon="ℹ️"),
    st.Page(page_submit_document,   title="Submit Document",         icon="📄"),
    st.Page(page_underwriter_queue, title="Underwriter Review Queue", icon="📋"),
    st.Page(page_submission_lookup, title="Submission Lookup",       icon="🔍"),
    st.Page(page_audit_trail,       title="Audit Trail",             icon="🔒"),
    st.Page(page_cost_dashboard,    title="LLM Cost Dashboard",      icon="💰"),
])
pg.run()
