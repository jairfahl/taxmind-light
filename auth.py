# /downloads/tribus-ai-light/auth.py
"""
Módulo de autenticação do Tribus-AI.
Responsável por: verificação de credenciais, geração/decodificação de JWT,
busca de usuário no banco e registro do primeiro uso.
"""

import bcrypt
import jwt
import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from dataclasses import dataclass

import psycopg2
import psycopg2.extras

# ─── CONFIGURAÇÃO ──────────────────────────────────────────────────────────────

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://taxmind:taxmind123@localhost:5436/taxmind_db"
)

# Chave secreta para assinar JWT.
# Obrigatório: definir JWT_SECRET como variável de ambiente.
_jwt_secret = os.getenv("JWT_SECRET")
if not _jwt_secret:
    raise RuntimeError("JWT_SECRET não configurada. Defina a variável de ambiente JWT_SECRET.")
JWT_SECRET  = _jwt_secret
JWT_ALGO    = "HS256"
JWT_EXPIRY_HOURS = 8  # sessão expira em 8 horas


# ─── DATACLASSES ───────────────────────────────────────────────────────────────

@dataclass
class Usuario:
    id:           str
    email:        str
    nome:         str
    perfil:       str   # 'ADMIN' | 'USER'
    ativo:        bool
    primeiro_uso: Optional[datetime]
    criado_em:    datetime
    tenant_id:    Optional[str] = None

    @property
    def is_admin(self) -> bool:
        return self.perfil == "ADMIN"

    @property
    def dias_restantes_trial(self) -> Optional[int]:
        """
        Retorna dias restantes no período de trial de 30 dias.
        None se primeiro_uso ainda não foi registrado.
        0 se trial expirou.
        """
        if self.primeiro_uso is None:
            return None
        expira = self.primeiro_uso + timedelta(days=30)
        agora  = datetime.now(timezone.utc)
        delta  = (expira - agora).days
        return max(0, delta)

    @property
    def trial_expirado(self) -> bool:
        if self.primeiro_uso is None:
            return False
        return self.dias_restantes_trial == 0

    @property
    def data_expiracao_trial(self) -> Optional[datetime]:
        if self.primeiro_uso is None:
            return None
        return self.primeiro_uso + timedelta(days=30)


# ─── BANCO DE DADOS ─────────────────────────────────────────────────────────────

def _get_connection():
    return psycopg2.connect(DATABASE_URL)


def buscar_usuario_por_email(email: str) -> Optional[Usuario]:
    """
    Busca usuário no banco pelo email.

    Params:
      email : str — email do usuário

    Returns:
      Usuario | None
    """
    sql = """
        SELECT id, email, nome, perfil, ativo, primeiro_uso, criado_em, tenant_id
        FROM users
        WHERE email = %s
        LIMIT 1;
    """
    with _get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (email.lower().strip(),))
            row = cur.fetchone()
            if not row:
                return None
            return Usuario(
                id=str(row["id"]),
                email=row["email"],
                nome=row["nome"],
                perfil=row["perfil"],
                ativo=row["ativo"],
                primeiro_uso=row["primeiro_uso"],
                criado_em=row["criado_em"],
                tenant_id=str(row["tenant_id"]) if row["tenant_id"] else None,
            )


def buscar_usuario_por_id(user_id: str) -> Optional[Usuario]:
    """
    Busca usuário no banco pelo ID.

    Params:
      user_id : str — UUID do usuário

    Returns:
      Usuario | None
    """
    sql = """
        SELECT id, email, nome, perfil, ativo, primeiro_uso, criado_em, tenant_id
        FROM users
        WHERE id = %s
        LIMIT 1;
    """
    with _get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (user_id,))
            row = cur.fetchone()
            if not row:
                return None
            return Usuario(
                id=str(row["id"]),
                email=row["email"],
                nome=row["nome"],
                perfil=row["perfil"],
                ativo=row["ativo"],
                primeiro_uso=row["primeiro_uso"],
                criado_em=row["criado_em"],
                tenant_id=str(row["tenant_id"]) if row["tenant_id"] else None,
            )


