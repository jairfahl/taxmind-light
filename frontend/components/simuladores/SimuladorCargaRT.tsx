"use client";
import { useState } from "react";
import { Card } from "@/components/shared/Card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import api from "@/lib/api";
import { GuiaSimulador } from "./GuiaSimulador";
import { GUIA_CARGA_RT } from "./guias";

const fmt = (v: number) =>
  new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(v);
const pct = (v: number) => `${(v * 100).toFixed(2)}%`;

interface AnoResult {
  ano: number;
  atual: { carga_liquida: number; aliquota_efetiva: number };
  novo:  { carga_liquida: number; aliquota_efetiva: number };
}

export function SimuladorCargaRT() {
  const [form, setForm] = useState({
    faturamento_anual: "10000000",
    regime_tributario: "lucro_real",
    tipo_operacao: "misto",
    percentual_exportacao: "0",
    percentual_credito_novo: "100",
  });
  const [loading, setLoading] = useState(false);
  const [resultado, setResultado] = useState<AnoResult[] | null>(null);
  const [erro, setErro] = useState("");

  const simular = async () => {
    setLoading(true); setErro(""); setResultado(null);
    try {
      const res = await api.post<{ resultados: AnoResult[] }>("/v1/simuladores/carga-rt", {
        faturamento_anual:     parseFloat(form.faturamento_anual),
        regime_tributario:     form.regime_tributario,
        tipo_operacao:         form.tipo_operacao,
        percentual_exportacao: parseFloat(form.percentual_exportacao) / 100,
        percentual_credito_novo: parseFloat(form.percentual_credito_novo) / 100,
      });
      setResultado(res.data.resultados);
    } catch {
      setErro("Erro ao simular. Verifique os dados.");
    } finally {
      setLoading(false);
    }
  };

  const f = (k: string, v: string) => setForm((p) => ({ ...p, [k]: v }));

  return (
    <div className="space-y-4">
      <Card titulo="Parâmetros">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-muted-foreground">Faturamento anual (R$)</label>
            <Input value={form.faturamento_anual} onChange={(e) => f("faturamento_anual", e.target.value)} className="mt-1 bg-input" />
          </div>
          <div>
            <label className="text-xs text-muted-foreground">Regime tributário</label>
            <select value={form.regime_tributario} onChange={(e) => f("regime_tributario", e.target.value)}
              className="mt-1 w-full rounded border border-border bg-input px-3 py-2 text-sm text-foreground">
              <option value="lucro_real">Lucro Real</option>
              <option value="lucro_presumido">Lucro Presumido</option>
              <option value="simples_nacional">Simples Nacional</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-muted-foreground">Tipo de operação</label>
            <select value={form.tipo_operacao} onChange={(e) => f("tipo_operacao", e.target.value)}
              className="mt-1 w-full rounded border border-border bg-input px-3 py-2 text-sm text-foreground">
              <option value="misto">Misto</option>
              <option value="so_mercadorias">Só mercadorias</option>
              <option value="so_servicos">Só serviços</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-muted-foreground">% Exportação (0-100)</label>
            <Input value={form.percentual_exportacao} onChange={(e) => f("percentual_exportacao", e.target.value)} className="mt-1 bg-input" />
          </div>
          <div>
            <label className="text-xs text-muted-foreground">% Aproveitamento créditos novo (0-100)</label>
            <Input value={form.percentual_credito_novo} onChange={(e) => f("percentual_credito_novo", e.target.value)} className="mt-1 bg-input" />
          </div>
        </div>
        {erro && <p className="text-xs text-red-600 mt-2">{erro}</p>}
        <Button onClick={simular} disabled={loading} className="mt-4 bg-primary text-primary-foreground w-full">
          {loading ? "Simulando…" : "Simular"}
        </Button>
        <GuiaSimulador {...GUIA_CARGA_RT} />
      </Card>

      {resultado && (
        <Card titulo="Carga Tributária — Regime Atual vs Novo (2024→2033)">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-primary text-primary-foreground">
                  <th className="px-3 py-2 text-left">Ano</th>
                  <th className="px-3 py-2 text-right">Carga Líquida Atual</th>
                  <th className="px-3 py-2 text-right">Alíq. Efetiva Atual</th>
                  <th className="px-3 py-2 text-right">Carga Líquida Novo</th>
                  <th className="px-3 py-2 text-right">Alíq. Efetiva Nova</th>
                  <th className="px-3 py-2 text-right">Δ Carga</th>
                </tr>
              </thead>
              <tbody>
                {resultado.map((r, i) => {
                  const delta = r.novo.carga_liquida - r.atual.carga_liquida;
                  return (
                    <tr key={r.ano} className={i % 2 === 0 ? "bg-card" : "bg-muted/30"}>
                      <td className="px-3 py-2 font-semibold">{r.ano}</td>
                      <td className="px-3 py-2 text-right">{fmt(r.atual.carga_liquida)}</td>
                      <td className="px-3 py-2 text-right">{pct(r.atual.aliquota_efetiva)}</td>
                      <td className="px-3 py-2 text-right">{fmt(r.novo.carga_liquida)}</td>
                      <td className="px-3 py-2 text-right">{pct(r.novo.aliquota_efetiva)}</td>
                      <td className={`px-3 py-2 text-right font-semibold ${delta > 0 ? "text-red-600" : "text-emerald-600"}`}>
                        {delta > 0 ? "+" : ""}{fmt(delta)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-muted-foreground italic mt-2">
            Simulação baseada em alíquotas da LC 214/2025. Resultados estimados — sujeitos a regulamentação do CGIBS.
          </p>
        </Card>
      )}
    </div>
  );
}
