# /Users/jairfahl/Downloads/tribus-ai-light/tests/test_auth.py
"""
Testes do módulo de autenticação e isolamento de tenant.
"""

import pytest
import uuid
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta, timezone

from auth import (
    verificar_senha,
    gerar_hash_senha,
    gerar_token,
    decodificar_token,
    autenticar,
    Usuario,
)


# ─── FIXTURES ──────────────────────────────────────────────────────────────────

@pytest.fixture
def usuario_admin():
    return Usuario(
        id=str(uuid.uuid4()),
        email="admin@tribus-ai.com.br",
        nome="Administrador",
        perfil="ADMIN",
        ativo=True,
        primeiro_uso=datetime.now(timezone.utc) - timedelta(days=5),
        criado_em=datetime.now(timezone.utc) - timedelta(days=30),
    )


@pytest.fixture
def usuario_comum():
    return Usuario(
        id=str(uuid.uuid4()),
        email="user@empresa.com.br",
        nome="Usuário Teste",
        perfil="USER",
        ativo=True,
        primeiro_uso=datetime.now(timezone.utc) - timedelta(days=2),
        criado_em=datetime.now(timezone.utc) - timedelta(days=5),
    )


@pytest.fixture
def usuario_sem_primeiro_uso():
    return Usuario(
        id=str(uuid.uuid4()),
        email="novo@empresa.com.br",
        nome="Usuário Novo",
        perfil="USER",
        ativo=True,
        primeiro_uso=None,
        criado_em=datetime.now(timezone.utc),
    )


# ─── TESTES DE SENHA ───────────────────────────────────────────────────────────

class TestSenha:

    def test_hash_e_verificacao_corretos(self):
        senha = "MinhaSenh@123"
        h = gerar_hash_senha(senha)
        assert verificar_senha(senha, h) is True

    def test_senha_errada_nao_verifica(self):
        h = gerar_hash_senha("SenhaCorreta@1")
        assert verificar_senha("SenhaErrada@1", h) is False

    def test_hash_diferente_a_cada_geracao(self):
        senha = "MesmaSenh@123"
        h1 = gerar_hash_senha(senha)
        h2 = gerar_hash_senha(senha)
        assert h1 != h2  # bcrypt gera salt diferente

    def test_hash_vazio_nao_verifica(self):
        h = gerar_hash_senha("Qualquer@1")
        assert verificar_senha("", h) is False


# ─── TESTES DE JWT ──────────────────────────────────────────────────────────────

class TestJWT:

    def test_gerar_e_decodificar_token_valido(self, usuario_admin):
        token = gerar_token(usuario_admin)
        payload = decodificar_token(token)
        assert payload is not None
        assert payload["sub"] == usuario_admin.id
        assert payload["perfil"] == "ADMIN"
        assert payload["email"] == usuario_admin.email
        assert "session_id" in payload  # session_id sempre presente no payload JWT

    def test_token_invalido_retorna_none(self):
        assert decodificar_token("token.invalido.qualquer") is None

    def test_token_vazio_retorna_none(self):
        assert decodificar_token("") is None

    def test_token_expirado_retorna_none(self, usuario_admin):
        import jwt
        from auth import JWT_SECRET, JWT_ALGO
        payload_expirado = {
            "sub":    usuario_admin.id,
            "email":  usuario_admin.email,
            "perfil": usuario_admin.perfil,
            "iat":    datetime.now(timezone.utc) - timedelta(hours=10),
            "exp":    datetime.now(timezone.utc) - timedelta(hours=2),
        }
        token_expirado = jwt.encode(payload_expirado, JWT_SECRET, algorithm=JWT_ALGO)
        assert decodificar_token(token_expirado) is None

    def test_token_adulterado_retorna_none(self, usuario_admin):
        token = gerar_token(usuario_admin)
        token_adulterado = token[:-5] + "XXXXX"
        assert decodificar_token(token_adulterado) is None


# ─── TESTES DE TRIAL ───────────────────────────────────────────────────────────