def buscar_senha_hash(email: str) -> Optional[str]:
    """
    Retorna apenas o hash de senha do usuário.
    Separado de buscar_usuario_por_email por segurança.
    """
    sql = "SELECT senha_hash FROM users WHERE email = %s LIMIT 1;"
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (email.lower().strip(),))
            row = cur.fetchone()
            return row[0] if row else None


def registrar_primeiro_uso(user_id: str) -> None:
    """
    Registra o timestamp do primeiro uso se ainda não foi registrado.
    Dispara o contador de 30 dias de trial.

    Params:
      user_id : str — UUID do usuário
    """
    sql = """
        UPDATE users
        SET primeiro_uso = NOW()
        WHERE id = %s
          AND primeiro_uso IS NULL;
    """
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (user_id,))
        conn.commit()


# ─── SENHA ──────────────────────────────────────────────────────────────────────

def verificar_senha(senha_plaintext: str, senha_hash: str) -> bool:
    """
    Verifica se a senha em texto plano corresponde ao hash bcrypt.

    Params:
      senha_plaintext : str — senha digitada pelo usuário
      senha_hash      : str — hash armazenado no banco

    Returns:
      bool
    """
    try:
        return bcrypt.checkpw(
            senha_plaintext.encode("utf-8"),
            senha_hash.encode("utf-8"),
        )
    except Exception:
        return False


def gerar_hash_senha(senha: str) -> str:
    """
    Gera hash bcrypt para uma senha.
    Usado ao criar ou redefinir senhas.

    Params:
      senha : str — senha em texto plano

    Returns:
      str — hash bcrypt
    """
    return bcrypt.hashpw(
        senha.encode("utf-8"),
        bcrypt.gensalt(rounds=12)
    ).decode("utf-8")


# ─── JWT ────────────────────────────────────────────────────────────────────────

def gerar_token(usuario: Usuario) -> str:
    """
    Gera JWT com payload do usuário.

    Params:
      usuario : Usuario

    Returns:
      str — token JWT assinado
    """
    agora  = datetime.now(timezone.utc)
    expira = agora + timedelta(hours=JWT_EXPIRY_HOURS)

    payload = {
        "sub":    usuario.id,
        "email":  usuario.email,
        "perfil": usuario.perfil,
        "iat":    agora,
        "exp":    expira,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def decodificar_token(token: str) -> Optional[dict]:
    """
    Decodifica e valida JWT.

    Params:
      token : str — token JWT

    Returns:
      dict com payload | None se inválido ou expirado
    """
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# ─── AUTENTICAÇÃO COMPLETA ──────────────────────────────────────────────────────

def autenticar(email: str, senha: str) -> tuple[Optional[str], Optional[str]]:
    """
    Fluxo completo de autenticação:
    1. Busca usuário por email
    2. Verifica se está ativo
    3. Verifica senha
    4. Registra primeiro uso se necessário
    5. Gera e retorna JWT

    Params:
      email : str — email digitado
      senha : str — senha digitada

    Returns:
      tuple: (token: str | None, erro: str | None)
        - sucesso: (token, None)
        - falha:   (None, mensagem_de_erro)

    Nota: mensagem de erro é genérica — nunca revela se email existe.
    """
    ERRO_GENERICO = "Email ou senha incorretos."

    # 1. Buscar hash separadamente (não expõe existência do email no erro)
    senha_hash = buscar_senha_hash(email)
    if not senha_hash:
        return None, ERRO_GENERICO

    # 2. Verificar senha
    if not verificar_senha(senha, senha_hash):
        return None, ERRO_GENERICO

    # 3. Buscar usuário completo
    usuario = buscar_usuario_por_email(email)
    if not usuario:
        return None, ERRO_GENERICO

    # 4. Verificar se está ativo
    if not usuario.ativo:
        return None, "Acesso desativado. Entre em contato com o administrador."

    # 5. Registrar primeiro uso (no-op se já registrado)
    registrar_primeiro_uso(usuario.id)

    # 6. Gerar token
    token = gerar_token(usuario)
    return token, None
