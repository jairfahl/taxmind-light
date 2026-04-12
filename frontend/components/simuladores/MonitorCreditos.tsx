"use client";
import { useState } from "react";
import { Card } from "@/components/shared/Card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Plus, X } from "lucide-react";
import api from "@/lib/api";
import { GuiaSimulador } from "./GuiaSimulador";
import { GUIA_CREDITOS } from "./guias";

const fmt = (v: number) =>
  new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(v);

const CATEGORIAS = [
  { value: "insumos_diretos",          label: "Insumos diretos" },
  { value: "servicos_tomados",         label: "Serviços tomados" },
  { value: "ativo_imobilizado",        label: "Ativo imobilizado" },
  { value: "fornecedor_simples",       label: "Fornecedor Simples Nacional" },
  { value: "uso_consumo",              label: "Uso e consumo" },
  { value: "operacoes_imunes_isentas", label: "Operações imunes/isentas" },
  { value: "exportacoes",              label: "Exportações" },
];

const RISCO_COR: Record<string, string> = {
  baixo: "text-emerald-600", medio: "text-amber-600", alto: "text-red-600",
};

interface ItemInput { categoria: string; valor_mensal: string; }
interface ItemResult {
  categoria: string; label: string; creditamento: string;
  credito_estimado_mensal: number; credito_estimado_anual: number;
  risco: string; alerta: string;
}
interface CreditosResult {
  total_aquisicoes_mensal: number; total_credito_mensal: number;
  total_credito_anual: number; creditos_em_risco: number;
  itens: ItemResult[];
}

export function MonitorCreditos() {
  const [itens, setItens] = useState<ItemInput[]>([{ categoria: "insumos_diretos", valor_mensal: "100000" }]);
  const [loading, setLoading] = useState(false);
  const [resultado, setResultado] = useState<CreditosResult | null>(null);
  const [erro, setErro] = useState("");

  const addItem = () => setItens((p) => [...p, { categoria: "insumos_diretos", valor_mensal: "0" }]);
  const removeItem = (i: number) => setItens((p) => p.filter((_, j) => j !== i));
  const updateItem = (i: number, k: keyof ItemInput, v: string) =>
    setItens((p) => p.map((item, j) => j === i ? { ...item, [k]: v } : item));

  const simular = async () => {
    setLoading(true); setErro(""); setResultado(null);
    try {
      const res = await api.post<CreditosResult>("/v1/simuladores/creditos-ibs", {
        itens: itens.map((it) => ({ categoria: it.categoria, valor_mensal: parseFloat(it.valor_mensal) || 0 })),
      });
      setResultado(res.data);
    } catch { setErro("Erro ao simular."); }
    finally { setLoading(false); }
  };

  return (
    <div className="space-y-4">
      <Card titulo="Aquisições para mapeamento">
        <div className="space-y-2">
          {itens.map((item, i) => (
            <div key={i} className="flex gap-2 items-center">
              <select value={item.categoria} onChange={(e) => updateItem(i, "categoria", e.target.value)}
                className="flex-1 rounded border border-border bg-input px-2 py-1.5 text-xs text-foreground">
                {CATEGORIAS.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
              </select>
              <Input value={item.valor_mensal} onChange={(e) => updateItem(i, "valor_mensal", e.target.value)}
                placeholder="R$/mês" className="w-32 text-xs bg-input" />
              <button onClick={() => removeItem(i)} className="text-muted-foreground hover:text-red-500 cursor-pointer">
                <X size={14} />
              </button>
            </div>
          ))}
        </div>
        <div className="flex gap-2 mt-3">
          <Button variant="outline" size="sm" onClick={addItem} className="gap-1 text-xs">
            <Plus size={12} />Adicionar item
          </Button>
          <Button onClick={simular} disabled={loading} size="sm" className="bg-primary text-primary-foreground">
            {loading ? "Analisando…" : "Mapear créditos"}
          </Button>
        </div>
        {erro && <p className="text-xs text-red-600 mt-2">{erro}</p>}
        <GuiaSimulador {...GUIA_CREDITOS} />
      </Card>

      {resultado && (
        <Card titulo="Mapeamento de Créditos IBS/CBS">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
            {[
              ["Total aquisições/mês", fmt(resultado.total_aquisicoes_mensal)],
              ["Crédito mensal", fmt(resultado.total_credito_mensal)],
              ["Crédito anual",  fmt(resultado.total_credito_anual)],
              ["Créditos em risco", fmt(resultado.creditos_em_risco)],
            ].map(([label, value]) => (
              <div key={label} className="bg-muted/30 rounded p-2">
                <p className="text-xs text-muted-foreground">{label}</p>
                <p className="text-sm font-semibold">{value}</p>
              </div>
            ))}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-primary text-primary-foreground">
                  <th className="px-3 py-2 text-left">Categoria</th>
                  <th className="px-3 py-2 text-left">Creditamento</th>
                  <th className="px-3 py-2 text-right">Crédito/mês</th>
                  <th className="px-3 py-2 text-right">Crédito/ano</th>
                  <th className="px-3 py-2 text-left">Risco</th>
                </tr>
              </thead>
              <tbody>
                {resultado.itens.map((item, i) => (
                  <tr key={i} className={i % 2 === 0 ? "bg-card" : "bg-muted/30"}>
                    <td className="px-3 py-2">{item.label}</td>
                    <td className="px-3 py-2 font-medium">{item.creditamento}</td>
                    <td className="px-3 py-2 text-right text-emerald-600">{fmt(item.credito_estimado_mensal)}</td>
                    <td className="px-3 py-2 text-right text-emerald-600 font-semibold">{fmt(item.credito_estimado_anual)}</td>
                    <td className={`px-3 py-2 font-semibold ${RISCO_COR[item.risco] ?? ""}`}>{item.risco}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-muted-foreground italic mt-2">
            Mapeamento baseado na LC 214/2025. Creditamento definitivo sujeito a regulamentação do CGIBS.
          </p>
        </Card>
      )}
    </div>
  );
}
