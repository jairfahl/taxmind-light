# /Users/jairfahl/Downloads/tribus-ai-light/admin.py
"""
Painel de administração do Tribus-AI.
Visível exclusivamente para usuários com perfil ADMIN.

Seção A — Gestão de Usuários
Seção B — Consumo de API (Step 06)
"""

import streamlit as st
import psycopg2
import psycopg2.extras
import os
from datetime import datetime, date, timedelta, timezone
from typing import Optional

import pandas as pd

from auth import gerar_hash_senha, buscar_usuario_por_id
from src.billing.mau_tracker import (
    obter_mau_mes,
    obter_serie_mau,
    obter_detalhamento_usuarios,
)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://taxmind:taxmind123@localhost:5436/taxmind_db"
)

# Preço estimado por token (Claude Sonnet — atualizar conforme tabela Anthropic)
PRECO_INPUT_POR_1K_TOKENS  = 0.003   # USD por 1.000 tokens de input
PRECO_OUTPUT_POR_1K_TOKENS = 0.015   # USD por 1.000 tokens de output


def _get_connection():
    return psycopg2.connect(DATABASE_URL)


# ─── QUERIES DE USUÁRIOS ───────────────────────────────────────────────────────

def listar_usuarios(filtro_perfil: str = "TODOS", filtro_ativo: str = "TODOS") -> list[dict]:
    """
    Lista todos os usuários com informações de trial e último acesso.

    Params:
      filtro_perfil : str — 'TODOS' | 'ADMIN' | 'USER'
      filtro_ativo  : str — 'TODOS' | 'ATIVO' | 'INATIVO'

    Returns:
      list[dict] — lista de usuários com campos calculados
    """
    where_clauses = []
    params = []

    if filtro_perfil != "TODOS":
        where_clauses.append("u.perfil = %s")
        params.append(filtro_perfil)

    if filtro_ativo == "ATIVO":
        where_clauses.append("u.ativo = TRUE")
    elif filtro_ativo == "INATIVO":
        where_clauses.append("u.ativo = FALSE")

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    sql = f"""
        SELECT
            u.id,
            u.email,
            u.nome,
            u.perfil,
            u.ativo,
            u.primeiro_uso,
            u.criado_em,
            MAX(ai.created_at) AS ultimo_acesso
        FROM users u
        LEFT JOIN ai_interactions ai ON ai.user_id = u.id
        {where_sql}
        GROUP BY u.id, u.email, u.nome, u.perfil, u.ativo, u.primeiro_uso, u.criado_em
        ORDER BY u.criado_em DESC;
    """

    with _get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    agora = datetime.now(timezone.utc)
    resultado = []
    for row in rows:
        primeiro_uso = row["primeiro_uso"]
        if primeiro_uso:
            expira = primeiro_uso + timedelta(days=30)
            dias_restantes = max(0, (expira.replace(tzinfo=timezone.utc) - agora).days)
        else:
            dias_restantes = None

        resultado.append({
            "id":             str(row["id"]),
            "email":          row["email"],
            "nome":           row["nome"],
            "perfil":         row["perfil"],
            "ativo":          row["ativo"],
            "primeiro_uso":   primeiro_uso,
            "criado_em":      row["criado_em"],
            "ultimo_acesso":  row["ultimo_acesso"],
            "dias_restantes": dias_restantes,
        })

    return resultado


def criar_usuario(email: str, nome: str, senha: str, perfil: str) -> tuple[bool, str]:
    """
    Cria novo usuário no banco.

    Returns:
      tuple: (sucesso: bool, mensagem: str)
    """
    try:
        senha_hash = gerar_hash_senha(senha)
        sql = """
            INSERT INTO users (email, nome, senha_hash, perfil)
            VALUES (%s, %s, %s, %s);
        """
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (email.lower().strip(), nome.strip(), senha_hash, perfil))
            conn.commit()
        return True, f"Usuário {email} criado com sucesso."
    except psycopg2.errors.UniqueViolation:
        return False, "Email já cadastrado."
    except Exception as e:
        return False, f"Erro ao criar usuário: {str(e)}"


