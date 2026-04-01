# /downloads/taxmind/components/trial_banner.py
"""
Banner de trial exibido no topo do app após login.
Mostra dias restantes do período de testes de 30 dias.
"""

import streamlit as st
from datetime import datetime, timedelta, timezone
from auth import buscar_usuario_por_id


def render_trial_banner() -> None:
    """
    Renderiza o banner de trial no topo da página.
    Comportamento:
      - Verde/cinza: > 5 dias restantes
      - Vermelho: <= 5 dias restantes
      - Bloqueio: 0 dias restantes (trial expirado)

    Deve ser chamado no início de cada página, após confirmação de sessão.
    """
    user_id = st.session_state.get("user_id")
    if not user_id:
        return

    # Buscar dados atualizados do usuário (garante primeiro_uso atualizado)
    usuario = buscar_usuario_por_id(user_id)
    if not usuario:
        return

    # Se primeiro_uso ainda não foi registrado, não exibir banner
    if usuario.primeiro_uso is None:
        return

    dias = usuario.dias_restantes_trial
    data_exp = usuario.data_expiracao_trial

    if dias is None:
        return

    data_formatada = data_exp.strftime("%d/%m/%Y") if data_exp else ""

    # ─── TRIAL EXPIRADO ────────────────────────────────────────────────────────
    if dias == 0:
        st.error(
            f"⛔ Período de testes encerrado em {data_formatada}. "
            "Entre em contato com o administrador para continuar usando o Tribus-AI."
        )
        st.stop()  # Bloqueia toda a execução da página abaixo deste ponto
        return

    # ─── ALERTA: MENOS DE 5 DIAS ───────────────────────────────────────────────
    if dias <= 5:
        st.warning(
            f"⚠️ **Período de testes:** {dias} dia{'s' if dias != 1 else ''} restante{'s' if dias != 1 else ''}  |  "
            f"Vence em {data_formatada}"
        )
        return

    # ─── NORMAL: MAIS DE 5 DIAS ────────────────────────────────────────────────
    st.info(
        f"⏱ **Período de testes:** {dias} dias restantes  |  "
        f"Vence em {data_formatada}"
    )


def render_header_com_logout() -> None:
    """
    Renderiza header com nome do usuário e botão de logout.
    Deve ser chamado uma vez por página, após sessao_valida().
    """
    from pages.login import logout

    col1, col2 = st.columns([4, 1])

    with col1:
        nome   = st.session_state.get("user_nome", "")
        perfil = st.session_state.get("user_perfil", "")
        badge  = "🛡️ Admin" if perfil == "ADMIN" else "👤 Usuário"
        st.caption(f"{badge} — {nome}")

    with col2:
        if st.button("Sair", use_container_width=True):
            logout()
