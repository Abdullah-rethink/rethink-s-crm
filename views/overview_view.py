import streamlit as st
import plotly.express as px
import pandas as pd
from config.settings import PLOTLY_COLORS
from components.metrics import format_currency

def render_overview_tab(df, col_amount, col_campaign, col_heading, col_date, currency_symbol):
    """Renders Executive Overview tab charts and timeline visualizations."""
    st.subheader("📊 Executive Overview & Campaign Dynamics")
    
    col_chart1, col_chart2 = st.columns([6, 4])
    
    with col_chart1:
        st.markdown("**Fundraising Volume & Transaction Timeline (UTC)**")
        if col_date in df.columns and not df[col_date].dropna().empty:
            df_time = df.set_index(col_date).resample('D')[col_amount].agg(['sum', 'count']).reset_index()
            df_time.columns = [col_date, 'Total Raised', 'Donation Count']
            
            fig_time = px.line(
                df_time, x=col_date, y='Total Raised',
                hover_data=['Donation Count'],
                color_discrete_sequence=['#38BDF8']
            )
            fig_time.update_traces(line=dict(width=2.5))
            fig_time.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font=dict(color='#94A3B8'),
                margin=dict(l=10, r=10, t=10, b=10),
                xaxis=dict(gridcolor='rgba(255,255,255,0.05)'),
                yaxis=dict(gridcolor='rgba(255,255,255,0.05)', tickprefix=currency_symbol)
            )
            st.plotly_chart(fig_time, use_container_width=True)
        else:
            st.info("No timeline date data available.")
            
    with col_chart2:
        st.markdown("**Category Distribution (Headings)**")
        if col_heading in df.columns and not df[col_heading].dropna().empty:
            df_head = df.groupby(col_heading)[col_amount].sum().reset_index()
            df_head = df_head.sort_values(by=col_amount, ascending=False).head(7)
            
            fig_pie = px.pie(
                df_head, names=col_heading, values=col_amount,
                color_discrete_sequence=PLOTLY_COLORS,
                hole=0.45
            )
            fig_pie.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font=dict(color='#94A3B8'),
                margin=dict(l=10, r=10, t=10, b=10),
                legend=dict(orientation="h", y=-0.1)
            )
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("No heading category data available.")
            
    st.markdown('<hr class="custom-divider">', unsafe_allow_html=True)
    
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        st.markdown("**Top 10 Campaigns by Total Raised**")
        if col_campaign in df.columns:
            df_camp = df.groupby(col_campaign)[col_amount].sum().reset_index()
            df_camp = df_camp.sort_values(by=col_amount, ascending=True).tail(10)
            
            fig_camp = px.bar(
                df_camp, y=col_campaign, x=col_amount, orientation='h',
                color_discrete_sequence=['#8B5CF6']
            )
            fig_camp.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font=dict(color='#94A3B8'),
                margin=dict(l=10, r=10, t=10, b=10),
                xaxis=dict(gridcolor='rgba(255,255,255,0.05)', tickprefix=currency_symbol),
                yaxis=dict(gridcolor='rgba(255,255,255,0.05)')
            )
            st.plotly_chart(fig_camp, use_container_width=True)

    with col_c2:
        st.markdown("**Sub-Heading Performance**")
        if "Sub-Heading" in df.columns and not df["Sub-Heading"].dropna().empty:
            df_sub = df.groupby("Sub-Heading")[col_amount].sum().reset_index()
            df_sub = df_sub.sort_values(by=col_amount, ascending=True).tail(10)
            
            fig_sub = px.bar(
                df_sub, y="Sub-Heading", x=col_amount, orientation='h',
                color_discrete_sequence=['#10B981']
            )
            fig_sub.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font=dict(color='#94A3B8'),
                margin=dict(l=10, r=10, t=10, b=10),
                xaxis=dict(gridcolor='rgba(255,255,255,0.05)', tickprefix=currency_symbol),
                yaxis=dict(gridcolor='rgba(255,255,255,0.05)')
            )
            st.plotly_chart(fig_sub, use_container_width=True)
