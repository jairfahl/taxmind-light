/**
 * lib/api.ts — Cliente HTTP para a FastAPI (porta 8020).
 * Para mudar a URL base: alterar NEXT_PUBLIC_API_URL em .env.local
 */
import axios from "axios";

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8020",
  timeout: 120000,
  headers: { "Content-Type": "application/json" },
});

// ── Request: injeta Bearer token ──────────────────────────────────────────
// X-API-Key removida do browser (era NEXT_PUBLIC_* → exposta no JS bundle).
// Autenticação do browser é feita exclusivamente via JWT no header Authorization.
api.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("tribus_token");
    if (token) config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ── Response: trata 401 ───────────────────────────────────────────────────
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401 && typeof window !== "undefined") {
      // Não redirecionar se já está na página de login — senão limpa o form
      if (!window.location.pathname.includes("/login")) {
        // Sessão inválida por novo login em outro dispositivo
        if (err.response?.data?.detail === "session_expired") {
          sessionStorage.setItem(
            "auth_msg",
            "Sua conta foi acessada em outro dispositivo. Faça login novamente."
          );
        }
        localStorage.removeItem("tribus_token");
        window.location.href = "/login";
      }
    }
    return Promise.reject(err);
  }
);

export default api;

// ── Auth — endpoint de login (form-encoded, padrão FastAPI OAuth2) ─────────
export async function login(
  email: string,
  senha: string
): Promise<{ access_token: string; token_type: string }> {
  const form = new URLSearchParams({ username: email, password: senha });
  const res = await api.post<{ access_token: string; token_type: string }>(
    "/v1/auth/login",
    form.toString(),
    { headers: { "Content-Type": "application/x-www-form-urlencoded" } }
  );
  return res.data;
}

// ── Upload (multipart) ────────────────────────────────────────────────────
export async function apiUpload<T>(path: string, formData: FormData): Promise<T> {
  const res = await api.post<T>(path, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return res.data;
}