def alternar_status_usuario(user_id: str, ativo: bool) -> tuple[bool, str]:
    """Ativa ou desativa um usuário."""
    try:
        sql = "UPDATE users SET ativo = %s WHERE id = %s;"
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (ativo, user_id))
            conn.commit()
        status = "ativado" if ativo else "desativado"
        return True, f"Usuário {status}."
    except Exception as e:
        return False, f"Erro: {str(e)}"


def redefinir_senha(user_id: str, nova_senha: str) -> tuple[bool, str]:
    """Redefine a senha de um usuário."""
    try:
        nova_hash = gerar_hash_senha(nova_senha)
        sql = "UPDATE users SET senha_hash = %s WHERE id = %s;"
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (nova_hash, user_id))
            conn.commit()
        return True, "Senha redefinida com sucesso."
    except Exception as e:
        return False, f"Erro: {str(e)}"


# ─── RENDERIZAÇÃO — SEÇÃO A ────────────────────────────────────────────────────

def _render_secao_usuarios():
    """Renderiza a seção A — Gestão de Usuários."""

    st.subheader("Usuários")

    # ── Filtros ────────────────────────────────────────────────────────────────
    col1, col2 = st.columns(2)
    with col1:
        filtro_perfil = st.selectbox(
            "Perfil", ["TODOS", "ADMIN", "USER"], key="filtro_perfil"
        )
    with col2:
        filtro_ativo = st.selectbox(
            "Status", ["TODOS", "ATIVO", "INATIVO"], key="filtro_ativo"
        )

    usuarios = listar_usuarios(filtro_perfil, filtro_ativo)

    # ── Métricas rápidas ───────────────────────────────────────────────────────
    total    = len(usuarios)
    ativos   = sum(1 for u in usuarios if u["ativo"])
    inativos = total - ativos

    mc1, mc2, mc3 = st.columns(3)
    mc1.metric("Total", total)
    mc2.metric("Ativos", ativos)
    mc3.metric("Inativos", inativos)

    st.divider()

    # ── Tabela de usuários ─────────────────────────────────────────────────────
    if not usuarios:
        st.info("Nenhum usuário encontrado com os filtros selecionados.")
    else:
        for u in usuarios:
            with st.expander(
                f"{'🛡️' if u['perfil'] == 'ADMIN' else '👤'} "
                f"{u['nome']} — {u['email']} "
                f"{'✅' if u['ativo'] else '❌'}",
                expanded=False,
            ):
                col_info, col_acoes = st.columns([2, 1])

                with col_info:
                    st.write(f"**Perfil:** {u['perfil']}")

                    # Trial
                    if u["dias_restantes"] is None:
                        st.write("**Trial:** Não iniciado")
                    elif u["dias_restantes"] == 0:
                        st.write("**Trial:** ⛔ Expirado")
                    elif u["dias_restantes"] <= 5:
                        st.write(f"**Trial:** ⚠️ {u['dias_restantes']} dias restantes")
                    else:
                        st.write(f"**Trial:** ⏱ {u['dias_restantes']} dias restantes")

                    # Último acesso
                    if u["ultimo_acesso"]:
                        st.write(f"**Último acesso:** {u['ultimo_acesso'].strftime('%d/%m/%Y %H:%M')}")
                    else:
                        st.write("**Último acesso:** Nunca acessou")

                    st.write(f"**Criado em:** {u['criado_em'].strftime('%d/%m/%Y')}")

                with col_acoes:
                    admin_atual = st.session_state.get("user_id")

                    # Ativar/Desativar (não pode desativar a si mesmo)
                    if u["id"] != admin_atual:
                        if u["ativo"]:
                            if st.button("Desativar", key=f"desat_{u['id']}", use_container_width=True):
                                ok, msg = alternar_status_usuario(u["id"], False)
                                st.success(msg) if ok else st.error(msg)
                                st.rerun()
                        else:
                            if st.button("Ativar", key=f"ativ_{u['id']}", use_container_width=True):
                                ok, msg = alternar_status_usuario(u["id"], True)
                                st.success(msg) if ok else st.error(msg)
                                st.rerun()

                    # Redefinir senha
                    with st.popover("Redefinir senha", use_container_width=True):
                        nova_senha = st.text_input(
                            "Nova senha",
                            type="password",
                            key=f"nova_senha_{u['id']}",
                            placeholder="Mínimo 8 caracteres",
                        )
                        if st.button("Confirmar", key=f"conf_senha_{u['id']}"):
                            if len(nova_senha) < 8:
                                st.error("Mínimo 8 caracteres.")
                            else:
                                ok, msg = redefinir_senha(u["id"], nova_senha)
                                st.success(msg) if ok else st.error(msg)

    st.divider()

    # ── Criar novo usuário ─────────────────────────────────────────────────────
    st.subheader("Criar Novo Usuário")

    with st.form("form_criar_usuario"):
        c1, c2 = st.columns(2)
        with c1:
            novo_nome  = st.text_input("Nome completo", placeholder="João Silva")
            novo_email = st.text_input("Email", placeholder="joao@empresa.com.br")
        with c2:
            novo_perfil = st.selectbox("Perfil", ["USER", "ADMIN"])
            nova_senha  = st.text_input(
                "Senha inicial", type="password", placeholder="Mínimo 8 caracteres"
            )

        if st.form_submit_button("Criar Usuário", type="primary"):
            if not all([novo_nome, novo_email, nova_senha]):
                st.error("Preencha todos os campos.")
            elif len(nova_senha) < 8:
                st.error("Senha deve ter no mínimo 8 caracteres.")
            else:
                ok, msg = criar_usuario(novo_email, novo_nome, nova_senha, novo_perfil)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)


