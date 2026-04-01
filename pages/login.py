# /downloads/taxmind/pages/login.py
"""
Tela de login do Tribus-AI.
Exibida quando o usuário não está autenticado.
"""

import streamlit as st
from auth import autenticar, buscar_usuario_por_email, decodificar_token


def render_login() -> bool:
    """
    Renderiza a tela de login e processa a autenticação.

    Returns:
      bool — True se login foi bem-sucedido nesta chamada
    """
    # Centralizar o formulário
    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        st.markdown("## 🔐 Tribus-AI")
        st.markdown("#### Inteligência Tributária para a Reforma")
        st.divider()

        with st.form("form_login", clear_on_submit=False):
            email = st.text_input(
                "Email",
                placeholder="seu@email.com.br",
                autocomplete="email",
            )
            senha = st.text_input(
                "Senha",
                type="password",
                placeholder="••••••••",
                autocomplete="current-password",
            )
            submitted = st.form_submit_button(
                "Entrar",
                use_container_width=True,
                type="primary",
            )

        if submitted:
            if not email or not senha:
                st.error("Preencha email e senha.")
                return False

            token, erro = autenticar(email.strip(), senha)

            if erro:
                st.error(erro)
                return False

            # Buscar dados completos do usuário
            payload = decodificar_token(token)
            usuario = buscar_usuario_por_email(email.strip())

            if not usuario or not payload:
                st.error("Erro interno. Tente novamente.")
                return False

            # Persistir sessão
            st.session_state["auth_token"]    = token
            st.session_state["user_id"]       = usuario.id
            st.session_state["user_nome"]     = usuario.nome
            st.session_state["user_email"]    = usuario.email
            st.session_state["user_perfil"]   = usuario.perfil
            st.session_state["user_is_admin"] = usuario.is_admin
            st.session_state["primeiro_uso"]  = usuario.primeiro_uso

            st.success(f"Bem-vindo, {usuario.nome}!")
            st.rerun()
            return True

        st.caption("Não possui acesso? Solicite ao administrador.")

    return False


def logout() -> None:
    """
    Encerra a sessão do usuário e limpa o session_state.
    """
    keys_to_clear = [
        "auth_token", "user_id", "user_nome",
        "user_email", "user_perfil", "user_is_admin", "primeiro_uso",
    ]
    for key in keys_to_clear:
        st.session_state.pop(key, None)
    st.rerun()


def sessao_valida() -> bool:
    """
    Verifica se existe sessão ativa e token JWT válido.

    Returns:
      bool
    """
    token = st.session_state.get("auth_token")
    if not token:
        return False

    payload = decodificar_token(token)
    return payload is not None
