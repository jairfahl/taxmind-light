"use client";
import { useState, useEffect } from "react";
import { useProtocoloStore } from "@/store/protocolo";
import { Card } from "@/components/shared/Card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { CheckCircle, Clock, AlertTriangle } from "lucide-react";
import api from "@/lib/api";

interface CasoListado {
  case_id: string;
  titulo: string;
  status: string;
  passo_atual: number;
  created_at: string;
}

interface DriftAlert {
  id: number;
  query_original: string;
  alerta_tipo: string;
  criado_em: string;
}

export function P6Monitoramento() {
  const { caseId, query, set, setStep, reset } = useProtocoloStore();
  const [resultadoReal, setResultadoReal] = useState("");
  const [aprendizado, setAprendizado] = useState("");
  const [loading, setLoading] = useState(false);
  const [encerrado, setEncerrado] = useState(false);
  const [erro, setErro] = useState("");
  const [casos, setCasos] = useState<CasoListado[]>([]);
  const [loadingCasos, setLoadingCasos] = useState(true);
  const [alertas, setAlertas] = useState<DriftAlert[]>([]);

  // Carregar lista de casos ativos
  useEffect(() => {
    api.get<CasoListado[]>("/v1/cases")
      .then((r) => setCasos(r.data.filter((c) => c.status !== "encerrado").slice(0, 5)))
      .catch(() => setCasos([]))
      .finally(() => setLoadingCasos(false));
  }, []);

  // Carregar alertas de monitoramento ativos
  useEffect(() => {
    api.get<DriftAlert[]>("/v1/observability/drift")
      .then((r) => setAlertas(r.data.slice(0, 3)))
      .catch(() => setAlertas([]));
  }, []);

  const encerrar = async () => {
    if (!resultadoReal.trim() || !aprendizado.trim()) return;
    if (!caseId) { setErro("Caso não encontrado."); return; }
    setLoading(true);
    setErro("");
    try {
      await api.post(`/v1/cases/${caseId}/steps/6`, {
        dados: {
          resultado_real: resultadoReal,
          data_revisao: new Date().toISOString().split("T")[0],
          aprendizado_extraido: aprendizado,
        },
        acao: "avancar",
      });
      setEncerrado(true);
      set({ interactionId: String(caseId) });
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setErro(typeof msg === "string" ? msg : "Erro ao encerrar caso.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card titulo="P6 — Monitoramento" acento="success">
        {!encerrado ? (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Registre o resultado real observado após a implementação da decisão
              e o aprendizado institucional extraído.
            </p>

            <div>
              <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Resultado real observado
              </label>
              <Textarea
                value={resultadoReal}
                onChange={(e) => setResultadoReal(e.target.value)}
                placeholder="O resultado efetivo após implementar a decisão foi…"
                className="mt-1 min-h-20 resize-none text-sm bg-input border-border"
              />
            </div>

            <div>
              <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Aprendizado institucional
              </label>
              <Textarea
                value={aprendizado}
                onChange={(e) => setAprendizado(e.target.value)}
                placeholder="O aprendizado extraído para casos futuros é…"
                className="mt-1 min-h-20 resize-none text-sm bg-input border-border"
              />
            </div>

            {erro && <p className="text-xs text-red-600">{erro}</p>}

            <Button
              onClick={encerrar}
              disabled={loading || !resultadoReal.trim() || !aprendizado.trim()}
              className="w-full bg-primary text-primary-foreground"
            >
              {loading ? "Encerrando caso…" : "Encerrar e registrar aprendizado"}
            </Button>
          </div>
        ) : (
          <div className="space-y-3 text-center py-4">
            <CheckCircle size={40} className="text-emerald-500 mx-auto" />
            <p className="font-semibold text-foreground">Caso encerrado com sucesso</p>
            <p className="text-sm text-muted-foreground">
              O aprendizado institucional foi registrado e ficará disponível para análises futuras
              (válido por 6 meses).
            </p>
            <Button onClick={reset} className="bg-primary text-primary-foreground">
              Iniciar novo protocolo
            </Button>
          </div>
        )}
      </Card>

      {/* Casos ativos do tenant */}
      <Card titulo="Decisões em monitoramento">
        {loadingCasos ? (
          <p className="text-xs text-muted-foreground animate-pulse">Carregando…</p>
        ) : casos.length === 0 ? (
          <p className="text-xs text-muted-foreground">Nenhuma decisão ativa no momento.</p>
        ) : (
          <div className="space-y-2">
            {casos.map((c) => (
              <div
                key={c.case_id}
                className={`flex items-start gap-3 p-2.5 rounded border ${
                  c.case_id === caseId ? "border-primary bg-primary/5" : "border-border"
                }`}
              >
                <Clock size={14} className="text-muted-foreground shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium truncate">{c.titulo}</p>
                  <p className="text-xs text-muted-foreground">
                    Passo {c.passo_atual}/6 · {c.status}
                  </p>
                </div>
                {c.case_id === caseId && (
                  <span className="text-xs text-primary font-semibold shrink-0">atual</span>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Alertas de monitoramento ativos */}
      {alertas.length > 0 && (
        <Card titulo="Alertas de monitoramento ativos">
          <div className="space-y-2">
            {alertas.map((a) => (
              <div key={a.id} className="flex items-start gap-2 p-2.5 rounded border border-amber-200 bg-amber-50">
                <AlertTriangle size={14} className="text-amber-600 shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium text-amber-800 truncate">{a.alerta_tipo}</p>
                  {a.query_original && (
                    <p className="text-xs text-amber-700/80 mt-0.5 truncate">{a.query_original}</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {!encerrado && (
        <div className="flex gap-3">
          <Button variant="outline" onClick={() => setStep(5)}>← Anterior</Button>
        </div>
      )}
    </div>
  );
}
