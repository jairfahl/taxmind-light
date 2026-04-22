"use client";
import { useState } from "react";
import { useProtocoloStore } from "@/store/protocolo";
import { Card } from "@/components/shared/Card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { AlertTriangle } from "lucide-react";
import api from "@/lib/api";
import { useAuthStore } from "@/store/auth";

interface CarimboResponse {
  score_similaridade: number;
  alerta: boolean;
  mensagem: string | null;
  alert_id: number;
}

interface StepResponse {
  case_id: string;
  passo: number;
  concluido: boolean;
  proximo_passo: number | null;
  carimbo: CarimboResponse | null;
}

export function P5Decisao() {
  const { caseId, resultadoIA, decisaoFinal, set, setStep } = useProtocoloStore();
  const { user } = useAuthStore();
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState("");
  const [carimbo, setCarimbo] = useState<CarimboResponse | null>(null);
  const [justificativa, setJustificativa] = useState("");
  const [confirmando, setConfirmando] = useState(false);
  const [confirmado, setConfirmado] = useState(false);
  const [concluido, setConcluido] = useState(false);

  const salvarDecisao = async () => {
    if (!decisaoFinal.trim()) return;
    if (!caseId) { setErro("Caso não encontrado. Volte ao P1."); return; }
    setLoading(true);
    setErro("");
    try {
      const res = await api.post<StepResponse>(`/v1/cases/${caseId}/steps/5`, {
        dados: {
          recomendacao: resultadoIA?.resposta ?? "",
          decisao_final: decisaoFinal,
          decisor: user?.nome ?? "Gestor",
        },
        acao: "avancar",
      });

      if (res.data.carimbo?.alerta) {
        setCarimbo(res.data.carimbo);
        set({ carimboPct: Math.round((res.data.carimbo.score_similaridade ?? 0) * 100), carimboAlertId: res.data.carimbo.alert_id });
      } else {
        setConcluido(true);
      }
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setErro(typeof msg === "string" ? msg : "Erro ao salvar decisão.");
    } finally {
      setLoading(false);
    }
  };

  const confirmarCarimbo = async () => {
    if (!carimbo || !caseId || justificativa.trim().length < 20) return;
    setConfirmando(true);
    try {
      await api.post(`/v1/cases/${caseId}/carimbo/confirmar`, {
        alert_id: carimbo.alert_id,
        justificativa,
      });
      setConfirmado(true);
      setConcluido(true);
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setErro(typeof msg === "string" ? msg : "Erro ao confirmar carimbo.");
    } finally {
      setConfirmando(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card titulo="P5 — O que você vai fazer?">
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">
            Registre a decisão tomada. O sistema calculará a similaridade com a análise da IA
            e ativará o detector de terceirização cognitiva se necessário.
          </p>
          <Textarea
            value={decisaoFinal}
            onChange={(e) => { set({ decisaoFinal: e.target.value }); setCarimbo(null); setConcluido(false); }}
            placeholder="Descreva o que você decidiu fazer com base nesta análise..."
            className="min-h-24 resize-none text-sm bg-input border-border"
            disabled={concluido}
          />
          <p className="text-xs text-muted-foreground">{decisaoFinal.length} caracteres</p>
          {erro && <p className="text-xs text-red-600">{erro}</p>}

          {!concluido && !carimbo && (
            <Button
              onClick={salvarDecisao}
              disabled={loading || !decisaoFinal.trim()}
              className="w-full bg-primary text-primary-foreground"
            >
              {loading ? "Processando…" : "Registrar decisão"}
            </Button>
          )}
        </div>
      </Card>

      {/* Alerta de Carimbo */}
      {carimbo && !confirmado && (
        <Card acento="warning">
          <div className="space-y-3">
            <div className="flex items-start gap-3">
              <AlertTriangle size={18} className="text-amber-600 shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-semibold text-amber-800">
                  Detector de Terceirização Cognitiva ativado
                </p>
                <p className="text-xs text-amber-700 mt-1">
                  Similaridade entre sua decisão e a análise da IA:{" "}
                  <strong>{Math.round((carimbo.score_similaridade ?? 0) * 100)}%</strong>.
                  {carimbo.mensagem && ` ${carimbo.mensagem}`}
                </p>
                <p className="text-xs text-amber-700 mt-1">
                  Para confirmar que a decisão é autônoma, registre uma justificativa própria
                  (mínimo 20 caracteres).
                </p>
              </div>
            </div>
            <div className="space-y-2">
              <Input
                value={justificativa}
                onChange={(e) => setJustificativa(e.target.value)}
                placeholder="Justificativa da decisão autônoma…"
                className="text-sm bg-input border-border"
              />
              <p className="text-xs text-muted-foreground">{justificativa.length}/20 mínimo</p>
              <Button
                onClick={confirmarCarimbo}
                disabled={confirmando || justificativa.trim().length < 20}
                className="w-full bg-amber-600 hover:bg-amber-700 text-white"
              >
                {confirmando ? "Confirmando…" : "Confirmar decisão autônoma"}
              </Button>
            </div>
          </div>
        </Card>
      )}

      {confirmado && (
        <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-md">
          <p className="text-xs text-emerald-700 font-medium">
            ✓ Decisão autônoma confirmada e registrada no audit trail.
          </p>
        </div>
      )}

      <div className="flex gap-3">
        <Button variant="outline" onClick={() => setStep(4)}>← Anterior</Button>
        <Button
          onClick={() => setStep(6)}
          disabled={!concluido}
          className="flex-1 bg-primary text-primary-foreground disabled:opacity-50"
        >
          Monitorar →
        </Button>
      </div>
    </div>
  );
}
