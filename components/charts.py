"""Plotly chart builders for the sector dashboard."""

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

_COLOR_SCALE = ["#d73027", "#fee08b", "#1a9850"]


def sector_heatmap(df_perf: pd.DataFrame, group_by_sector: bool = False) -> go.Figure:
    """
    Treemap heatmap of performance.
    If group_by_sector=True, df_perf must have a 'sector' column (Korean mode).
    """
    if group_by_sector and "sector" in df_perf.columns:
        path = ["sector", "name"]
    else:
        path = ["name"]

    fig = px.treemap(
        df_perf,
        path=path,
        values=[1] * len(df_perf),
        color="change_pct",
        color_continuous_scale=_COLOR_SCALE,
        color_continuous_midpoint=0,
        custom_data=["ticker", "current_price", "change_pct"],
    )
    fig.update_traces(
        texttemplate="<b>%{label}</b><br>%{customdata[2]:.2f}%",
        hovertemplate=(
            "<b>%{label}</b><br>"
            "Ticker: %{customdata[0]}<br>"
            "Price: %{customdata[1]:,.0f}<br>"
            "Change: %{customdata[2]:+.2f}%<extra></extra>"
        ),
    )
    fig.update_layout(margin=dict(t=10, l=0, r=0, b=0), coloraxis_showscale=False)
    return fig


def performance_bar(df_perf: pd.DataFrame, label_col: str = "name") -> go.Figure:
    """Horizontal bar chart of % change, colored by direction."""
    colors = ["#1a9850" if v >= 0 else "#d73027" for v in df_perf["change_pct"]]
    fig = go.Figure(go.Bar(
        x=df_perf["change_pct"],
        y=df_perf[label_col],
        orientation="h",
        marker_color=colors,
        text=[f"{v:+.2f}%" for v in df_perf["change_pct"]],
        textposition="outside",
        hovertemplate="<b>%{y}</b><br>Change: %{x:+.2f}%<extra></extra>",
    ))
    fig.update_layout(
        xaxis_title="% Change",
        yaxis=dict(autorange="reversed"),
        margin=dict(l=10, r=60, t=10, b=40),
        height=max(300, len(df_perf) * 35),
    )
    return fig


def price_history(history: dict[str, pd.DataFrame], tickers: list[str], names: dict[str, str] | None = None) -> go.Figure:
    """Normalized price history (rebased to 100) for selected tickers."""
    fig = go.Figure()
    for ticker in tickers:
        df = history.get(ticker)
        if df is None or df.empty:
            continue
        rebased = df["Close"] / df["Close"].iloc[0] * 100
        label = f"{ticker} ({names[ticker]})" if names and ticker in names else ticker
        fig.add_trace(go.Scatter(
            x=df.index,
            y=rebased,
            mode="lines",
            name=label,
            hovertemplate=f"<b>{label}</b><br>Date: %{{x|%Y-%m-%d}}<br>Rebased: %{{y:.1f}}<extra></extra>",
        ))
    fig.add_hline(y=100, line_dash="dot", line_color="gray", opacity=0.5)
    fig.update_layout(
        yaxis_title="Price (rebased to 100)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=10, r=10, t=40, b=40),
        hovermode="x unified",
    )
    return fig


def candlestick(df: pd.DataFrame, ticker: str, name: str = "") -> go.Figure:
    """OHLC candlestick chart for a single ETF or stock."""
    label = f"{ticker} — {name}" if name else ticker
    fig = go.Figure(go.Candlestick(
        x=df.index,
        open=df["Open"],
        high=df["High"],
        low=df["Low"],
        close=df["Close"],
        name=label,
    ))
    fig.update_layout(
        title=label,
        xaxis_rangeslider_visible=False,
        margin=dict(l=10, r=10, t=50, b=40),
    )
    return fig
