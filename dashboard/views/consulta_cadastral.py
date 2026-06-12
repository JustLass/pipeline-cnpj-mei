"""
pages/consulta_cadastral.py
---------------------------
Página 5: Consulta Cadastral via MongoDB — Busca pontual de MEIs.
"""

import streamlit as st
import polars as pl

from mongo_client import testar_conexao, buscar_por_cnpj, buscar_por_uf_cnae, stats_collection
from data_loader import carregar_dim_cnaes, carregar_dim_municipios, carregar_dim_naturezas, resolver_codigo
from config import SITUACAO_CADASTRAL, PORTE_EMPRESA, IDENTIFICADOR_MATRIZ_FILIAL, UFS_BRASIL


def _formatar_data(valor: int | None) -> str:
    """Converte YYYYMMDD int para DD/MM/YYYY string."""
    if valor is None or valor == 0:
        return "—"
    s = str(valor)
    if len(s) != 8:
        return s
    return f"{s[6:8]}/{s[4:6]}/{s[:4]}"


def _formatar_cnpj(basico: int, ordem: int | None = None, dv: int | None = None) -> str:
    """Formata CNPJ completo: XX.XXX.XXX/YYYY-ZZ."""
    b = str(basico).zfill(8)
    if ordem is not None and dv is not None:
        o = str(ordem).zfill(4)
        d = str(dv).zfill(2)
        return f"{b[:2]}.{b[2:5]}.{b[5:]}/{o}-{d}"
    return b


