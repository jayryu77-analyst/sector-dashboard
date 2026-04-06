"""Plotly chart builders for the sector dashboard."""

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px


def sector_heatmap(df_perf: pd.DataFrame) -> go.Figure:
    """Treemap-style heatmap of sector performance."""
    fig = px.treemap(
        df_perf,
        path=["name"],
        values=[1] * len(df_perf),  # equal-area tiles
        color="change_pct",
        color_continuous_scale=["#d73027", "#fee08b", "#1a9850"],
        color_continuous_midpoint=0,
        custom_data=["ticker", "current_price", "change_pct"],
    )
    fig.update_traces(
        texttemplate="<b>%{label}</b><br>%{customdata[2]:.2f}%",
        hovertemplate=(
            "<b>%{label}</b><br>"
            "Ticker: %{customdata[0]}<br>"
            "Price: $%{customdata[1]:.2f}<br>"
            "Change: %{customdata[2]:+.2f}%<extra></extra>"
        ),
    )
    fig.update_layout(
        margin=dict(t=10, l=0, r=0, b=0),
        coloraxis_showscale=False,
    )
    return fig


def performance_bar(df_perf: pd.DataFrame) -> go.Figure:
    """Horizontal bar chart of sector % change, colored by direction."""
    colors = ["#1a9850" if v >= 0 else "#d73027" for v in df_perf["change_pct"]]
    fig = go.Figure(go.Bar(
        x=df_perf["change_pct"],
        y=df_perf["name"],
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
        height=400,
    )
    return fig


def price_history(history: dict[str, pd.DataFrame], tickers: list[str]) -> go.Figure:
    """Normalized price history (rebased to 100) for selected tickers."""
    fig = go.Figure()
    for ticker in tickers:
        df = history.get(ticker)
        if df is None or df.empty:
            continue
        rebased = df["Close"] / df["Close"].iloc[0] * 100
        fig.add_trace(go.Scatter(
            x=df.index,
            y=rebased,
            mode="lines",
            name=ticker,
            hovertemplate=f"<b>{ticker}</b><br>Date: %{{x|%Y-%m-%d}}<br>Rebased: %{{y:.1f}}<extra></extra>",
        ))
    fig.add_hline(y=100, line_dash="dot", line_color="gray", opacity=0.5)
    fig.update_layout(
        yaxis_title="Price (rebased to 100)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=10, r=10, t=40, b=40),
        hovermode="x unified",
    )
    return fig


def candlestick(df: pd.DataFrame, ticker: str) -> go.Figure:
    """OHLC candlestick chart for a single sector ETF."""
    fig = go.Figure(go.Candlestick(
        x=df.index,
        open=df["Open"],
        high=df["High"],
        low=df["Low"],
        close=df["Close"],
        name=ticker,
    ))
    fig.update_layout(
        title=f"{ticker} — OHLC",
        xaxis_rangeslider_visible=False,
        margin=dict(l=10, r=10, t=50, b=40),
    )
    return fig
