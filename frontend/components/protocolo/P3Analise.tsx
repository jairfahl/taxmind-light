"use client";
import { useState } from "react";
import { useProtocoloStore } from "@/store/protocolo";
import { Card } from "@/components/shared/Card";
import { Button } from "@/components/ui/button";
import { BadgeCriticidade } from "@/components/shared/BadgeCriticidade";
import { PainelGovernanca } from "@/components/shared/PainelGovernanca";
import { AnalysisLoading } from "@/components/shared/AnalysisLoading";
import api from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import type { ResultadoAnalise, Criticidade } from "@/types";

export function P3Analise() {
  const { caseId, query, premissas, riscos, topK, resultadoIA, set, setStep } = useProtocoloStore();
  const { user } = useAuthStore();
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState("");

  const executarAnalise = async () => {
    if (!caseId) { setErro("Caso não encontrado. Volte ao P1."); return; }
    setLoading(true);
    setErro("");
    try {
      const res = await api.post<ResultadoAnalise>("/v1/analyze", {
        query,
        top_k: topK,
        premissas,
        riscos_fiscais: riscos,
        user_id: user?.id ?? null,
        case_id: caseId,
      });
      const resultado = res.data;

      // Salvar no store
      set({
        resultadoIA: resultado,
        grauConsolidacao: resultado.grau_consolidacao ?? "",
        contraTese: resultado.forca_corrente_contraria ?? "",
        criticidade: resultado.criticidade ?? "",
      });

      // Submeter passo 3 à API
      await api.post(`/v1/cases/${caseId}/steps/3`, {
        dados: {
          query_analise: query,
          analise_result: { resposta: resultado.resposta, criticidade: resultado.criticidade },
        },
        acao: "avancar",
      });
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setErro(typeof msg === "string" ? msg : "Erro ao processar análise.");
    } finally {
      setLoading(false);
    }
  };

  const isValidCriticidade = (v: string): v is Criticidade =>
    ["critico", "atencao", "informativo"].includes(v);

  return (
    <div className="space-y-4">
      <Card titulo="P3 — Análise">
        {!resultadoIA ? (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              A IA irá analisar sua consulta com base na LC 214/2025, EC 132/2023 e LC 227/2026,
              utilizando as {premissas.length} premissas e {riscos.length} riscos declarados em P2.
            </p>
            {erro && <p className="text-xs text-red-600">{erro}</p>}
            {loading && <AnalysisLoading />}
            {!loading && (
              <Button onClick={executarAnalise} className="bg-primary text-primary-foreground w-full">
                Executar análise →
              </Button>
            )}
          </div>
        ) : (
          <div className="space-y-4">
            {isValidCriticidade(resultadoIA.criticidade) && (
              <BadgeCriticidade nivel={resultadoIA.criticidade} />
            )}

            {resultadoIA.alertas_vigencia?.filter((a) => a.alerta).map((a, i) => (
              <div key={i} className="p-3 bg-amber-50 border border-amber-200 rounded-md">
                <p className="text-xs text-amber-700">{a.mensagem}</p>
              </div>
            ))}

            <p className="text-sm leading-relaxed whitespace-pre-wrap text-foreground">
              {resultadoIA.resposta}
            </p>

            {resultadoIA.grau_consolidacao && (
              <PainelGovernanca
                grau={resultadoIA.grau_consolidacao}
                forcaContraTese={resultadoIA.forca_corrente_contraria}
                scoringConfianca={resultadoIA.scoring_confianca}
                risco={resultadoIA.risco_adocao}
                mostrarDisclaimer={false}
              />
            )}

            <Button
              variant="outline"
              onClick={() => set({ resultadoIA: null })}
              className="text-xs"
            >
              Refazer análise
            </Button>
          </div>
        )}
      </Card>

      <div className="flex gap-3">
        <Button variant="outline" onClick={() => setStep(2)}>← Anterior</Button>
        <Button
          onClick={() => setStep(4)}
          disabled={!resultadoIA}
          className="flex-1 bg-primary text-primary-foreground disabled:opacity-50"
        >
          Hipotetizar →
        </Button>
      </div>
    </div>
  );
}