# ─── SEÇÃO B — CONSUMO DE API ──────────────────────────────────────────────────

def _calcular_custo(input_tokens: int, output_tokens: int) -> float:
    """
    Calcula custo estimado em USD.

    Params:
      input_tokens  : int — tokens de entrada
      output_tokens : int — tokens de saída

    Returns:
      float — custo estimado em USD
    """
    custo_input  = (input_tokens  / 1000) * PRECO_INPUT_POR_1K_TOKENS
    custo_output = (output_tokens / 1000) * PRECO_OUTPUT_POR_1K_TOKENS
    return round(custo_input + custo_output, 4)


def _buscar_consumo_por_usuario(
    data_inicio: str,
    data_fim: str,
) -> list[dict]:
    """
    Busca consumo de tokens agregado por usuário no período.

    Params:
      data_inicio : str — formato 'YYYY-MM-DD'
      data_fim    : str — formato 'YYYY-MM-DD'

    Returns:
      list[dict] — [{user_id, nome, email, input_tokens, output_tokens, total_consultas}]
    """
    sql = """
        SELECT
            u.id                       AS user_id,
            u.nome,
            u.email,
            COALESCE(SUM(ai.input_tokens), 0)   AS input_tokens,
            COALESCE(SUM(ai.output_tokens), 0)  AS output_tokens,
            COUNT(ai.id)               AS total_consultas
        FROM users u
        LEFT JOIN ai_interactions ai
            ON  ai.user_id = u.id
            AND ai.created_at::date BETWEEN %s AND %s
        GROUP BY u.id, u.nome, u.email
        ORDER BY (COALESCE(SUM(ai.input_tokens), 0) + COALESCE(SUM(ai.output_tokens), 0)) DESC;
    """
    with _get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (data_inicio, data_fim))
            rows = cur.fetchall()

    return [
        {
            "user_id":         str(row["user_id"]),
            "nome":            row["nome"],
            "email":           row["email"],
            "input_tokens":    int(row["input_tokens"]),
            "output_tokens":   int(row["output_tokens"]),
            "total_tokens":    int(row["input_tokens"]) + int(row["output_tokens"]),
            "total_consultas": int(row["total_consultas"]),
            "custo_usd":       _calcular_custo(int(row["input_tokens"]), int(row["output_tokens"])),
        }
        for row in rows
    ]


