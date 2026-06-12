"""
components/kpi_cards.py
-----------------------
Cards KPI estilizados com métricas.
"""

import streamlit as st


def render_kpi_card(label: str, valor: str, icone: str = "📊", delta: str | None = None):
    """Renderiza um card KPI individual usando st.metric com estilo customizado."""
    st.metric(
        label=f"{icone}  {label}",
        value=valor,
        delta=delta,
    )


def render_kpi_row(kpis: list[dict]):
    """
    Renderiza uma fileira de KPI cards.
    kpis: lista de dicts com keys: label, valor, icone, delta (opcional)
    """
    cols = st.columns(len(kpis))
    for col, kpi in zip(cols, kpis):
        with col:
            render_kpi_card(
                label=kpi["label"],
                valor=kpi["valor"],
                icone=kpi.get("icone", "📊"),
                delta=kpi.get("delta"),
            )


def formatar_numero(n: int | float, decimais: int = 0) -> str:
    """Formata número com separador de milhar brasileiro."""
    if isinstance(n, float):
        return f"{n:,.{decimais}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{n:,}".replace(",", ".")


def formatar_moeda(valor: float) -> str:
    """Formata valor como moeda brasileira."""
    return f"R$ {formatar_numero(valor, 2)}"


def formatar_percentual(valor: float, decimais: int = 1) -> str:
    """Formata valor como percentual."""
    return f"{valor:.{decimais}f}%".replace(".", ",")
