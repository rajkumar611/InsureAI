"""
QBE AI Underwriting — Underwriter UI

Run with:
    uv run streamlit run streamlit_app.py
"""
from __future__ import annotations

import json
import os

import httpx
import streamlit as st

API_BASE = os.getenv("API_BASE", "http://localhost:8081/api/v1")
TIMEOUT = 300  # seconds — pipeline can take 2-3 minutes

st.set_page_config(
    page_title="QBE AI Underwriting",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Sidebar navigation ────────────────────────────────────────────────────────

st.sidebar.title("QBE AI Underwriting")
st.sidebar.caption("Enterprise Multi-Agent System")
page = st.sidebar.radio(
    "Navigation",
    ["Submit Document", "Underwriter Queue", "Submission Lookup"],
    index=0,
)
st.sidebar.divider()
st.sidebar.caption(f"API: `{API_BASE}`")


# ── Shared helpers ────────────────────────────────────────────────────────────

def _badge(text: str, colour: str) -> str:
    return f":{colour}[**{text}**]"


def _risk_colour(decision: str) -> str:
    return {"ACCEPT": "green", "REFER": "orange", "DECLINE": "red"}.get(decision, "gray")


def _status_colour(status: str) -> str:
    mapping = {
        "COMPLETED": "green", "DECLINED": "red",
        "AWAITING_SENIOR_REVIEW": "orange", "GOVERNANCE_REJECTED": "red",
        "RUNNING": "blue", "AWAITING_HUMAN": "orange",
        "INGESTED": "green", "INGESTION_FAILED": "red",
    }
    return mapping.get(status, "gray")


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

    if po.get("claims_loadings"):
        st.write("**Claims loadings:**")
        for l in po["claims_loadings"]:
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


# ── Page: Submit Document ─────────────────────────────────────────────────────

if page == "Submit Document":
    st.title("Submit Broker Document")
    st.caption("Paste the broker document text below. The AI pipeline will extract, analyse, and return a risk decision.")

    with st.form("submit_form"):
        col1, col2, col3 = st.columns(3)
        submission_ref = col1.text_input("Submission Reference", value="SUB-2025-NEW-001")
        class_of_business = col2.selectbox(
            "Class of Business", ["property", "liability", "marine", "motor", "specialty"]
        )
        jurisdiction = col3.selectbox("Jurisdiction", ["NZ", "AU"])

        document_content = st.text_area(
            "Broker Document (paste full text)",
            height=300,
            placeholder="Paste the broker submission document here...",
        )

        submitted = st.form_submit_button("Run Full Pipeline", type="primary", use_container_width=True)

    if submitted:
        if not document_content.strip():
            st.error("Please paste a broker document before submitting.")
        else:
            with st.spinner("Running AI pipeline (this takes 1-3 minutes)..."):
                try:
                    resp = httpx.post(
                        f"{API_BASE}/submissions/pipeline",
                        json={
                            "submission_ref": submission_ref,
                            "class_of_business": class_of_business,
                            "jurisdiction": jurisdiction,
                            "document_content": document_content,
                        },
                        timeout=TIMEOUT,
                    )
                    resp.raise_for_status()
                    result = resp.json()
                except httpx.HTTPStatusError as e:
                    st.error(f"API error {e.response.status_code}: {e.response.text[:500]}")
                    st.stop()
                except Exception as e:
                    st.error(f"Connection error: {e}")
                    st.stop()

            st.success(f"Pipeline complete — Submission ID: `{result['submission_id']}`")

            wf_status = result.get("workflow_status", "?")
            colour = _status_colour(wf_status)
            st.markdown(f"**Workflow status:** :{colour}[**{wf_status}**]")

            # Ingestion summary
            with st.expander("Document Ingestion", expanded=False):
                ing = result.get("ingestion", {})
                st.metric("Confidence", ing.get("extraction_confidence", "?"))
                if ing.get("anomalies"):
                    st.write("**Anomalies:**")
                    for a in ing["anomalies"]:
                        st.warning(a)
                if ing.get("missing_required_fields"):
                    st.write("**Missing fields:**", ", ".join(ing["missing_required_fields"]))

            # Claims profile
            if result.get("claim_profile"):
                with st.expander("Claims History Profile", expanded=False):
                    _show_claim_profile(result["claim_profile"])

            # Hazard score
            if result.get("hazard_score"):
                with st.expander("Hazard Evaluation", expanded=False):
                    _show_hazard_score(result["hazard_score"])

            # Risk assessment — always expanded
            if result.get("risk_assessment"):
                with st.expander("Risk Assessment", expanded=True):
                    _show_risk_assessment(result["risk_assessment"])

            if wf_status == "RUNNING":
                st.info("This submission has been queued for underwriter review. Go to **Underwriter Queue** to action it.")

            if result.get("pricing_output"):
                with st.expander("Pricing", expanded=True):
                    _show_pricing(result["pricing_output"])

            if result.get("governance_decision"):
                with st.expander("Governance Decision", expanded=True):
                    _show_governance(result["governance_decision"])


# ── Page: Underwriter Queue ───────────────────────────────────────────────────

elif page == "Underwriter Queue":
    st.title("Underwriter Review Queue")

    col_refresh, _ = st.columns([1, 5])
    if col_refresh.button("Refresh"):
        st.rerun()

    try:
        resp = httpx.get(f"{API_BASE}/queue", timeout=10)
        resp.raise_for_status()
        queue_items = resp.json()
    except Exception as e:
        st.error(f"Could not load queue: {e}")
        queue_items = []

    if not queue_items:
        st.info("No submissions pending review.")
    else:
        st.write(f"**{len(queue_items)} item(s) pending review**")

        for item in queue_items:
            ra = item.get("risk_assessment") or {}
            decision = ra.get("risk_decision", "?")
            score = ra.get("risk_score", 0)
            colour = _risk_colour(decision)
            priority_icon = "🔴" if item["priority"] == "HIGH" else "🟡"

            with st.expander(
                f"{priority_icon} `{item['submission_id'][:8]}...` — "
                f":{colour}[{decision}] (score {score:.2f}) — "
                f"SLA: {item['sla_deadline'][:10]}",
                expanded=False,
            ):
                # Load full details
                try:
                    detail_resp = httpx.get(f"{API_BASE}/queue/{item['queue_id']}", timeout=10)
                    detail_resp.raise_for_status()
                    detail = detail_resp.json()
                except Exception as e:
                    st.error(f"Could not load details: {e}")
                    continue

                sub = detail.get("submission") or {}
                extracted = sub.get("extracted_data") or {}

                st.subheader("Submission Details")
                col1, col2, col3 = st.columns(3)
                col1.write(f"**Insured:** {extracted.get('insured_name', 'N/A')}")
                col2.write(f"**Class:** {sub.get('class_of_business', 'N/A')}")
                col3.write(f"**Jurisdiction:** {sub.get('jurisdiction', 'N/A')}")

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
                    override_reason = col_b.text_input(
                        "Override reason", placeholder="Required if overriding AI score"
                    )
                    conditions_raw = st.text_area(
                        "Conditions (one per line)",
                        placeholder="e.g. Annual risk survey required within 90 days",
                        height=80,
                    )
                    exclusions_raw = st.text_area(
                        "Exclusions (one per line)", height=60,
                        placeholder="e.g. Flood damage excluded"
                    )
                    notes = st.text_area("Notes", height=60)

                    decide = st.form_submit_button("Submit Decision", type="primary", use_container_width=True)

                if decide:
                    conditions = [c.strip() for c in conditions_raw.splitlines() if c.strip()]
                    exclusions = [e.strip() for e in exclusions_raw.splitlines() if e.strip()]
                    with st.spinner("Submitting decision and resuming pipeline..."):
                        try:
                            dec_resp = httpx.post(
                                f"{API_BASE}/queue/{item['queue_id']}/decision",
                                json={
                                    "underwriter_id": underwriter_id,
                                    "action": action,
                                    "override_risk_score": override_score if override_reason else None,
                                    "override_reason": override_reason or None,
                                    "conditions": conditions,
                                    "exclusions": exclusions,
                                    "notes": notes,
                                },
                                timeout=TIMEOUT,
                            )
                            dec_resp.raise_for_status()
                            final = dec_resp.json()
                        except httpx.HTTPStatusError as e:
                            st.error(f"API error: {e.response.text[:300]}")
                            st.stop()
                        except Exception as e:
                            st.error(f"Error: {e}")
                            st.stop()

                    st.success(f"Decision submitted! Workflow status: **{final.get('workflow_status')}**")

                    if final.get("pricing_output"):
                        with st.expander("Pricing Result", expanded=True):
                            _show_pricing(final["pricing_output"])

                    if final.get("governance_decision"):
                        with st.expander("Governance Decision", expanded=True):
                            _show_governance(final["governance_decision"])


# ── Page: Submission Lookup ───────────────────────────────────────────────────

elif page == "Submission Lookup":
    st.title("Submission Lookup")

    submission_id = st.text_input("Submission ID (UUID)", placeholder="Paste the submission UUID here")

    if st.button("Lookup", type="primary") and submission_id.strip():
        try:
            resp = httpx.get(f"{API_BASE}/submissions/{submission_id.strip()}", timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                st.error("Submission not found.")
            else:
                st.error(f"API error: {e.response.text[:300]}")
            st.stop()
        except Exception as e:
            st.error(f"Connection error: {e}")
            st.stop()

        wf_status = data.get("status", "?")
        colour = _status_colour(wf_status)
        st.markdown(f"**Status:** :{colour}[**{wf_status}**]")
        st.write(f"**Submission ref:** {data.get('submission_ref', 'N/A')}")
        st.write(f"**Received:** {data.get('received_at', 'N/A')}")
        st.write(f"**Extraction confidence:** {data.get('extraction_confidence', 'N/A')}")

        if data.get("extracted_data"):
            with st.expander("Extracted Data", expanded=False):
                st.json(data["extracted_data"])

        if data.get("anomalies"):
            st.write("**Anomalies:**")
            for a in data["anomalies"]:
                st.warning(a)

        if data.get("missing_required_fields"):
            st.write("**Missing fields:**", ", ".join(data["missing_required_fields"]))
