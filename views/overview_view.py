import plotly.express as px
import streamlit as st

from config.settings import PLOTLY_COLORS


def render_overview_tab(df, col_amount, col_campaign, col_heading, col_date, currency_symbol):
    """Renders Executive Overview tab charts and timeline visualizations with glassmorphic cards."""
    st.subheader("📊 Executive Overview & Campaign Dynamics")
    st.markdown("<br>", unsafe_allow_html=True)

    col_chart1, col_chart2 = st.columns([6, 4])

    with col_chart1:
        st.markdown("""
        <div class="glass-panel" style="padding: 18px 20px; border-left: 4px solid #38BDF8;">
            <div style="font-weight: 700; color: #F8FAFC; font-size: 1.05rem; margin-bottom: 10px;">📈 Fundraising Volume & Transaction Timeline (UTC)</div>
        </div>
        """, unsafe_allow_html=True)
        if col_date in df.columns and not df[col_date].dropna().empty:
            df_time = df.set_index(col_date).resample('D')[col_amount].agg(['sum', 'count']).reset_index()
            df_time.columns = [col_date, 'Total Raised', 'Donation Count']

            fig_time = px.line(
                df_time, x=col_date, y='Total Raised',
                hover_data=['Donation Count'],
                color_discrete_sequence=['#38BDF8']
            )
            fig_time.update_traces(
                line={"width": 2.5},
                hovertemplate=f"<b>Date:</b> %{{x}}<br><b>Total Raised:</b> {currency_symbol}%{{y:,.2f}}<br><b>Donations:</b> %{{customdata[0]:,}}<extra></extra>"
            )
            fig_time.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font={"color": '#94A3B8'},
                margin={"l": 10, "r": 10, "t": 10, "b": 10},
                xaxis={"gridcolor": 'rgba(255,255,255,0.05)'},
                yaxis={"gridcolor": 'rgba(255,255,255,0.05)', "tickprefix": currency_symbol}
            )
            st.plotly_chart(fig_time, use_container_width=True)
        else:
            st.info("No timeline date data available.")

    with col_chart2:
        st.markdown("""
        <div class="glass-panel" style="padding: 18px 20px; border-left: 4px solid #8B5CF6;">
            <div style="font-weight: 700; color: #F8FAFC; font-size: 1.05rem; margin-bottom: 10px;">🍩 Category Distribution (Headings)</div>
        </div>
        """, unsafe_allow_html=True)
        if col_heading in df.columns and not df[col_heading].dropna().empty:
            df_head = df.groupby(col_heading)[col_amount].sum().reset_index()
            df_head = df_head.sort_values(by=col_amount, ascending=False).head(7)

            fig_pie = px.pie(
                df_head, names=col_heading, values=col_amount,
                color_discrete_sequence=PLOTLY_COLORS,
                hole=0.45
            )
            fig_pie.update_traces(
                hovertemplate=f"<b>Category:</b> %{{label}}<br><b>Raised:</b> {currency_symbol}%{{value:,.2f}} (%{{percent}})<extra></extra>"
            )
            fig_pie.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font={"color": '#94A3B8'},
                margin={"l": 10, "r": 10, "t": 10, "b": 10},
                legend={"orientation": "h", "y": -0.1}
            )
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("No heading category data available.")

    st.markdown('<hr class="custom-divider">', unsafe_allow_html=True)

    col_c1, col_c2 = st.columns(2)
    with col_c1:
        st.markdown("""
        <div class="glass-panel" style="padding: 18px 20px; border-left: 4px solid #10B981;">
            <div style="font-weight: 700; color: #F8FAFC; font-size: 1.05rem; margin-bottom: 10px;">🏆 Top 10 Campaigns by Total Raised</div>
        </div>
        """, unsafe_allow_html=True)
        if col_campaign in df.columns:
            df_camp = df.groupby(col_campaign)[col_amount].sum().reset_index()
            df_camp = df_camp.sort_values(by=col_amount, ascending=True).tail(10)

            fig_camp = px.bar(
                df_camp, y=col_campaign, x=col_amount, orientation='h',
                color_discrete_sequence=['#10B981']
            )
            fig_camp.update_traces(
                hovertemplate=f"<b>Campaign:</b> %{{y}}<br><b>Total Raised:</b> {currency_symbol}%{{x:,.2f}}<extra></extra>"
            )
            fig_camp.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font={"color": '#94A3B8'},
                margin={"l": 10, "r": 10, "t": 10, "b": 10},
                xaxis={"gridcolor": 'rgba(255,255,255,0.05)', "tickprefix": currency_symbol},
                yaxis={"gridcolor": 'rgba(255,255,255,0.05)'}
            )
            st.plotly_chart(fig_camp, use_container_width=True)

    with col_c2:
        st.markdown("""
        <div class="glass-panel" style="padding: 18px 20px; border-left: 4px solid #EC4899;">
            <div style="font-weight: 700; color: #F8FAFC; font-size: 1.05rem; margin-bottom: 10px;">🏷️ Sub-Heading Performance</div>
        </div>
        """, unsafe_allow_html=True)
        if "Sub-Heading" in df.columns and not df["Sub-Heading"].dropna().empty:
            df_sub = df.groupby("Sub-Heading")[col_amount].sum().reset_index()
            df_sub = df_sub.sort_values(by=col_amount, ascending=True).tail(10)

            fig_sub = px.bar(
                df_sub, y="Sub-Heading", x=col_amount, orientation='h',
                color_discrete_sequence=['#EC4899']
            )
            fig_sub.update_traces(
                hovertemplate=f"<b>Sub-Heading:</b> %{{y}}<br><b>Total Raised:</b> {currency_symbol}%{{x:,.2f}}<extra></extra>"
            )
            fig_sub.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font={"color": '#94A3B8'},
                margin={"l": 10, "r": 10, "t": 10, "b": 10},
                xaxis={"gridcolor": 'rgba(255,255,255,0.05)', "tickprefix": currency_symbol},
                yaxis={"gridcolor": 'rgba(255,255,255,0.05)'}
            )
            st.plotly_chart(fig_sub, use_container_width=True)
