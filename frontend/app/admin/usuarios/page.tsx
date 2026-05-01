"use client";
import { useEffect, useState, useCallback } from "react";
import { Shield, UserPlus, Eye, EyeOff, KeyRound, CheckCircle, XCircle, RefreshCw } from "lucide-react";
import { AdminNav } from "@/components/admin/AdminNav";
import { Card } from "@/components/shared/Card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuthStore } from "@/store/auth";
import api from "@/lib/api";

interface UserRow {
  id: string;
  email: string;
  nome: string;
  perfil: "ADMIN" | "USER";
  ativo: boolean;
  criado_em: string | null;
  email_verificado: boolean;
  empresa: string | null;
  subscription_status: string | null;
  trial_ends_at: string | null;
}

const PERFIL_OPTS = ["Todos", "ADMIN", "USER"] as const;
const STATUS_OPTS = [
  { label: "Todos",    value: undefined },
  { label: "Ativos",   value: true },
  { label: "Inativos", value: false },
];

export default function UsuariosAdminPage() {
  const { user: me } = useAuthStore();

  const [users, setUsers]         = useState<UserRow[]>([]);
  const [total, setTotal]         = useState(0);
  const [loading, setLoading]     = useState(true);
  const [filtroP, setFiltroP]     = useState<string>("Todos");
  const [filtroA, setFiltroA]     = useState<boolean | undefined>(undefined);
  const [erro, setErro]           = useState("");

  // Modal novo usuário
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating]     = useState(false);
  const [createErro, setCreateErro] = useState("");
  const [showNewPass, setShowNewPass] = useState(false);
  const [novoUser, setNovoUser] = useState({ nome: "", email: "", senha: "", perfil: "USER" });

  // Modal reset senha
  const [resetTarget, setResetTarget]  = useState<UserRow | null>(null);
  const [novaSenha, setNovaSenha]      = useState("");
  const [showReset, setShowReset]      = useState(false);
  const [resetting, setResetting]      = useState(false);
  const [resetErro, setResetErro]      = useState("");

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    setErro("");
    try {
      const params: Record<string, string> = {};
      if (filtroP !== "Todos") params.perfil = filtroP;
      if (filtroA !== undefined) params.ativo = String(filtroA);
      const res = await api.get<{ users: UserRow[]; total: number }>("/v1/admin/users", { params });
      setUsers(res.data.users);
      setTotal(res.data.total);
    } catch {
      setErro("Erro ao carregar usuários.");
    } finally {
      setLoading(false);
    }
  }, [filtroP, filtroA]);

  useEffect(() => { fetchUsers(); }, [fetchUsers]);

  const toggleAtivo = async (u: UserRow) => {
    if (u.id === me?.id) return; // proteção: admin não se desativa
    await api.patch(`/v1/admin/users/${u.id}`, { ativo: !u.ativo });
    fetchUsers();
  };

  const criarUser = async () => {
    setCreateErro("");
    setCreating(true);
    try {
      await api.post("/v1/admin/users", novoUser);
      setShowCreate(false);
      setNovoUser({ nome: "", email: "", senha: "", perfil: "USER" });
      fetchUsers();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setCreateErro(detail ?? "Erro ao criar usuário.");
    } finally {
      setCreating(false);
    }
  };

  const resetSenha = async () => {
    if (!resetTarget) return;
    setResetErro("");
    setResetting(true);
    try {
      await api.post(`/v1/admin/users/${resetTarget.id}/reset-senha`, { nova_senha: novaSenha });
      setResetTarget(null);
      setNovaSenha("");
    } catch {
      setResetErro("Erro ao redefinir senha.");
    } finally {
      setResetting(false);
    }
  };

  const statusBadge = (status: string | null) => {
    const map: Record<string, { label: string; color: string }> = {
      trial:         { label: "Trial",          color: "#f59e0b" },
      trial_expired: { label: "Trial Expirado", color: "#ef4444" },
      active:        { label: "Ativo",          color: "#10b981" },
      past_due:      { label: "Atrasado",       color: "#ef4444" },
      canceled:      { label: "Cancelado",      color: "#6b7280" },
    };
    const s = map[status ?? ""] ?? { label: status ?? "—", color: "#9ca3af" };
    return (
      <span
        className="text-[11px] font-semibold px-2 py-0.5 rounded-full"
        style={{ background: s.color + "20", color: s.color }}
      >
        {s.label}
      </span>
    );
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Shield size={20} className="text-primary" />
          <h1 className="text-2xl font-semibold">Painel Admin</h1>
        </div>
        <Button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 text-sm"
          style={{ background: "linear-gradient(135deg,#2E75B6,#1F3864)" }}
        >
          <UserPlus size={14} /> Novo usuário
        </Button>
      </div>

      <AdminNav />

      {/* Filtros */}
      <div className="flex flex-wrap gap-3 items-center">
        <div className="flex gap-1 bg-slate-100 rounded-lg p-1">
          {PERFIL_OPTS.map((p) => (
            <button
              key={p}
              onClick={() => setFiltroP(p)}
              className="px-3 py-1 text-xs font-medium rounded-md transition-colors cursor-pointer"
              style={filtroP === p
                ? { background: "#fff", color: "#1F3864", boxShadow: "0 1px 3px rgba(0,0,0,.1)" }
                : { color: "#64748b" }
              }
            >
              {p}
            </button>
          ))}
        </div>
        <div className="flex gap-1 bg-slate-100 rounded-lg p-1">
          {STATUS_OPTS.map((s) => (
            <button
              key={s.label}
              onClick={() => setFiltroA(s.value)}
              className="px-3 py-1 text-xs font-medium rounded-md transition-colors cursor-pointer"
              style={filtroA === s.value
                ? { background: "#fff", color: "#1F3864", boxShadow: "0 1px 3px rgba(0,0,0,.1)" }
                : { color: "#64748b" }
              }
            >
              {s.label}
            </button>
          ))}
        </div>
        <button onClick={fetchUsers} className="p-2 rounded-md hover:bg-slate-100 transition-colors cursor-pointer">
          <RefreshCw size={14} className="text-slate-500" />
        </button>
        <span className="text-xs text-muted-foreground ml-auto">{total} usuário(s)</span>
      </div>

      {/* Tabela */}
      <Card>
        {erro && <p className="text-sm text-red-500 mb-3">{erro}</p>}
        {loading ? (
          <p className="text-sm text-muted-foreground py-8 text-center">Carregando…</p>
        ) : users.length === 0 ? (
          <p className="text-sm text-muted-foreground py-8 text-center">Nenhum usuário encontrado.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left" style={{ borderColor: "var(--border,#e2e8f0)" }}>
                  {["Nome / E-mail", "Perfil", "Status", "Plano", "Verificado", "Criado em", "Ações"].map((h) => (
                    <th key={h} className="pb-2 pr-4 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr
                    key={u.id}
                    className="border-b last:border-0 hover:bg-slate-50 transition-colors"
                    style={{ borderColor: "var(--border,#e2e8f0)" }}
                  >
                    <td className="py-3 pr-4">
                      <p className="font-medium text-foreground">{u.nome}</p>
                      <p className="text-xs text-muted-foreground">{u.email}</p>
                      {u.empresa && <p className="text-xs text-muted-foreground">{u.empresa}</p>}
                    </td>
                    <td className="py-3 pr-4">
                      <span
                        className="text-[11px] font-semibold px-2 py-0.5 rounded-full"
                        style={u.perfil === "ADMIN"
                          ? { background: "#ede9fe", color: "#7c3aed" }
                          : { background: "#e0f2fe", color: "#0369a1" }
                        }
                      >
                        {u.perfil}
                      </span>
                    </td>
                    <td className="py-3 pr-4">
                      {u.ativo
                        ? <span className="flex items-center gap-1 text-xs text-emerald-600"><CheckCircle size={12} /> Ativo</span>
                        : <span className="flex items-center gap-1 text-xs text-slate-400"><XCircle size={12} /> Inativo</span>
                      }
                    </td>
                    <td className="py-3 pr-4">{statusBadge(u.subscription_status)}</td>
                    <td className="py-3 pr-4">
                      {u.email_verificado
                        ? <CheckCircle size={14} className="text-emerald-500" />
                        : <XCircle size={14} className="text-slate-300" />
                      }
                    </td>
                    <td className="py-3 pr-4 text-xs text-muted-foreground whitespace-nowrap">
                      {u.criado_em ? new Date(u.criado_em).toLocaleDateString("pt-BR") : "—"}
                    </td>
                    <td className="py-3">
                      <div className="flex gap-2">
                        <button
                          onClick={() => toggleAtivo(u)}
                          disabled={u.id === me?.id}
                          title={u.id === me?.id ? "Não pode desativar a si mesmo" : u.ativo ? "Desativar" : "Ativar"}
                          className="text-xs px-2 py-1 rounded border transition-colors cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed"
                          style={{ borderColor: "var(--border,#e2e8f0)" }}
                        >
                          {u.ativo ? "Desativar" : "Ativar"}
                        </button>
                        <button
                          onClick={() => { setResetTarget(u); setNovaSenha(""); setResetErro(""); }}
                          className="text-xs px-2 py-1 rounded border transition-colors cursor-pointer flex items-center gap-1"
                          style={{ borderColor: "var(--border,#e2e8f0)" }}
                          title="Redefinir senha"
                        >
                          <KeyRound size={11} /> Senha
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Modal — Novo Usuário */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: "rgba(0,0,0,.45)" }}>
          <div className="bg-white rounded-2xl p-8 w-full max-w-md shadow-2xl">
            <h3 className="text-lg font-bold mb-5" style={{ color: "#0f2040" }}>Novo usuário</h3>
            <div className="space-y-4">
              {(["nome", "email"] as const).map((f) => (
                <div key={f}>
                  <label className="block text-xs font-semibold uppercase tracking-wider mb-1 text-slate-500">
                    {f === "nome" ? "Nome" : "E-mail"}
                  </label>
                  <Input
                    value={novoUser[f]}
                    onChange={(e) => setNovoUser((p) => ({ ...p, [f]: e.target.value }))}
                    placeholder={f === "nome" ? "Nome completo" : "email@empresa.com"}
                    className="h-10"
                  />
                </div>
              ))}
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider mb-1 text-slate-500">Senha</label>
                <div className="relative">
                  <Input
                    type={showNewPass ? "text" : "password"}
                    value={novoUser.senha}
                    onChange={(e) => setNovoUser((p) => ({ ...p, senha: e.target.value }))}
                    placeholder="Mínimo 6 caracteres"
                    className="h-10 pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setShowNewPass(!showNewPass)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 cursor-pointer"
                  >
                    {showNewPass ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider mb-1 text-slate-500">Perfil</label>
                <select
                  value={novoUser.perfil}
                  onChange={(e) => setNovoUser((p) => ({ ...p, perfil: e.target.value }))}
                  className="w-full h-10 px-3 rounded-md border text-sm"
                  style={{ borderColor: "var(--border,#e2e8f0)" }}
                >
                  <option value="USER">USER</option>
                  <option value="ADMIN">ADMIN</option>
                </select>
              </div>
              {createErro && <p className="text-xs text-red-500">{createErro}</p>}
            </div>
            <div className="flex gap-3 mt-6">
              <Button onClick={criarUser} disabled={creating} className="flex-1 text-white" style={{ background: "linear-gradient(135deg,#2E75B6,#1F3864)" }}>
                {creating ? "Criando…" : "Criar usuário"}
              </Button>
              <Button variant="outline" onClick={() => setShowCreate(false)} className="flex-1">Cancelar</Button>
            </div>
          </div>
        </div>
      )}

      {/* Modal — Reset Senha */}
      {resetTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: "rgba(0,0,0,.45)" }}>
          <div className="bg-white rounded-2xl p-8 w-full max-w-sm shadow-2xl">
            <h3 className="text-lg font-bold mb-2" style={{ color: "#0f2040" }}>Redefinir senha</h3>
            <p className="text-sm text-muted-foreground mb-5">{resetTarget.email}</p>
            <div className="relative mb-4">
              <Input
                type={showReset ? "text" : "password"}
                value={novaSenha}
                onChange={(e) => setNovaSenha(e.target.value)}
                placeholder="Nova senha (mín. 6 caracteres)"
                className="h-10 pr-10"
              />
              <button
                type="button"
                onClick={() => setShowReset(!showReset)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 cursor-pointer"
              >
                {showReset ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
            {resetErro && <p className="text-xs text-red-500 mb-3">{resetErro}</p>}
            <div className="flex gap-3">
              <Button onClick={resetSenha} disabled={resetting || novaSenha.length < 6} className="flex-1 text-white" style={{ background: "linear-gradient(135deg,#2E75B6,#1F3864)" }}>
                {resetting ? "Salvando…" : "Salvar"}
              </Button>
              <Button variant="outline" onClick={() => setResetTarget(null)} className="flex-1">Cancelar</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
