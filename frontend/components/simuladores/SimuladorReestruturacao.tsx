"use client";
import { useState } from "react";
import { Card } from "@/components/shared/Card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Plus, X } from "lucide-react";
import api from "@/lib/api";
import { GuiaSimulador } from "./GuiaSimulador";
import { GUIA_REESTRUTURACAO } from "./guias";

const fmt = (v: number) =>
  new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(v);

const REC_COR: Record<string, string> = {
  manter: "text-emerald-600", revisar: "text-amber-600", encerrar: "text-red-600",
};

interface UnidadeInput { uf: string; tipo: string; custo_fixo_anual: string; faturamento_anual: string; }
interface UnidadeResult {
  uf: string; tipo: string; beneficio_icms_atual: number; beneficio_icms_2033: number;
  economia_icms_perdida: number; custo_manutencao: number;
  recomendacao: string; justificativa: string; ano_decisao_critica: number;
}
interface ReestResult {
  unidades: UnidadeResult[]; economia_total_perdida_anual: number;
  unidades_revisar: number; unidades_encerrar: number; ressalvas: string[];
}

const UFS = ["AC","AL","AP","AM","BA","CE","DF","ES","GO","MA","MT","MS","MG","PA","PB","PR","PE","PI","RJ","RN","RS","RO","RR","SC","SP","SE","TO"];

export function SimuladorReestruturacao() {
  const [unidades, setUnidades] = useState<UnidadeInput[]>([
    { uf: "SP", tipo: "filial", custo_fixo_anual: "500000", faturamento_anual: "3000000" },
  ]);
  const [loading, setLoading] = useState(false);
  const [resultado, setResultado] = useState<ReestResult | null>(null);
  const [erro, setErro] = useState("");

  const add = () => setUnidades((p) => [...p, { uf: "MG", tipo: "filial", custo_fixo_anual: "0", faturamento_anual: "0" }]);
  const remove = (i: number) => setUnidades((p) => p.filter((_, j) => j !== i));
  const upd = (i: number, k: keyof UnidadeInput, v: string) =>
    setUnidades((p) => p.map((u, j) => j === i ? { ...u, [k]: v } : u));

  const simular = async () => {
    setLoading(true); setErro(""); setResultado(null);
    try {
      const res = await api.post<ReestResult>("/v1/simuladores/reestruturacao", {
        unidades: unidades.map((u) => ({
          uf: u.uf, tipo: u.tipo,
          custo_fixo_anual: parseFloat(u.custo_fixo_anual) || 0,
          faturamento_anual: parseFloat(u.faturamento_anual) || 0,
        })),
        ano_analise: new Date().getFullYear(),
      });
      setResultado(res.data);
    } catch { setErro("Erro ao simular."); }
    finally { setLoading(false); }
  };

  return (
    <div className="space-y-4">
      <Card titulo="Unidades Operacionais">
        <div className="space-y-3">
          {unidades.map((u, i) => (
            <div key={i} className="grid grid-cols-5 gap-2 items-end">
              <div>
                <label className="text-xs text-muted-foreground">UF</label>
                <select value={u.uf} onChange={(e) => upd(i, "uf", e.target.value)}
                  className="mt-1 w-full rounded border border-border bg-input px-2 py-1.5 text-xs text-foreground">
                  {UFS.map((uf) => <option key={uf} value={uf}>{uf}</option>)}
                </select>
              </div>
              <div>
                <label className="text-xs text-muted-foreground">Tipo</label>
                <select value={u.tipo} onChange={(e) => upd(i, "tipo", e.target.value)}
                  className="mt-1 w-full rounded border border-border bg-input px-2 py-1.5 text-xs text-foreground">
                  {["CD","planta","filial","escritorio"].map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
              <div>
                <label className="text-xs text-muted-foreground">Custo fixo/ano</label>
                <Input value={u.custo_fixo_anual} onChange={(e) => upd(i, "custo_fixo_anual", e.target.value)} className="mt-1 text-xs bg-input" />
              </div>
              <div>
                <label className="text-xs text-muted-foreground">Faturamento/ano</label>
                <Input value={u.faturamento_anual} onChange={(e) => upd(i, "faturamento_anual", e.target.value)} className="mt-1 text-xs bg-input" />
              </div>
              <button onClick={() => remove(i)} className="text-muted-foreground hover:text-red-500 cursor-pointer pb-2">
                <X size={14} />
              </button>
            </div>
          ))}
        </div>
        <div className="flex gap-2 mt-3">
          <Button variant="outline" size="sm" onClick={add} className="gap-1 text-xs">
            <Plus size={12} />Adicionar unidade
          </Button>
          <Button onClick={simular} disabled={loading} size="sm" className="bg-primary text-primary-foreground">
            {loading ? "Analisando…" : "Analisar reestruturação"}
          </Button>
        </div>
        {erro && <p className="text-xs text-red-600 mt-2">{erro}</p>}
        <GuiaSimulador {...GUIA_REESTRUTURACAO} />
      </Card>

      {resultado && (
        <Card titulo="Análise por Unidade">
          <div className="grid grid-cols-3 gap-3 mb-4">
            <div className="bg-muted/30 rounded p-2">
              <p className="text-xs text-muted-foreground">Economia ICMS perdida/ano</p>
              <p className="text-sm font-semibold text-red-600">{fmt(resultado.economia_total_perdida_anual)}</p>
            </div>
            <div className="bg-amber-50 rounded p-2 border border-amber-200">
              <p className="text-xs text-muted-foreground">Unidades para revisar</p>
              <p className="text-sm font-semibold text-amber-700">{resultado.unidades_revisar}</p>
            </div>
            <div className="bg-red-50 rounded p-2 border border-red-200">
              <p className="text-xs text-muted-foreground">Unidades para encerrar</p>
              <p className="text-sm font-semibold text-red-700">{resultado.unidades_encerrar}</p>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-primary text-primary-foreground">
                  <th className="px-3 py-2 text-left">UF / Tipo</th>
                  <th className="px-3 py-2 text-right">Benefício ICMS 2026</th>
                  <th className="px-3 py-2 text-right">Benefício ICMS 2033</th>
                  <th className="px-3 py-2 text-right">Economia perdida/ano</th>
                  <th className="px-3 py-2 text-left">Recomendação</th>
                  <th className="px-3 py-2 text-left">Decisão crítica</th>
                </tr>
              </thead>
              <tbody>
                {resultado.unidades.map((u, i) => (
                  <tr key={i} className={i % 2 === 0 ? "bg-card" : "bg-muted/30"}>
                    <td className="px-3 py-2 font-medium">{u.uf} — {u.tipo}</td>
                    <td className="px-3 py-2 text-right">{fmt(u.beneficio_icms_atual)}</td>
                    <td className="px-3 py-2 text-right text-red-600">{fmt(u.beneficio_icms_2033)}</td>
                    <td className="px-3 py-2 text-right text-red-600 font-semibold">{fmt(u.economia_icms_perdida)}</td>
                    <td className={`px-3 py-2 font-bold uppercase ${REC_COR[u.recomendacao] ?? ""}`}>{u.recomendacao}</td>
                    <td className="px-3 py-2">{u.ano_decisao_critica}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {resultado.ressalvas.map((r, i) => (
            <p key={i} className="text-xs text-muted-foreground italic mt-1">⚠ {r}</p>
          ))}
        </Card>
      )}
    </div>
  );
}
