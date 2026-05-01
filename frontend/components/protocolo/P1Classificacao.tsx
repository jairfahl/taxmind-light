"use client";
import { useState } from "react";
import { useProtocoloStore } from "@/store/protocolo";
import { useAuthStore } from "@/store/auth";
import { Card } from "@/components/shared/Card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Lightbulb, Info } from "lucide-react";
import api from "@/lib/api";

const METODOS_SUGERIDOS = [
  "Análise literal da norma",
  "Análise sistemática (LC 214 + EC 132)",
  "Análise histórico-evolutiva",
  "Análise teleológica",
];

export function P1Classificacao() {
  const { query, metodos, topK, set, setStep } = useProtocoloStore();
  const { user } = useAuthStore();
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
      const res = await api.post<{ case_id: string; status: string; passo_atual: number }>(
        "/v1/cases",
        { titulo: query.slice(0, 120), descricao: query, contexto_fiscal: query, user_id: user?.id ?? null }
      );
      set({ caseId: res.data.case_id });
      setStep(2);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      if (detail?.includes("Limite de casos")) {
        setErro(detail);
      } else {
        setErro("Erro ao criar o caso. Verifique a conexão com a API.");
      }
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
          <p className="flex items-start gap-1.5 text-xs text-muted-foreground mt-1 mb-2">
            <Lightbulb size={12} className="shrink-0 mt-0.5" />
            Quanto mais contexto você fornecer, mais precisa será a análise.
          </p>
          <details className="mb-2 text-xs text-muted-foreground">
            <summary className="cursor-pointer hover:text-foreground transition-colors">
              Dicas para uma boa consulta
            </summary>
            <ul className="mt-1.5 ml-4 space-y-0.5 list-disc">
              <li>Tipo de empresa ou contribuinte (Lucro Real, Simples Nacional, etc.)</li>
              <li>Operação ou transação em questão</li>
              <li>Legislação ou norma específica, se conhecida</li>
              <li>Tributos envolvidos (IBS, CBS, ISS, IRRF, etc.)</li>
              <li>Período fiscal relevante</li>
            </ul>
          </details>
          <Textarea
            value={query}
            onChange={(e) => set({ query: e.target.value })}
            placeholder={"Ex.: Empresa optante pelo Lucro Real realiza importação de serviços. Dúvida sobre incidência de ISS e IRRF na operação, considerando o art. 156-A da CF e a LC 214/2025..."}
            className="mt-1 min-h-28 resize-none text-sm bg-input border-border"
          />
          <p className="text-xs text-muted-foreground mt-1">{query.length} caracteres</p>
        </div>

        <div>
          <div className="flex items-center gap-1.5 mb-2">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Métodos de análise (opcional — máx. 4)
            </p>
            <div className="group relative">
              <Info size={13} className="text-muted-foreground cursor-help" />
              <div className="absolute left-0 bottom-5 z-10 hidden group-hover:block w-72 rounded-lg border border-border bg-popover p-3 shadow-md text-xs text-foreground leading-relaxed">
                <p className="font-semibold mb-1">Para que servem?</p>
                <p className="mb-2">Orientam a lente interpretativa que a IA usará ao analisar sua consulta. Cada método produz conclusões diferentes sobre o mesmo dispositivo legal.</p>
                <ul className="space-y-1 text-muted-foreground">
                  <li><span className="text-foreground font-medium">Literal</span> — interpreta o texto exato da norma, sem extrapolações.</li>
                  <li><span className="text-foreground font-medium">Sistemática</span> — cruza a norma com outras leis relacionadas (ex.: LC 214 + EC 132).</li>
                  <li><span className="text-foreground font-medium">Histórico-evolutiva</span> — analisa como o dispositivo evoluiu ao longo das reformas.</li>
                  <li><span className="text-foreground font-medium">Teleológica</span> — interpreta pela finalidade e intenção do legislador.</li>
                </ul>
                <p className="mt-2 text-muted-foreground">Se nenhum for selecionado, a IA escolhe automaticamente o mais adequado.</p>
              </div>
            </div>
          </div>
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