def _buscar_consumo_total(data_inicio: str, data_fim: str) -> dict:
    """
    Busca consumo total agregado no período (todos os usuários).

    Returns:
      dict com input_tokens, output_tokens, total_tokens, custo_usd, total_consultas
    """
    sql = """
        SELECT
            COALESCE(SUM(input_tokens), 0)   AS input_tokens,
            COALESCE(SUM(output_tokens), 0)  AS output_tokens,
            COUNT(id)                        AS total_consultas
        FROM ai_interactions
        WHERE created_at::date BETWEEN %s AND %s;
    """
    with _get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (data_inicio, data_fim))
            row = cur.fetchone()

    inp  = int(row["input_tokens"])
    out  = int(row["output_tokens"])
    return {
        "input_tokens":    inp,
        "output_tokens":   out,
        "total_tokens":    inp + out,
        "total_consultas": int(row["total_consultas"]),
        "custo_usd":       _calcular_custo(inp, out),
    }


def _render_secao_api():
    """Renderiza a Seção B — Consumo de API."""

    st.subheader("Consumo de API")
    st.caption(
        "Estimativa baseada nos tokens registrados em ai_interactions. "
        "Saldo real: consulte o dashboard da Anthropic."
    )

    # ── Filtro de período ──────────────────────────────────────────────────────
    hoje       = datetime.now(timezone.utc).date()
    inicio_mes = hoje.replace(day=1)

    col_d1, col_d2 = st.columns(2)
    with col_d1:
        data_inicio = st.date_input(
            "De", value=inicio_mes, key="api_data_inicio"
        )
    with col_d2:
        data_fim = st.date_input(
            "Até", value=hoje, key="api_data_fim"
        )

    if data_inicio > data_fim:
        st.error("Data inicial não pode ser maior que a data final.")
        return

    data_inicio_str = data_inicio.strftime("%Y-%m-%d")
    data_fim_str    = data_fim.strftime("%Y-%m-%d")

    # ── Totais do período ──────────────────────────────────────────────────────
    totais = _buscar_consumo_total(data_inicio_str, data_fim_str)

    st.divider()
    mt1, mt2, mt3, mt4 = st.columns(4)
    mt1.metric("Consultas",      totais["total_consultas"])
    mt2.metric("Tokens (total)", f"{totais['total_tokens']:,}")
    mt3.metric("Tokens input",   f"{totais['input_tokens']:,}")
    mt4.metric("Custo estimado", f"US$ {totais['custo_usd']:.4f}")

    st.caption(
        f"Preços de referência: input = US$ {PRECO_INPUT_POR_1K_TOKENS}/1K tokens | "
        f"output = US$ {PRECO_OUTPUT_POR_1K_TOKENS}/1K tokens (Claude Sonnet). "
        "Atualizar constantes em admin.py se os preços mudarem."
    )
    st.divider()

    # ── Consumo por usuário ────────────────────────────────────────────────────
    st.subheader("Por Usuário")

    consumo = _buscar_consumo_por_usuario(data_inicio_str, data_fim_str)

    if not consumo:
        st.info("Sem dados de consumo no período selecionado.")
        return

    tem_consumo = False
    for u in consumo:
        if u["total_tokens"] == 0 and u["total_consultas"] == 0:
            continue  # Ocultar usuários sem consumo

        tem_consumo = True
        with st.expander(
            f"{'🛡️' if u['nome'] == 'Administrador' else '👤'} "
            f"{u['nome']} — {u['email']} | "
            f"US$ {u['custo_usd']:.4f}",
            expanded=False,
        ):
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Consultas",     u["total_consultas"])
            c2.metric("Tokens total",  f"{u['total_tokens']:,}")
            c3.metric("Input tokens",  f"{u['input_tokens']:,}")
            c4.metric("Custo (USD)",   f"US$ {u['custo_usd']:.4f}")

    if not tem_consumo:
        st.info("Sem dados de consumo no período selecionado.")


# ─── SEÇÃO C — LEGAL HOLD ──────────────────────────────────────────────────────

