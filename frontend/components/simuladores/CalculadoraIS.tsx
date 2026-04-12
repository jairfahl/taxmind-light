"use client";
import { useState } from "react";
import { Card } from "@/components/shared/Card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import api from "@/lib/api";
import { GuiaSimulador } from "./GuiaSimulador";
import { GUIA_IMPACTO_IS } from "./guias";

const fmt = (v: number) =>
  new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(v);
const pct = (v: number) => `${(v * 100).toFixed(2)}%`;

const PRODUTOS = [
  { value: "tabaco",               label: "Tabaco (art. 412, I)" },
  { value: "bebidas_alcoolicas",   label: "Bebidas alcoólicas (art. 412, II)" },
  { value: "bebidas_acucaradas",   label: "Bebidas açucaradas (art. 412, III)" },
  { value: "veiculos",             label: "Veículos (art. 412, IV)" },
  { value: "embarcacoes",          label: "Embarcações (art. 412, V)" },
  { value: "minerais",             label: "Minerais (art. 412, VI)" },
];

interface ISResult {
  produto_label: string; base_legal: string;
  aliquota_usada: number; status_aliquota: string;
  is_por_unidade: number; preco_com_is: number;
  margem_atual: number; margem_com_is: number; delta_margem: number;
  receita_atual_mensal: number; receita_com_is_mensal: number; is_total_mensal: number;
  repassar_consumidor: { preco_final: number; reducao_volume_estimada_pct: number; volume_pos_repasse: number; margem_mantida: number };
  absorver_margem: { preco_final: number; reducao_volume: number; nova_margem: number; nova_margem_pct: number };
  ressalvas: string[];
}

