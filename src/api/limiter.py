"""
src/api/limiter.py — Instância compartilhada do slowapi Limiter.

Importado tanto pelo main.py quanto pelos routers que usam @limiter.limit(),
evitando import circular.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