def _render_secao_legal_hold() -> None:
    """Painel de Legal Hold — lista documentos preservados e permite desativar hold."""
    import pandas as pd
    from src.outputs.legal_hold import listar_documentos_com_hold

    st.subheader("Legal Hold — Documentos Preservados")
    st.caption(
        "Documentos com Legal Hold ativo não podem ser deletados. "
        "Dossiês de Decisão e Materiais Compartilháveis têm Legal Hold permanente "
        "(CTN art. 150, §4º — prescrição tributária 5 anos)."
    )

    try:
        docs = listar_documentos_com_hold(st.session_state.get("user_id", ""))
    except Exception as e:
        st.error(f"Erro ao carregar documentos: {e}")
        return

    st.metric("Total com Legal Hold", len(docs))

    if not docs:
        st.info("Nenhum documento com Legal Hold ativo.")
        return

    dados = [
        {
            "ID": d["id"],
            "Origem": d["tabela"],
            "Classe": d["classe"],
            "Usuário": d["usuario"] or "—",
            "Criado em": d["criado_em"].strftime("%d/%m/%Y") if d["criado_em"] else "—",
            "Hold até": d["legal_hold_ate"].strftime("%d/%m/%Y") if d.get("legal_hold_ate") else "Permanente",
        }
        for d in docs
    ]
    st.dataframe(pd.DataFrame(dados), use_container_width=True, hide_index=True)


# ─── SEÇÃO D — MAU METERING ────────────────────────────────────────────────────

def _render_secao_mau() -> None:
    """Painel de MAU — Monthly Active Users (G26, DEC-08)."""
    st.subheader("MAU — Monthly Active Users")
    st.caption(
        "Usuário ativo = realizou ao menos uma análise no mês. "
        "Login passivo não conta. DEC-08 (ESP-15)."
    )

    mes_atual = date.today().strftime("%B/%Y")

    try:
        mau_atual = obter_mau_mes()
        st.metric(f"MAU — {mes_atual}", mau_atual)
    except Exception as e:
        st.error(f"Erro ao carregar MAU: {e}")
        return

    # Série histórica (6 meses)
    try:
        serie = obter_serie_mau(6)
        if serie:
            dados_serie = [
                {
                    "Mês": s["active_month"].strftime("%m/%Y"),
                    "MAU": s["mau"],
                    "Total de Análises": s["eventos"],
                }
                for s in serie
            ]
            st.dataframe(
                pd.DataFrame(dados_serie),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("Sem histórico de MAU ainda.")
    except Exception as e:
        st.warning(f"Histórico indisponível: {e}")

    # Detalhamento do mês atual
    st.subheader(f"Usuários ativos — {mes_atual}")
    try:
        usuarios = obter_detalhamento_usuarios()
        if usuarios:
            dados_users = [
                {
                    "Nome": u["nome"],
                    "Email": u["email"],
                    "Perfil": u["perfil"],
                    "Análises no mês": u["total_eventos"],
                    "Primeiro acesso": (
                        u["primeiro_evento"].strftime("%d/%m %H:%M")
                        if u.get("primeiro_evento") else "—"
                    ),
                    "Último acesso": (
                        u["ultimo_evento"].strftime("%d/%m %H:%M")
                        if u.get("ultimo_evento") else "—"
                    ),
                }
                for u in usuarios
            ]
            st.dataframe(
                pd.DataFrame(dados_users),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("Nenhum usuário ativo este mês ainda.")
    except Exception as e:
        st.warning(f"Detalhamento indisponível: {e}")


# ─── ENTRY POINT ───────────────────────────────────────────────────────────────

def render_painel_admin():
    """
    Ponto de entrada do painel admin.
    Chamado por app.py quando aba Admin é selecionada.
    """
    # Guard extra: garantir que só ADMIN acessa
    if not st.session_state.get("user_is_admin", False):
        st.error("Acesso negado.")
        st.stop()
        return

    st.title("⚙️ Administração")

    sec_a, sec_b, sec_c, sec_d = st.tabs(
        ["👥 Usuários", "💰 Consumo de API", "🔒 Legal Hold", "📊 MAU"]
    )

    with sec_a:
        _render_secao_usuarios()

    with sec_b:
        _render_secao_api()

    with sec_c:
        _render_secao_legal_hold()

    with sec_d:
        _render_secao_mau()
