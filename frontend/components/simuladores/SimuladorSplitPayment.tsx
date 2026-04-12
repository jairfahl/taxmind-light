"use client";
import { useState } from "react";
import { Card } from "@/components/shared/Card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import api from "@/lib/api";
import { GuiaSimulador } from "./GuiaSimulador";
import { GUIA_SPLIT_PAYMENT } from "./guias";

const fmt = (v: number) =>
  new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(v);
const pct = (v: number) => `${(v * 100).toFixed(3)}%`;

interface Modalidade {
  modalidade: string;
  nome_completo: string;
  float_perdido_mensal: number;
  custo_financeiro_mensal: number;
  custo_financeiro_anual: number;
  impacto_margem_pct: number;
  capital_giro_adicional: number;
  ressalvas: string[];
}

interface SplitResult {
  faturamento_mensal: number;
  modalidades: Modalidade[];
  recomendacao: string;
  status_aliquotas: string;
}

export function SimuladorSplitPayment() {
  const [form, setForm] = useState({
    faturamento_mensal: "1000000",
    pct_vista: "50", pct_prazo: "50",
    prazo_medio_dias: "30",
    taxa_captacao_am: "2",
    pct_inadimplencia: "2",
    pct_creditos: "60",
  });
  const [loading, setLoading] = useState(false);
  const [resultado, setResultado] = useState<SplitResult | null>(null);
  const [erro, setErro] = useState("");

  const simular = async () => {
    setLoading(true); setErro(""); setResultado(null);
    try {
      const res = await api.post<SplitResult>("/v1/simuladores/split-payment", {
        faturamento_mensal:   parseFloat(form.faturamento_mensal),
        pct_vista:            parseFloat(form.pct_vista) / 100,
        pct_prazo:            parseFloat(form.pct_prazo) / 100,
        prazo_medio_dias:     parseInt(form.prazo_medio_dias),
        taxa_captacao_am:     parseFloat(form.taxa_captacao_am) / 100,
        pct_inadimplencia:    parseFloat(form.pct_inadimplencia) / 100,
        pct_creditos:         parseFloat(form.pct_creditos) / 100,
      });
      setResultado(res.data);
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
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {[
            ["faturamento_mensal", "Faturamento mensal (R$)"],
            ["pct_vista", "% Vendas à vista"],
            ["pct_prazo", "% Vendas a prazo"],
            ["prazo_medio_dias", "Prazo médio (dias)"],
            ["taxa_captacao_am", "Taxa captação a.m. (%)"],
            ["pct_inadimplencia", "% Inadimplência"],
            ["pct_creditos", "% Créditos a compensar"],
          ].map(([k, label]) => (
            <div key={k}>
              <label className="text-xs text-muted-foreground">{label}</label>
              <Input value={form[k as keyof typeof form]} onChange={(e) => f(k, e.target.value)} className="mt-1 bg-input" />
            </div>
          ))}
        </div>
        {erro && <p className="text-xs text-red-600 mt-2">{erro}</p>}
        <Button onClick={simular} disabled={loading} className="mt-4 bg-primary text-primary-foreground w-full">
          {loading ? "Simulando…" : "Simular"}
        </Button>
        <GuiaSimulador {...GUIA_SPLIT_PAYMENT} />
      </Card>

      {resultado && (
        <Card titulo="Impacto por Modalidade de Split Payment">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-primary text-primary-foreground">
                  <th className="px-3 py-2 text-left">Modalidade</th>
                  <th className="px-3 py-2 text-right">Float perdido/mês</th>
                  <th className="px-3 py-2 text-right">Custo financeiro/mês</th>
                  <th className="px-3 py-2 text-right">Custo financeiro/ano</th>
                  <th className="px-3 py-2 text-right">Impacto margem</th>
                  <th className="px-3 py-2 text-right">Capital giro adicional</th>
                </tr>
              </thead>
              <tbody>
                {resultado.modalidades.map((m, i) => (
                  <tr key={m.modalidade} className={i % 2 === 0 ? "bg-card" : "bg-muted/30"}>
                    <td className="px-3 py-2 font-medium">{m.nome_completo}</td>
                    <td className="px-3 py-2 text-right text-red-600">{fmt(m.float_perdido_mensal)}</td>
                    <td className="px-3 py-2 text-right text-red-600">{fmt(m.custo_financeiro_mensal)}</td>
                    <td className="px-3 py-2 text-right text-red-600 font-semibold">{fmt(m.custo_financeiro_anual)}</td>
                    <td className="px-3 py-2 text-right text-red-600">{pct(m.impacto_margem_pct)}</td>
                    <td className="px-3 py-2 text-right">{fmt(m.capital_giro_adicional)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-3 p-3 bg-primary/10 border border-primary/20 rounded">
            <p className="text-xs font-semibold text-primary">Recomendação</p>
            <p className="text-xs mt-1">{resultado.recomendacao}</p>
          </div>
          <p className="text-xs text-muted-foreground italic mt-2">
            Alíquotas: {resultado.status_aliquotas}. Simulação baseada na LC 214/2025 — regulamentação do split pendente.
          </p>
        </Card>
      )}
    </div>
  );
}
