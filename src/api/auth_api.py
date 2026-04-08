"""
src/api/auth_api.py — Dependency de autenticação interna da FastAPI.

Valida o header X-API-Key em todos os endpoints sensíveis.
Usado como Depends() nos decorators de rota.

Configuração:
  - Definir API_INTERNAL_KEY no .env com um UUID v4 forte.
  - A mesma chave deve ser configurada no serviço Streamlit (ui/app.py).
"""

import os
from fastapi import Header, HTTPException


def verificar_token_api(x_api_key: str = Header(...)):
    """
    FastAPI dependency: valida o header X-API-Key.

    Levanta 401 se a chave estiver ausente ou incorreta.
    Levanta RuntimeError (500) se API_INTERNAL_KEY não estiver configurada no ambiente.
    """
    api_key = os.getenv("API_INTERNAL_KEY")
    if not api_key:
        raise RuntimeError("API_INTERNAL_KEY não configurada no ambiente.")
    if x_api_key != api_key:
        raise HTTPException(status_code=401, detail="Não autorizado.")
