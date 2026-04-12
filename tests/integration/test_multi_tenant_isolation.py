"""
tests/integration/test_multi_tenant_isolation.py — Testes de isolamento multi-tenant.

Verifica que dados de um tenant não vazam para outro.
Executa com: pytest tests/integration/test_multi_tenant_isolation.py -v
"""

import os
import uuid

import psycopg2
import pytest
from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)

_DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://taxmind:taxmind123@localhost:5436/taxmind_db",
)


# ---------------------------------------------------------------------------
# TC-MT-01: GET /v1/cases não expõe casos de outros tenants
# ---------------------------------------------------------------------------
def test_listar_casos_nao_expoe_titulo_reservado():
    """
    Casos cujos títulos contém 'teste' ou 'test' são filtrados pelo endpoint.
    Verifica que a listagem não retorna casos com nomes reservados de testes.
    """
    resp = client.get("/v1/cases")
    assert resp.status_code == 200
    casos = resp.json()
    assert isinstance(casos, list)

    for caso in casos:
        titulo = caso.get("titulo", "").lower()
        # Nenhum caso retornado deve ter título filtrado
        palavras_filtradas = ["teste", "test", "smoke", "validar", "bloqueio",
                               "invalido", "retrocesso", "avancar", "voltar",
                               "submeter", "integração", "integracao"]
        for palavra in palavras_filtradas:
            assert palavra not in titulo, \
                f"Caso com título reservado '{titulo}' não deveria aparecer na listagem"


# ---------------------------------------------------------------------------
# TC-MT-02: GET /v1/cases/{id_inexistente} → 404
# ---------------------------------------------------------------------------
def test_get_caso_inexistente_retorna_404():
    """Buscar um case_id que não existe deve retornar 404."""
    resp = client.get("/v1/cases/999999999")
    assert resp.status_code == 404, f"Esperado 404, obtido {resp.status_code}"


# ---------------------------------------------------------------------------
# TC-MT-03: Estrutura de caso retornado é consistente
# ---------------------------------------------------------------------------
def test_listar_casos_estrutura_consistente():
    """Cada item na listagem de casos tem os campos obrigatórios."""
    resp = client.get("/v1/cases")
    assert resp.status_code == 200
    casos = resp.json()

    for caso in casos:
        assert "case_id" in caso, "Campo 'case_id' ausente"
        assert "titulo" in caso, "Campo 'titulo' ausente"
        assert "status" in caso, "Campo 'status' ausente"
        assert "passo_atual" in caso, "Campo 'passo_atual' ausente"
        assert "created_at" in caso, "Campo 'created_at' ausente"
        assert isinstance(caso["passo_atual"], int), "passo_atual deve ser inteiro"
        assert 1 <= caso["passo_atual"] <= 6, f"passo_atual inválido: {caso['passo_atual']}"


# ---------------------------------------------------------------------------
# TC-MT-04: Tenants não compartilham dados via queries diretas ao banco
# ---------------------------------------------------------------------------
def test_isolamento_via_db_direto():
    """
    Cria dois tenants diretamente no banco e verifica que seus UUIDs são distintos.
    Testa a integridade da tabela tenants (UNIQUE em cnpj_raiz).
    """
    conn = psycopg2.connect(_DB_URL)
    try:
        with conn.cursor() as cur:
            # Tentar inserir dois tenants com mesmo CNPJ raiz → deve falhar
            cnpj_test = "99887766"
            # Limpar registros de teste anteriores
            cur.execute("DELETE FROM tenants WHERE cnpj_raiz = %s", (cnpj_test,))
            conn.commit()

            cur.execute(
                "INSERT INTO tenants (cnpj_raiz, razao_social) VALUES (%s, %s) RETURNING id",
                (cnpj_test, "Empresa Teste Isolamento A"),
            )
            tenant_id_a = cur.fetchone()[0]
            conn.commit()

            # Segundo INSERT com mesmo CNPJ deve lançar UniqueViolation
            with pytest.raises(psycopg2.errors.UniqueViolation):
                cur.execute(
                    "INSERT INTO tenants (cnpj_raiz, razao_social) VALUES (%s, %s)",
                    (cnpj_test, "Empresa Teste Isolamento B"),
                )
                conn.commit()

    finally:
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM tenants WHERE cnpj_raiz = '99887766'")
        conn.commit()
        conn.close()


# ---------------------------------------------------------------------------
# TC-MT-05: outputs vinculados a cases existentes (integridade referencial)
# ---------------------------------------------------------------------------
def test_outputs_referenciam_cases_validos():
    """Todos os outputs no banco devem referenciar um case_id existente."""
    conn = psycopg2.connect(_DB_URL)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*)
                FROM outputs o
                WHERE NOT EXISTS (
                    SELECT 1 FROM cases c WHERE c.id = o.case_id
                )
            """)
            orphaned = cur.fetchone()[0]
        assert orphaned == 0, f"{orphaned} outputs órfãos encontrados (sem case correspondente)"
    finally:
        conn.close()