class TestTrial:

    def test_dias_restantes_com_primeiro_uso_recente(self, usuario_comum):
        # Primeiro uso há 2 dias → 2-3 dias restantes no trial de 5 dias
        assert usuario_comum.dias_restantes_trial in (2, 3)

    def test_dias_restantes_sem_primeiro_uso(self, usuario_sem_primeiro_uso):
        assert usuario_sem_primeiro_uso.dias_restantes_trial is None

    def test_trial_expirado_quando_mais_de_30_dias(self):
        usuario = Usuario(
            id=str(uuid.uuid4()),
            email="old@empresa.com.br",
            nome="Old User",
            perfil="USER",
            ativo=True,
            primeiro_uso=datetime.now(timezone.utc) - timedelta(days=35),
            criado_em=datetime.now(timezone.utc) - timedelta(days=35),
        )
        assert usuario.trial_expirado is True
        assert usuario.dias_restantes_trial == 0

    def test_trial_nao_expirado_sem_primeiro_uso(self, usuario_sem_primeiro_uso):
        assert usuario_sem_primeiro_uso.trial_expirado is False

    def test_is_admin_correto(self, usuario_admin, usuario_comum):
        assert usuario_admin.is_admin is True
        assert usuario_comum.is_admin is False


# ─── TESTES DE AUTENTICAÇÃO (com mock do banco) ────────────────────────────────

class TestAutenticacao:

    @patch("auth.buscar_senha_hash")
    @patch("auth.buscar_usuario_por_email")
    @patch("auth.registrar_primeiro_uso")
    def test_login_valido_retorna_token(
        self, mock_registro, mock_buscar, mock_hash, usuario_admin
    ):
        senha = "Tribus-AI@2026!"
        mock_hash.return_value = gerar_hash_senha(senha)
        mock_buscar.return_value = usuario_admin
        mock_registro.return_value = None

        token, erro = autenticar(usuario_admin.email, senha)

        assert token is not None
        assert erro is None
        payload = decodificar_token(token)
        assert payload["sub"] == usuario_admin.id

    @patch("auth.buscar_senha_hash")
    def test_email_inexistente_retorna_erro_generico(self, mock_hash):
        mock_hash.return_value = None
        token, erro = autenticar("naoexiste@test.com", "qualquer")
        assert token is None
        assert erro == "Email ou senha incorretos."

    @patch("auth.buscar_senha_hash")
    def test_senha_errada_retorna_erro_generico(self, mock_hash):
        mock_hash.return_value = gerar_hash_senha("SenhaCorreta@1")
        token, erro = autenticar("qualquer@test.com", "SenhaErrada@1")
        assert token is None
        assert erro == "Email ou senha incorretos."

    @patch("auth.buscar_senha_hash")
    @patch("auth.buscar_usuario_por_email")
    @patch("auth.registrar_primeiro_uso")
    def test_usuario_inativo_bloqueado(
        self, mock_registro, mock_buscar, mock_hash, usuario_comum
    ):
        senha = "Senh@1234"
        usuario_inativo = Usuario(
            id=usuario_comum.id,
            email=usuario_comum.email,
            nome=usuario_comum.nome,
            perfil="USER",
            ativo=False,  # inativo
            primeiro_uso=None,
            criado_em=usuario_comum.criado_em,
        )
        mock_hash.return_value = gerar_hash_senha(senha)
        mock_buscar.return_value = usuario_inativo
        mock_registro.return_value = None

        token, erro = autenticar(usuario_inativo.email, senha)
        assert token is None
        assert "desativado" in erro.lower()

    def test_erro_nao_revela_existencia_do_email(self):
        """Erro de email inexistente e senha errada devem ser idênticos."""
        with patch("auth.buscar_senha_hash", return_value=None):
            _, erro_email = autenticar("naoexiste@test.com", "qualquer")

        with patch("auth.buscar_senha_hash", return_value=gerar_hash_senha("correta")):
            _, erro_senha = autenticar("existe@test.com", "errada")

        assert erro_email == erro_senha
