"use client";
import { useState } from "react";
import { useProtocoloStore } from "@/store/protocolo";
import { Card } from "@/components/shared/Card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import api from "@/lib/api";

const METODOS_SUGERIDOS = [
  "Análise literal da norma",
  "Análise sistemática (LC 214 + EC 132)",
  "Análise histórico-evolutiva",
  "Análise teleológica",
];

export function P1Classificacao() {
  const { query, metodos, topK, set, setStep } = useProtocoloStore();
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState("");

  const toggleMetodo = (m: string) => {
    set({ metodos: metodos.includes(m) ? metodos.filter((x) => x !== m) : [...metodos, m] });
  };

  const avancar = async () => {
    if (!query.trim()) { setErro("Descreva a consulta tributária."); return; }
    setLoading(true);
    setErro("");
    try {
      const res = await api.post<{ case_id: number; status: string; passo_atual: number }>(
        "/v1/cases",
        { titulo: query.slice(0, 120), descricao: query, contexto_fiscal: query }
      );
      set({ caseId: res.data.case_id });
      setStep(2);
    } catch {
      setErro("Erro ao criar o caso. Verifique a conexão com a API.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card titulo="P1 — Qualificação da Consulta">
      <div className="space-y-4">
        <div>
          <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
            Consulta tributária
          </label>
          <Textarea
            value={query}
            onChange={(e) => set({ query: e.target.value })}
            placeholder="Descreva a situação ou questão tributária que precisa ser analisada…"
            className="mt-1 min-h-28 resize-none text-sm bg-input border-border"
          />
          <p className="text-xs text-muted-foreground mt-1">{query.length} caracteres</p>
        </div>

        <div>
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
            Métodos de análise (opcional — máx. 4)
          </p>
          <div className="flex flex-wrap gap-2">
            {METODOS_SUGERIDOS.map((m) => (
              <button
                key={m}
                onClick={() => toggleMetodo(m)}
                className={`text-xs px-3 py-1.5 rounded-full border transition-colors cursor-pointer ${
                  metodos.includes(m)
                    ? "bg-primary text-primary-foreground border-primary"
                    : "border-border text-muted-foreground hover:border-primary hover:text-foreground"
                }`}
              >
                {m}
              </button>
            ))}
          </div>
        </div>

        {/* Slider top_k */}
        <div className="pt-3 border-t border-border">
          <div className="flex items-center justify-between mb-1">
            <label className="text-xs font-medium text-muted-foreground">
              Trechos consultados
            </label>
            <span className="text-xs font-semibold text-primary tabular-nums">{topK}</span>
          </div>
          <input
            type="range"
            min={3}
            max={10}
            value={topK}
            onChange={(e) => set({ topK: Number(e.target.value) })}
            className="w-full h-1.5 rounded-full appearance-none cursor-pointer bg-border accent-primary"
          />
          <div className="flex justify-between text-xs text-muted-foreground mt-0.5">
            <span>3</span>
            <span className="text-muted-foreground/60">Mais trechos = resposta mais completa, porém mais lenta</span>
            <span>10</span>
          </div>
        </div>

        {erro && <p className="text-xs text-red-600">{erro}</p>}

        <Button
          onClick={avancar}
          disabled={loading || !query.trim()}
          className="bg-primary text-primary-foreground w-full"
        >
          {loading ? "Criando caso…" : "Confirmar e estruturar →"}
        </Button>
      </div>
    </Card>
  );
}
