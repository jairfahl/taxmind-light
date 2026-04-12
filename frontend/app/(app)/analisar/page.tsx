"use client";
import { useState } from "react";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Send, AlertCircle } from "lucide-react";
import { Card } from "@/components/shared/Card";
import { BadgeCriticidade } from "@/components/shared/BadgeCriticidade";
import { PainelGovernanca } from "@/components/shared/PainelGovernanca";
import { AnalysisLoading } from "@/components/shared/AnalysisLoading";
import { CTADocumentar } from "@/components/analisar/CTADocumentar";
import api from "@/lib/api";
import axios from "axios";
import { useAuthStore } from "@/store/auth";
import type { ResultadoAnalise } from "@/types";

export default function AnalisarPage() {
  const { user } = useAuthStore();
  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState(5);
  const [loading, setLoading] = useState(false);
  const [resultado, setResultado] = useState<ResultadoAnalise | null>(null);
  const [erro, setErro] = useState<{ tipo: "fora_escopo" | "generico"; mensagem: string } | null>(null);

  const analisar = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setErro(null);
    setResultado(null);
    try {
      const res = await api.post<ResultadoAnalise>("/v1/analyze", {
        query,
        top_k: topK,
        user_id: user?.id ?? null,
      });
      setResultado(res.data);
    } catch (e: unknown) {
      if (axios.isAxiosError(e) && e.response?.status === 400) {
        setErro({ tipo: "fora_escopo", mensagem: "" });
      } else {
        setErro({ tipo: "generico", mensagem: "Erro ao processar. Verifique a conexão com a API." });
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-5">
      {/* Cabeçalho */}
      <div>
        <h1 className="text-2xl font-semibold">Analisar</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Fundamentação legislativa da Reforma Tributária em segundos.
        </p>
      </div>

      {/* Campo de consulta */}
      <Card>
        <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
          Qual é sua dúvida tributária?
        </label>
        <Textarea
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) analisar();
          }}
          placeholder="Descreva sua situação em linguagem natural. Ex: Somos um supermercado no Lucro Real. Como fica nossa carga de IBS/CBS a partir de 2027?"
          className="mt-2 min-h-32 bg-input border-border resize-none text-sm"
        />
        {/* Slider top_k */}
        <div className="mt-4 pt-4 border-t border-border">
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
            onChange={(e) => setTopK(Number(e.target.value))}
            className="w-full h-1.5 rounded-full appearance-none cursor-pointer bg-border accent-primary"
          />
          <div className="flex justify-between text-xs text-muted-foreground mt-0.5">
            <span>3</span>
            <span className="text-xs text-muted-foreground/60">Mais trechos = resposta mais completa, porém mais lenta</span>
            <span>10</span>
          </div>
        </div>

        <div className="flex justify-between items-center mt-3">
          <p className="text-xs text-muted-foreground">
            {query.length > 0
              ? `${query.length} caracteres · Cmd+Enter para analisar`
              : "Cmd+Enter para analisar"}
          </p>
          <Button
            onClick={analisar}
            disabled={loading || !query.trim()}
            className="bg-primary hover:bg-primary/90 text-primary-foreground gap-2"
          >
            <Send size={14} />
            {loading ? "Analisando…" : "Analisar"}
          </Button>
        </div>
      </Card>

      {/* Loading */}
      {loading && <AnalysisLoading />}

      {/* Erro fora de escopo */}
      {erro && erro.tipo === "fora_escopo" && (
        <Card>
          <div className="flex gap-3 items-start">
            <AlertCircle size={18} className="text-amber-500 mt-0.5 shrink-0" />
            <div>
              <p className="text-sm font-medium text-amber-700">
                Essa informação não faz parte do propósito do Tribus-AI.
              </p>
              <p className="text-sm text-muted-foreground mt-1">
                Tente uma consulta mais adequada ao ecossistema tributário da Reforma Tributária brasileira — como alíquotas do IVA Dual, regras de CBS/IBS, benefícios fiscais ou impactos setoriais.
              </p>
            </div>
          </div>
        </Card>
      )}
      {erro && erro.tipo === "generico" && (
        <Card acento="danger">
          <p className="text-sm text-red-600">{erro.mensagem}</p>
        </Card>
      )}

      {/* Resultado */}
      {resultado && !loading && (
        <div className="space-y-4">
          <BadgeCriticidade nivel={resultado.criticidade} />

          {resultado.alertas_vigencia
            ?.filter((a) => a.alerta)
            .map((a, i) => (
              <div key={i} className="p-3 bg-amber-50 border border-amber-200 rounded-md">
                <p className="text-xs text-amber-700">{a.mensagem}</p>
              </div>
            ))}

          <Card titulo="Análise" acento="primary">
            <p className="text-sm leading-relaxed whitespace-pre-wrap text-foreground">
              {resultado.resposta}
            </p>
            <PainelGovernanca
              grau={resultado.grau_consolidacao}
              forcaContraTese={resultado.forca_corrente_contraria}
              scoringConfianca={resultado.scoring_confianca}
              risco={resultado.risco_adocao}
              mostrarDisclaimer={false}
            />
          </Card>

          {resultado.saidas_stakeholders && resultado.saidas_stakeholders.length > 0 && (
            <Card titulo="🎯 O que isso significa para cada área">
              <div className="space-y-4">
                {resultado.saidas_stakeholders.map((s) => (
                  <div key={s.stakeholder_id}>
                    <p className="text-xs font-semibold text-muted-foreground mb-1">
                      {s.emoji} {s.label}
                    </p>
                    <p className="text-sm leading-relaxed whitespace-pre-wrap text-foreground">
                      {s.resumo}
                    </p>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {/* CTA de documentação — sempre ao final */}
          <CTADocumentar query={query} resultado={resultado} />
        </div>
      )}
    </div>
  );
}
