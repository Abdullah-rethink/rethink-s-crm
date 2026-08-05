import streamlit as st
import plotly.express as px
import pandas as pd
from config.settings import DONOR_TIER_ORDER, PLOTLY_COLORS
from components.metrics import format_currency, format_number

def render_ltv_tab(df, col_amount, currency_symbol):
    """Renders Lifetime LTV Analytics & Donor Segmentation tab."""
    st.subheader("👑 Lifetime Donor Value (LTV) & Segmentation")
    st.markdown("Donors are classified into tiers based on their **Total Lifetime Raised** across all campaigns:")

    if "Lifetime Donor Classification" in df.columns:
        ltv_summary = df.groupby("Lifetime Donor Classification").agg(
            Total_Raised=(col_amount, "sum"),
            Donation_Count=(col_amount, "count"),
            Avg_Donation=(col_amount, "mean")
        ).reset_index()

        ltv_summary["Tier_Order"] = ltv_summary["Lifetime Donor Classification"].map(
            {t: i for i, t in enumerate(DONOR_TIER_ORDER)}
        )
        ltv_summary = ltv_summary.sort_values("Tier_Order").drop(columns=["Tier_Order"])

        l1, l2 = st.columns([5, 5])
        with l1:
            st.markdown("**Revenue Contribution by Donor Tier**")
            fig_ltv_bar = px.bar(
                ltv_summary, x="Lifetime Donor Classification", y="Total_Raised",
                color="Lifetime Donor Classification",
                color_discrete_sequence=PLOTLY_COLORS,
                text_auto='.2s'
            )
            fig_ltv_bar.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font=dict(color='#94A3B8'),
                showlegend=False,
                margin=dict(l=10, r=10, t=10, b=10),
                yaxis=dict(gridcolor='rgba(255,255,255,0.05)', tickprefix=currency_symbol)
            )
            st.plotly_chart(fig_ltv_bar, use_container_width=True)

        with l2:
            st.markdown("**Donor Count Share by Tier**")
            fig_ltv_pie = px.pie(
                ltv_summary, names="Lifetime Donor Classification", values="Donation_Count",
                color_discrete_sequence=PLOTLY_COLORS,
                hole=0.45
            )
            fig_ltv_pie.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font=dict(color='#94A3B8'),
                margin=dict(l=10, r=10, t=10, b=10),
                legend=dict(orientation="h", y=-0.1)
            )
            st.plotly_chart(fig_ltv_pie, use_container_width=True)

        ltv_summary["Total_Raised"] = ltv_summary["Total_Raised"].round(2)
        ltv_summary["Avg_Donation"] = ltv_summary["Avg_Donation"].round(2)

        st.markdown('<hr class="custom-divider">', unsafe_allow_html=True)
        st.markdown("**Detailed LTV Tier Breakdown Table**")
        st.dataframe(ltv_summary, use_container_width=True, hide_index=True)
    else:
        st.info("No Lifetime Donor Classification data available.")
