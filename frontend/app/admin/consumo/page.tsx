"use client";
import { useEffect, useState, useCallback } from "react";
import { Shield, RefreshCw, DollarSign, Zap, TrendingUp } from "lucide-react";
import { AdminNav } from "@/components/admin/AdminNav";
import { Card } from "@/components/shared/Card";
import api from "@/lib/api";

interface Resumo {
  total_gasto: number;
  total_chamadas: number;
  periodo_inicio: string | null;
  periodo_fim: string | null;
}

interface PorDia {
  dia: string;
  custo: number;
  chamadas: number;
}

interface PorTenant {
  tenant_id: string | null;
  razao_social: string;
  custo: number;
  chamadas: number;
}

interface PorServico {
  service: string;
  model: string;
  custo: number;
  chamadas: number;
}

interface ConsumoData {
  resumo: Resumo;
  por_dia: PorDia[];
  por_tenant: PorTenant[];
  por_servico: PorServico[];
}

const PERIODOS = [
  { label: "7 dias",  value: 7 },
  { label: "30 dias", value: 30 },
  { label: "90 dias", value: 90 },
] as const;

export default function ConsumoAdminPage() {
  const [data, setData]       = useState<ConsumoData | null>(null);
  const [loading, setLoading] = useState(true);
  const [erro, setErro]       = useState("");
  const [dias, setDias]       = useState(30);

  const fetchConsumo = useCallback(async () => {
    setLoading(true);
    setErro("");
    try {
      const res = await api.get<ConsumoData>("/v1/admin/consumo", { params: { dias } });
      setData(res.data);
    } catch {
      setErro("Erro ao carregar dados de consumo.");
    } finally {
      setLoading(false);
    }
  }, [dias]);

  useEffect(() => { fetchConsumo(); }, [fetchConsumo]);

  const custoMedio = data && data.resumo.total_chamadas > 0
    ? (data.resumo.total_gasto / data.resumo.total_chamadas)
    : 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Shield size={20} className="text-primary" />
          <h1 className="text-2xl font-semibold">Painel Admin</h1>
        </div>
        <button
          onClick={fetchConsumo}
          className="p-2 rounded-md hover:bg-slate-100 transition-colors cursor-pointer"
        >
          <RefreshCw size={16} className="text-slate-500" />
        </button>
      </div>

      <AdminNav />

      {/* Filtro de período */}
      <div className="flex flex-wrap gap-1 bg-slate-100 rounded-lg p-1 w-fit">
        {PERIODOS.map((p) => (
          <button
            key={p.value}
            onClick={() => setDias(p.value)}
            className="px-3 py-1 text-xs font-medium rounded-md transition-colors cursor-pointer"
            style={dias === p.value
              ? { background: "#fff", color: "#1F3864", boxShadow: "0 1px 3px rgba(0,0,0,.1)" }
              : { color: "#64748b" }
            }
          >
            {p.label}
          </button>
        ))}
      </div>

      {erro && <p className="text-sm text-red-500">{erro}</p>}

      {loading ? (
        <p className="text-sm text-muted-foreground py-8 text-center">Carregando...</p>
      ) : data ? (
        <>
          {/* Cards resumo */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <Card>
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-emerald-50">
                  <DollarSign size={18} className="text-emerald-600" />
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Total gasto</p>
                  <p className="text-xl font-bold text-foreground">US$ {data.resumo.total_gasto.toFixed(2)}</p>
                </div>
              </div>
            </Card>
            <Card>
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-blue-50">
                  <Zap size={18} className="text-blue-600" />
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Total chamadas</p>
                  <p className="text-xl font-bold text-foreground">{data.resumo.total_chamadas.toLocaleString("pt-BR")}</p>
                </div>
              </div>
            </Card>
            <Card>
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-amber-50">
                  <TrendingUp size={18} className="text-amber-600" />
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Custo medio/chamada</p>
                  <p className="text-xl font-bold text-foreground">US$ {custoMedio.toFixed(4)}</p>
                </div>
              </div>
            </Card>
          </div>

          {/* Tabela por tenant */}
          <Card>
            <h2 className="text-sm font-semibold text-foreground mb-3">Consumo por Tenant</h2>
            {data.por_tenant.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-4">Sem dados no periodo.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left" style={{ borderColor: "var(--border,#e2e8f0)" }}>
                      {["Empresa", "Custo (US$)", "Chamadas"].map((h) => (
                        <th key={h} className="pb-2 pr-4 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.por_tenant.map((t, i) => (
                      <tr
                        key={t.tenant_id ?? `sys-${i}`}
                        className="border-b last:border-0 hover:bg-slate-50 transition-colors"
                        style={{ borderColor: "var(--border,#e2e8f0)" }}
                      >
                        <td className="py-2.5 pr-4 font-medium text-foreground">{t.razao_social}</td>
                        <td className="py-2.5 pr-4 text-muted-foreground">{t.custo.toFixed(4)}</td>
                        <td className="py-2.5 text-muted-foreground">{t.chamadas.toLocaleString("pt-BR")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          {/* Tabela por servico/modelo */}
          <Card>
            <h2 className="text-sm font-semibold text-foreground mb-3">Consumo por Servico / Modelo</h2>
            {data.por_servico.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-4">Sem dados no periodo.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left" style={{ borderColor: "var(--border,#e2e8f0)" }}>
                      {["Servico", "Modelo", "Custo (US$)", "Chamadas"].map((h) => (
                        <th key={h} className="pb-2 pr-4 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.por_servico.map((s) => (
                      <tr
                        key={`${s.service}-${s.model}`}
                        className="border-b last:border-0 hover:bg-slate-50 transition-colors"
                        style={{ borderColor: "var(--border,#e2e8f0)" }}
                      >
                        <td className="py-2.5 pr-4 font-medium text-foreground">{s.service}</td>
                        <td className="py-2.5 pr-4 text-muted-foreground">{s.model}</td>
                        <td className="py-2.5 pr-4 text-muted-foreground">{s.custo.toFixed(4)}</td>
                        <td className="py-2.5 text-muted-foreground">{s.chamadas.toLocaleString("pt-BR")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          {/* Tabela por dia */}
          <Card>
            <h2 className="text-sm font-semibold text-foreground mb-3">Consumo por Dia</h2>
            {data.por_dia.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-4">Sem dados no periodo.</p>
            ) : (
              <div className="overflow-x-auto max-h-80 overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-white">
                    <tr className="border-b text-left" style={{ borderColor: "var(--border,#e2e8f0)" }}>
                      {["Dia", "Custo (US$)", "Chamadas"].map((h) => (
                        <th key={h} className="pb-2 pr-4 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.por_dia.map((d) => (
                      <tr
                        key={d.dia}
                        className="border-b last:border-0 hover:bg-slate-50 transition-colors"
                        style={{ borderColor: "var(--border,#e2e8f0)" }}
                      >
                        <td className="py-2.5 pr-4 font-medium text-foreground whitespace-nowrap">
                          {new Date(d.dia + "T00:00:00").toLocaleDateString("pt-BR")}
                        </td>
                        <td className="py-2.5 pr-4 text-muted-foreground">{d.custo.toFixed(4)}</td>
                        <td className="py-2.5 text-muted-foreground">{d.chamadas.toLocaleString("pt-BR")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      ) : null}
    </div>
  );
}
