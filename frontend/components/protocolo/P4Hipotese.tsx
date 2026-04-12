"use client";
import { useState } from "react";
import { useProtocoloStore } from "@/store/protocolo";
import { Card } from "@/components/shared/Card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import api from "@/lib/api";

export function P4Hipotese() {
  const { caseId, hipoteseGestor, resultadoIA, set, setStep } = useProtocoloStore();
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState("");
  const [salvo, setSalvo] = useState(false);

  const salvar = async () => {
    if (!hipoteseGestor.trim()) return;
    if (!caseId) { setErro("Caso não encontrado. Volte ao P1."); return; }
    setLoading(true);
    setErro("");
    try {
      await api.post(`/v1/cases/${caseId}/steps/4`, {
        dados: { hipotese_gestor: hipoteseGestor },
        acao: "avancar",
      });
      setSalvo(true);
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setErro(typeof msg === "string" ? msg : "Erro ao salvar hipótese.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Campo de hipótese */}
      <Card titulo="P4 — Qual era seu palpite?">
        <p className="text-sm text-muted-foreground mb-3">
          Registre sua leitura da situação <strong>antes</strong> de comparar com a análise da IA.
          Este campo é obrigatório e compõe o registro auditável da decisão.
        </p>
        <Textarea
          value={hipoteseGestor}
          onChange={(e) => { set({ hipoteseGestor: e.target.value }); setSalvo(false); }}
          placeholder="Registre aqui sua leitura inicial. Isso preserva seu raciocínio independente."
          className="min-h-28 resize-none text-sm bg-input border-border"
          disabled={salvo}
        />
        <p className="text-xs text-muted-foreground mt-1">{hipoteseGestor.length} caracteres</p>
        {erro && <p className="text-xs text-red-600 mt-1">{erro}</p>}

        {!salvo && (
          <Button
            onClick={salvar}
            disabled={loading || !hipoteseGestor.trim()}
            className="mt-3 bg-primary text-primary-foreground w-full"
          >
            {loading ? "Salvando…" : "Registrar hipótese"}
          </Button>
        )}

        {salvo && (
          <p className="text-xs text-emerald-600 mt-2 font-medium">
            ✓ Hipótese registrada. Agora compare com a análise da IA abaixo.
          </p>
        )}
      </Card>

      {/* Lado a lado: hipótese vs IA */}
      {salvo && resultadoIA && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Card titulo="Sua hipótese (P4)" acento="muted">
            <p className="text-sm leading-relaxed whitespace-pre-wrap text-foreground">
              {hipoteseGestor}
            </p>
          </Card>
          <Card titulo="Recomendação da IA (P3)" acento="primary">
            <p className="text-sm leading-relaxed whitespace-pre-wrap text-foreground line-clamp-10">
              {resultadoIA.resposta}
            </p>
          </Card>
        </div>
      )}

      <div className="flex gap-3">
        <Button variant="outline" onClick={() => setStep(3)}>← Anterior</Button>
        <Button
          onClick={() => setStep(5)}
          disabled={!salvo}
          className="flex-1 bg-primary text-primary-foreground disabled:opacity-50"
        >
          Decidir →
        </Button>
      </div>
    </div>
  );
}