export function CalculadoraIS() {
  const [form, setForm] = useState({
    produto: "bebidas_alcoolicas",
    preco_venda_atual: "20",
    volume_mensal: "10000",
    custo_producao: "8",
    elasticidade: "media",
    aliquota_customizada: "",
  });
  const [loading, setLoading] = useState(false);
  const [resultado, setResultado] = useState<ISResult | null>(null);
  const [erro, setErro] = useState("");

  const f = (k: string, v: string) => setForm((p) => ({ ...p, [k]: v }));

  const simular = async () => {
    setLoading(true); setErro(""); setResultado(null);
    try {
      const res = await api.post<ISResult>("/v1/simuladores/impacto-is", {
        produto:              form.produto,
        preco_venda_atual:    parseFloat(form.preco_venda_atual),
        volume_mensal:        parseInt(form.volume_mensal),
        custo_producao:       parseFloat(form.custo_producao),
        elasticidade:         form.elasticidade,
        aliquota_customizada: form.aliquota_customizada ? parseFloat(form.aliquota_customizada) / 100 : null,
      });
      setResultado(res.data);
    } catch { setErro("Erro ao simular."); }
    finally { setLoading(false); }
  };

  return (
    <div className="space-y-4">
      {/* Alerta obrigatório */}
      <div className="p-3 bg-red-50 border border-red-300 rounded-md">
        <p className="text-xs text-red-700 font-semibold">
          🔴 Alíquotas do IS não regulamentadas — simulação usa estimativas de mercado baseadas na EC 132/2023 e LC 214/2025
        </p>
      </div>

      <Card titulo="Parâmetros">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="sm:col-span-2">
            <label className="text-xs text-muted-foreground">Produto</label>
            <select value={form.produto} onChange={(e) => f("produto", e.target.value)}
              className="mt-1 w-full rounded border border-border bg-input px-3 py-2 text-sm text-foreground">
              {PRODUTOS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-muted-foreground">Preço de venda atual (R$)</label>
            <Input value={form.preco_venda_atual} onChange={(e) => f("preco_venda_atual", e.target.value)} className="mt-1 bg-input" />
          </div>
          <div>
            <label className="text-xs text-muted-foreground">Volume mensal (unidades)</label>
            <Input value={form.volume_mensal} onChange={(e) => f("volume_mensal", e.target.value)} className="mt-1 bg-input" />
          </div>
          <div>
            <label className="text-xs text-muted-foreground">Custo de produção/unidade (R$)</label>
            <Input value={form.custo_producao} onChange={(e) => f("custo_producao", e.target.value)} className="mt-1 bg-input" />
          </div>
          <div>
            <label className="text-xs text-muted-foreground">Elasticidade da demanda</label>
            <select value={form.elasticidade} onChange={(e) => f("elasticidade", e.target.value)}
              className="mt-1 w-full rounded border border-border bg-input px-3 py-2 text-sm text-foreground">
              <option value="alta">Alta (redução volume ~15%)</option>
              <option value="media">Média (redução volume ~8%)</option>
              <option value="baixa">Baixa (redução volume ~3%)</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-muted-foreground">Alíquota customizada % (opcional)</label>
            <Input value={form.aliquota_customizada} onChange={(e) => f("aliquota_customizada", e.target.value)}
              placeholder="Deixar vazio para usar estimativa de mercado" className="mt-1 bg-input" />
          </div>
        </div>
        {erro && <p className="text-xs text-red-600 mt-2">{erro}</p>}
        <Button onClick={simular} disabled={loading} className="mt-4 bg-primary text-primary-foreground w-full">
          {loading ? "Calculando…" : "Calcular impacto IS"}
        </Button>
        <GuiaSimulador {...GUIA_IMPACTO_IS} />
      </Card>

      {resultado && (
        <div className="space-y-4">
          <Card titulo={`Impacto IS — ${resultado.produto_label}`}>
            <p className="text-xs text-muted-foreground mb-3">
              {resultado.base_legal} · Alíquota {pct(resultado.aliquota_usada)} ({resultado.status_aliquota})
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-primary text-primary-foreground">
                    <th className="px-3 py-2 text-left">Métrica</th>
                    <th className="px-3 py-2 text-right">Atual</th>
                    <th className="px-3 py-2 text-right">Com IS</th>
                    <th className="px-3 py-2 text-right">Impacto</th>
                  </tr>
                </thead>
                <tbody>
                  {[
                    ["Preço/unidade", fmt(resultado.preco_com_is - resultado.is_por_unidade), fmt(resultado.preco_com_is), `+${fmt(resultado.is_por_unidade)}`],
                    ["Margem", pct(resultado.margem_atual), pct(resultado.margem_com_is), pct(resultado.delta_margem)],
                    ["Receita mensal", fmt(resultado.receita_atual_mensal), fmt(resultado.receita_com_is_mensal), fmt(resultado.is_total_mensal)],
                  ].map(([label, atual, com_is, delta], i) => (
                    <tr key={label} className={i % 2 === 0 ? "bg-card" : "bg-muted/30"}>
                      <td className="px-3 py-2 font-medium">{label}</td>
                      <td className="px-3 py-2 text-right">{atual}</td>
                      <td className="px-3 py-2 text-right">{com_is}</td>
                      <td className="px-3 py-2 text-right text-red-600 font-semibold">{delta}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Card titulo="Estratégia 1 — Repassar ao consumidor" acento="warning">
              <div className="space-y-1 text-xs">
                <div className="flex justify-between"><span className="text-muted-foreground">Preço final</span><span className="font-semibold">{fmt(resultado.repassar_consumidor.preco_final)}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">Redução de volume</span><span className="font-semibold text-amber-600">{pct(resultado.repassar_consumidor.reducao_volume_estimada_pct)}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">Volume pós-repasse</span><span className="font-semibold">{resultado.repassar_consumidor.volume_pos_repasse.toLocaleString("pt-BR")}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">Margem mantida</span><span className="font-semibold text-emerald-600">{pct(resultado.repassar_consumidor.margem_mantida)}</span></div>
              </div>
            </Card>
            <Card titulo="Estratégia 2 — Absorver na margem" acento="danger">
              <div className="space-y-1 text-xs">
                <div className="flex justify-between"><span className="text-muted-foreground">Preço mantido</span><span className="font-semibold">{fmt(resultado.absorver_margem.preco_final)}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">Volume perdido</span><span className="font-semibold">{resultado.absorver_margem.reducao_volume.toLocaleString("pt-BR")}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">Nova margem</span><span className="font-semibold text-red-600">{fmt(resultado.absorver_margem.nova_margem)}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">Nova margem %</span><span className="font-semibold text-red-600">{pct(resultado.absorver_margem.nova_margem_pct)}</span></div>
              </div>
            </Card>
          </div>

          {resultado.ressalvas.map((r, i) => (
            <p key={i} className="text-xs text-muted-foreground italic">⚠ {r}</p>
          ))}
        </div>
      )}
    </div>
  );
}
