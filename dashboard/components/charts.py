"""
components/charts.py
--------------------
Wrappers Plotly com tema escuro premium para o dashboard.
Paleta: tons de indigo, cyan, teal e âmbar — nada genérico.
"""

import plotly.express as px
import plotly.graph_objects as go
import polars as pl

# ---------------------------------------------------------------------------
# PALETA PREMIUM
# ---------------------------------------------------------------------------

_BG = "rgba(0,0,0,0)"
_GRID = "rgba(99, 102, 241, 0.08)"
_TEXT = "#CBD5E1"       # Texto claro e legível
_TEXT_BRIGHT = "#F1F5F9"  # Títulos e valores — quase branco
_ACCENT = "#818CF8"

# Sequência de cores calibrada — sem vermelho/verde primário genérico
PALETA = [
    "#818CF8",   # Indigo claro
    "#38BDF8",   # Sky
    "#34D399",   # Emerald
    "#FBBF24",   # Amber
    "#F472B6",   # Pink
    "#A78BFA",   # Violet
    "#22D3EE",   # Cyan
    "#FB923C",   # Orange
    "#4ADE80",   # Green
    "#E879F9",   # Fuchsia
    "#60A5FA",   # Blue
    "#2DD4BF",   # Teal
]

PALETA_SITUACAO = {
    "Ativa":      "#34D399",
    "Baixada":    "#F87171",
    "Inapta":     "#FBBF24",
    "Suspensa":   "#FB923C",
    "Nula":       "#64748B",
    "Desconhecido": "#475569",
}


# ---------------------------------------------------------------------------
# LAYOUT BASE
# ---------------------------------------------------------------------------

def _layout_base(fig: go.Figure, title: str = "", height: int | None = None) -> go.Figure:
    """Aplica tema escuro premium a qualquer gráfico."""
    fig.update_layout(
        title=dict(
            text=title,
            font=dict(size=17, color=_TEXT_BRIGHT, family="Inter, sans-serif", weight=700),
            x=0.0,
            y=0.97,
        ) if title else None,
        paper_bgcolor=_BG,
        plot_bgcolor=_BG,
        font=dict(color=_TEXT, family="Inter, sans-serif", size=14),
        margin=dict(l=16, r=24, t=48 if title else 16, b=16),
        legend=dict(
            bgcolor=_BG,
            font=dict(color=_TEXT, size=13),
            borderwidth=0,
        ),
        hoverlabel=dict(
            bgcolor="#1a1f35",
            bordercolor="rgba(99,102,241,0.3)",
            font_size=14,
            font_color=_TEXT_BRIGHT,
            font_family="Inter, sans-serif",
        ),
        height=height,
    )
    fig.update_xaxes(
        gridcolor=_GRID,
        zerolinecolor=_GRID,
        tickfont=dict(size=13, color=_TEXT),
        title_font=dict(size=14, color=_TEXT),
    )
    fig.update_yaxes(
        gridcolor=_GRID,
        zerolinecolor=_GRID,
        tickfont=dict(size=13, color=_TEXT),
        title_font=dict(size=14, color=_TEXT),
    )
    return fig


# ---------------------------------------------------------------------------
# GRÁFICOS
# ---------------------------------------------------------------------------

def donut_chart(
    df: pl.DataFrame, values: str, names: str,
    title: str = "", color_map: dict | None = None, height: int = 400,
) -> go.Figure:
    """Gráfico de rosca (donut) com estilo premium."""
    pdf = df.to_pandas()
    fig = px.pie(
        pdf, values=values, names=names,
        hole=0.6,
        color=names,
        color_discrete_map=color_map or {},
        color_discrete_sequence=PALETA,
    )
    fig.update_traces(
        textposition="outside",
        textinfo="label+percent",
        textfont_size=14,
        textfont_color=_TEXT_BRIGHT,
        marker=dict(line=dict(color="#111827", width=2)),
        pull=[0.02] * len(pdf),
    )
    return _layout_base(fig, title, height)


def bar_horizontal(
    df: pl.DataFrame, x: str, y: str,
    title: str = "", text: str | None = None, height: int = 400,
) -> go.Figure:
    """Barras horizontais com gradiente."""
    pdf = df.to_pandas()
    fig = go.Figure(go.Bar(
        x=pdf[x],
        y=pdf[y],
        orientation="h",
        text=pdf[text or x].apply(lambda v: f"{v:,.0f}".replace(",", ".") if isinstance(v, (int, float)) else v),
        textposition="outside",
        textfont=dict(size=13, color=_TEXT_BRIGHT),
        marker=dict(
            color=pdf[x],
            colorscale=[[0, "#4F46E5"], [1, "#818CF8"]],
            line=dict(width=0),
            cornerradius=4,
        ),
    ))
    fig.update_layout(yaxis=dict(autorange="reversed", title=""), xaxis=dict(title="", showticklabels=False))
    return _layout_base(fig, title, height)


