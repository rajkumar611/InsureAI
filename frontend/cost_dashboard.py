"""
LLM Cost Dashboard — run with:
    uv run streamlit run frontend/cost_dashboard.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend", "src"))

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://qbe:localdev@localhost:5432/aus_underwriting",
).replace("+asyncpg", "+psycopg")  # streamlit uses sync psycopg3 driver


@st.cache_data(ttl=30)
def load_cost_data() -> pd.DataFrame:
    engine = create_engine(DATABASE_URL)
    query = """
        SELECT
            agent_name,
            model_id,
            class_of_business,
            jurisdiction,
            feature_tag,
            input_tokens,
            output_tokens,
            cost_usd,
            timestamp::date AS date
        FROM cost_ledger
        ORDER BY timestamp DESC
        LIMIT 10000
    """
    with engine.connect() as conn:
        return pd.read_sql(text(query), conn)


def main() -> None:
    st.title("INSUREAI — LLM Cost Dashboard")

    try:
        df = load_cost_data()
    except Exception as e:
        st.error(f"Could not connect to database: {e}")
        st.info("Start Postgres with: docker compose up postgres -d")
        return

    if df.empty:
        st.warning("No cost data yet. Run the pipeline to generate LLM calls.")
        return

    df["cost_usd"] = df["cost_usd"].astype(float)

    # ── KPI row ──────────────────────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Spend (USD)", f"${df['cost_usd'].sum():.4f}")
    col2.metric("Total LLM Calls", f"{len(df):,}")
    col3.metric("Total Input Tokens", f"{df['input_tokens'].sum():,}")
    col4.metric("Total Output Tokens", f"{df['output_tokens'].sum():,}")

    st.divider()

    # ── Cost by agent ─────────────────────────────────────────────────────────
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("Cost by Agent")
        by_agent = (
            df.groupby("agent_name")["cost_usd"]
            .sum()
            .sort_values(ascending=False)
            .reset_index()
        )
        by_agent.columns = ["Agent", "Total Cost (USD)"]
        by_agent["Total Cost (USD)"] = by_agent["Total Cost (USD)"].map("${:.4f}".format)
        st.dataframe(by_agent, use_container_width=True, hide_index=True)

    with col_b:
        st.subheader("Cost by Model")
        by_model = (
            df.groupby("model_id")["cost_usd"]
            .sum()
            .sort_values(ascending=False)
            .reset_index()
        )
        by_model.columns = ["Model", "Total Cost (USD)"]
        by_model["Total Cost (USD)"] = by_model["Total Cost (USD)"].map("${:.4f}".format)
        st.dataframe(by_model, use_container_width=True, hide_index=True)

    st.divider()

    # ── Daily spend trend ─────────────────────────────────────────────────────
    st.subheader("Daily Spend Trend (USD)")
    daily = df.groupby("date")["cost_usd"].sum().reset_index()
    daily.columns = ["Date", "Cost (USD)"]
    st.line_chart(daily.set_index("Date"))

    st.divider()

    # ── Cost by class of business ─────────────────────────────────────────────
    col_c, col_d = st.columns(2)

    with col_c:
        st.subheader("Cost by Class of Business")
        by_class = (
            df.groupby("class_of_business")["cost_usd"]
            .sum()
            .sort_values(ascending=False)
            .reset_index()
        )
        by_class.columns = ["Class", "Total Cost (USD)"]
        st.bar_chart(by_class.set_index("Class"))

    with col_d:
        st.subheader("Cost by Jurisdiction")
        by_jur = (
            df.groupby("jurisdiction")["cost_usd"]
            .sum()
            .sort_values(ascending=False)
            .reset_index()
        )
        by_jur.columns = ["Jurisdiction", "Total Cost (USD)"]
        st.bar_chart(by_jur.set_index("Jurisdiction"))

    st.divider()

    # ── Token efficiency ──────────────────────────────────────────────────────
    st.subheader("Token Efficiency by Agent")
    efficiency = df.groupby("agent_name").agg(
        avg_input=("input_tokens", "mean"),
        avg_output=("output_tokens", "mean"),
        avg_cost=("cost_usd", "mean"),
        calls=("cost_usd", "count"),
    ).reset_index()
    efficiency.columns = ["Agent", "Avg Input Tokens", "Avg Output Tokens", "Avg Cost (USD)", "Calls"]
    efficiency["Avg Cost (USD)"] = efficiency["Avg Cost (USD)"].map("${:.5f}".format)
    efficiency["Avg Input Tokens"] = efficiency["Avg Input Tokens"].map("{:.0f}".format)
    efficiency["Avg Output Tokens"] = efficiency["Avg Output Tokens"].map("{:.0f}".format)
    st.dataframe(efficiency, use_container_width=True, hide_index=True)

    st.divider()

    # ── Raw ledger ────────────────────────────────────────────────────────────
    with st.expander("Raw Cost Ledger (last 100 rows)"):
        display = df.head(100).copy()
        display["cost_usd"] = display["cost_usd"].map("${:.6f}".format)
        st.dataframe(display, use_container_width=True, hide_index=True)

    st.caption("Refreshes every 30 seconds. Cost data is real — sourced from Anthropic API usage.response.usage.")


if __name__ == "__main__":
    main()