def _render_ficha(doc: dict):
    """Renderiza a ficha cadastral de um documento MongoDB."""
    dim_cnaes = carregar_dim_cnaes()
    dim_mun = carregar_dim_municipios()
    dim_nat = carregar_dim_naturezas()

    # Tratar Razão Social
    razao_social = doc.get("razao_social")
    if not razao_social or str(razao_social).strip().upper() in ("NONE", "NULL", ""):
        razao_social = "Sem nome (Razão Social não cadastrada)"
    else:
        razao_social = str(razao_social).strip()

    # Header da empresa
    st.markdown(f"### 🏢 {razao_social}")

    col1, col2, col3 = st.columns(3)
    col1.metric("CNPJ Básico", str(doc["_id"]).zfill(8))
    col2.metric("Capital Social", f"R$ {doc.get('capital_social', 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

    nat_cod = doc.get("natureza_juridica")
    nat_desc = resolver_codigo(dim_nat, nat_cod)
    col3.metric("Natureza Jurídica", nat_desc)

    porte_desc = PORTE_EMPRESA.get(doc.get("porte_empresa"), "Não informado")
    st.info(f"**Porte:** {porte_desc} | **Simples Nacional:** {doc.get('opcao_pelo_simples', '—')} | **MEI:** {doc.get('opcao_pelo_mei', '—')}")

    # Sócios / Proprietários
    socios = doc.get("socios", [])
    if socios:
        st.markdown("#### 👥 Sócios / Proprietários")
        for soc in socios:
            nome_socio = soc.get("nome_socio_razao_social")
            if not nome_socio or str(nome_socio).strip().upper() in ("NONE", "NULL", ""):
                nome_socio = "Sem nome cadastrado"
            else:
                nome_socio = str(nome_socio).strip()

            tipo_cod = soc.get("identificador_socio")
            tipo_desc = "Pessoa Física" if tipo_cod == 2 else ("Pessoa Jurídica" if tipo_cod == 1 else ("Estrangeiro" if tipo_cod == 3 else "Não informado"))
            st.markdown(f"- **{nome_socio}** ({tipo_desc})")

    # Estabelecimentos
    estabs = doc.get("estabelecimentos", [])
    st.markdown(f"#### 📍 Estabelecimentos ({len(estabs)})")

    for i, est in enumerate(estabs):
        tipo = IDENTIFICADOR_MATRIZ_FILIAL.get(est.get("identificador_matriz_filial"), "—")
        cnpj_fmt = _formatar_cnpj(doc["_id"], est.get("cnpj_ordem"), est.get("cnpj_dv"))
        sit_desc = SITUACAO_CADASTRAL.get(est.get("situacao_cadastral"), "Desconhecido")

        with st.expander(f"{'🏠' if tipo == 'Matriz' else '🏗️'} {tipo} — CNPJ {cnpj_fmt} — {sit_desc}", expanded=(i == 0)):
            c1, c2, c3 = st.columns(3)

            # Nome fantasia
            nome_fantasia = est.get("nome_fantasia")
            if not nome_fantasia or str(nome_fantasia).strip().upper() in ("NONE", "NULL", ""):
                nome_fantasia = "Sem nome fantasia"
            else:
                nome_fantasia = str(nome_fantasia).strip()
            c1.markdown(f"**Nome Fantasia:** {nome_fantasia}")

            # CNAE Principal
            cnae_cod = est.get("cnae_fiscal_principal")
            cnae_desc = resolver_codigo(dim_cnaes, cnae_cod)
            c2.markdown(f"**CNAE Principal:** {cnae_desc}")

            # Data de abertura
            c3.markdown(f"**Abertura:** {_formatar_data(est.get('data_inicio_atividade'))}")

            # Endereço
            end = est.get("endereco", {})
            mun_desc = resolver_codigo(dim_mun, end.get("municipio"))
            cep = str(end.get("cep", "")).zfill(8) if end.get("cep") else "—"
            endereco_str = (
                f"{end.get('tipo_logradouro', '')} {end.get('logradouro', '')}, "
                f"{end.get('numero', 'S/N')} "
                f"{'- ' + end.get('complemento') if end.get('complemento') else ''} "
                f"— {end.get('bairro', '')} — {mun_desc}/{end.get('uf', '')} "
                f"— CEP {cep[:5]}-{cep[5:]}"
            )
            st.markdown(f"📍 **Endereço:** {endereco_str.strip()}")

            # Contato
            contato = est.get("contato", {})
            tel_parts = []
            if contato.get("ddd_1") and contato.get("telefone_1"):
                tel_parts.append(f"({contato['ddd_1']}) {contato['telefone_1']}")
            if contato.get("ddd_2") and contato.get("telefone_2"):
                tel_parts.append(f"({contato['ddd_2']}) {contato['telefone_2']}")
            email = contato.get("correio_eletronico", "—")
            if tel_parts or email != "—":
                st.markdown(f"📞 **Contato:** {' | '.join(tel_parts) or '—'} | ✉️ {email}")

            # CNAEs secundários
            cnae_sec = est.get("cnae_fiscal_secundarias", [])
            if cnae_sec:
                descs = [resolver_codigo(dim_cnaes, c) for c in cnae_sec[:5]]
                st.markdown("**CNAEs Secundários:** " + " • ".join(descs))


def render():
    st.header("🔍 Consulta Cadastral")
    st.caption("Busca detalhada de empresas MEI via MongoDB")

    # --- Verificar conexão ---
    mongo_ok = testar_conexao()
    if not mongo_ok:
        st.error(
            "❌ **MongoDB não está acessível** na porta 27017.\n\n"
            "Inicie o container: `docker start mongo-local` ou:\n"
            "```\ndocker run -d --name mongo-local -p 27017:27017 -v mongo_data:/data/db mongo:latest\n```"
        )
        return

    # Stats
    stats = stats_collection()
    st.success(f"✅ Conectado ao MongoDB — **{stats['total_documentos']:,}** documentos na coleção `{stats['nome']}`")

    st.divider()

    st.markdown("Digite o **CNPJ básico** (8 dígitos numéricos, sem pontuação):")
    cnpj_input = st.text_input("CNPJ Básico", placeholder="Ex: 41367111", key="cnpj_input")

    if cnpj_input:
        try:
            cnpj_int = int(cnpj_input.strip())
        except ValueError:
            st.error("⚠️ CNPJ inválido. Digite apenas números.")
            return

        with st.spinner("Buscando no MongoDB..."):
            doc = buscar_por_cnpj(cnpj_int)

        if doc:
            _render_ficha(doc)
        else:
            st.warning(f"Nenhum MEI encontrado com CNPJ básico **{cnpj_input}**.")