def bar_vertical(
    df: pl.DataFrame, x: str, y: str,
    title: str = "", height: int = 400,
) -> go.Figure:
    """Barras verticais com cores individuais por barra."""
    pdf = df.to_pandas()
    n = len(pdf)
    colors = PALETA[:n] if n <= len(PALETA) else (PALETA * (n // len(PALETA) + 1))[:n]

    fig = go.Figure(go.Bar(
        x=pdf[x],
        y=pdf[y],
        text=pdf[y].apply(lambda v: f"{v:,.0f}".replace(",", ".") if isinstance(v, (int, float)) else v),
        textposition="outside",
        textfont=dict(size=13, color=_TEXT_BRIGHT),
        marker=dict(
            color=colors,
            line=dict(width=0),
            cornerradius=6,
        ),
    ))
    fig.update_layout(xaxis_title="", yaxis_title="")
    return _layout_base(fig, title, height)


def bar_agrupado(
    df: pl.DataFrame, x: str, y: str, color: str,
    title: str = "", height: int = 400,
) -> go.Figure:
    """Barras agrupadas (clustered)."""
    pdf = df.to_pandas()
    fig = px.bar(
        pdf, x=x, y=y, color=color,
        barmode="group",
        color_discrete_sequence=PALETA,
    )
    fig.update_traces(marker_line_width=0, marker_cornerradius=4)
    fig.update_layout(xaxis_title="", yaxis_title="")
    return _layout_base(fig, title, height)


def line_chart(
    df: pl.DataFrame, x: str, y: str,
    title: str = "", markers: bool = True, height: int = 400,
) -> go.Figure:
    """Linha com área gradiente."""
    pdf = df.to_pandas()
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=pdf[x], y=pdf[y],
        mode="lines+markers" if markers else "lines",
        line=dict(color=_ACCENT, width=2.5, shape="spline"),
        marker=dict(size=6, color=_ACCENT, line=dict(width=1.5, color="#0D1117")),
        fill="tozeroy",
        fillcolor="rgba(129, 140, 248, 0.08)",
    ))
    fig.update_layout(xaxis_title="", yaxis_title="")
    return _layout_base(fig, title, height)


def line_chart_multi(
    df: pl.DataFrame, x: str, y: str, color: str,
    title: str = "", height: int = 400,
) -> go.Figure:
    """Múltiplas linhas."""
    pdf = df.to_pandas()
    fig = px.line(
        pdf, x=x, y=y, color=color,
        markers=True,
        color_discrete_sequence=PALETA,
    )
    fig.update_traces(line=dict(width=2), marker=dict(size=5))
    fig.update_layout(xaxis_title="", yaxis_title="")
    return _layout_base(fig, title, height)


def heatmap_chart(
    df: pl.DataFrame, x: str, y: str, z: str,
    title: str = "", height: int = 400,
) -> go.Figure:
    """Heatmap com escala indigo."""
    pdf = df.to_pandas()
    pivot = pdf.pivot_table(index=y, columns=x, values=z, fill_value=0)
    fig = go.Figure(data=go.Heatmap(
        z=pivot.values,
        x=[str(c) for c in pivot.columns],
        y=[str(i) for i in pivot.index],
        colorscale=[
            [0, "#06080F"],
            [0.3, "#312E81"],
            [0.6, "#6366F1"],
            [1, "#C4B5FD"],
        ],
        hoverongaps=False,
        texttemplate="%{z:,}",
        textfont=dict(size=12, color=_TEXT_BRIGHT),
        showscale=False,
        xgap=2,
        ygap=2,
    ))
    fig.update_layout(xaxis_title="", yaxis_title="")
    return _layout_base(fig, title, height)


def choropleth_brasil(
    df: pl.DataFrame, locations: str, values: str,
    title: str = "", height: int = 600,
) -> go.Figure:
    """Ranking de UFs como barras horizontais com gradiente."""
    pdf = df.to_pandas().sort_values(values, ascending=True)

    fig = go.Figure(go.Bar(
        x=pdf[values],
        y=pdf[locations],
        orientation="h",
        text=pdf[values].apply(lambda v: f"{v:,.0f}".replace(",", ".")),
        textposition="outside",
        textfont=dict(size=13, color=_TEXT_BRIGHT),
        marker=dict(
            color=pdf[values],
            colorscale=[[0, "#312E81"], [0.5, "#6366F1"], [1, "#C4B5FD"]],
            line=dict(width=0),
            cornerradius=4,
        ),
    ))
    fig.update_layout(
        xaxis=dict(title="", showticklabels=False),
        yaxis=dict(title=""),
    )
    return _layout_base(fig, title, height)


def treemap_chart(
    df: pl.DataFrame, path: list[str], values: str,
    title: str = "", height: int = 600,
) -> go.Figure:
    """Treemap com escala indigo."""
    pdf = df.to_pandas()
    fig = px.treemap(
        pdf, path=path, values=values,
        color=values,
        color_continuous_scale=[[0, "#312E81"], [0.5, "#6366F1"], [1, "#C4B5FD"]],
    )
    fig.update_layout(coloraxis_showscale=False)
    fig.update_traces(
        textfont=dict(family="Inter, sans-serif", size=14, color=_TEXT_BRIGHT),
        marker=dict(cornerradius=6),
    )
    return _layout_base(fig, title, height)


def sunburst_chart(
    df: pl.DataFrame, path: list[str], values: str,
    title: str = "", height: int = 500,
) -> go.Figure:
    """Sunburst com paleta premium."""
    pdf = df.to_pandas()
    fig = px.sunburst(
        pdf, path=path, values=values,
        color=values,
        color_continuous_scale=[[0, "#312E81"], [0.5, "#6366F1"], [1, "#C4B5FD"]],
    )
    fig.update_layout(coloraxis_showscale=False)
    fig.update_traces(
        textfont=dict(family="Inter, sans-serif", size=13, color=_TEXT_BRIGHT),
        insidetextorientation="radial",
    )
    return _layout_base(fig, title, height)
