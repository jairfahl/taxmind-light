"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { X, AlertCircle } from "lucide-react";
import api from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import type { ResultadoAnalise } from "@/types";

interface Props {
  query: string;
  resultado: ResultadoAnalise;
  onConcluido: () => void;
  onCancelar: () => void;
}

function StepDot({ num, ativo, concluido }: { num: number; ativo: boolean; concluido: boolean }) {
  return (
    <div
      className={[
        "flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold shrink-0",
        concluido
          ? "bg-primary text-primary-foreground"
          : ativo
          ? "bg-primary/10 text-primary border border-primary"
          : "border border-border text-muted-foreground",
      ].join(" ")}
    >
      {concluido ? "✓" : num}
    </div>
  );
}

const STEPS = [
  { num: 1, label: "Contexto" },
  { num: 2, label: "Seu palpite" },
  { num: 3, label: "Decisão" },
];

export function FluxoDocumentacao({ query, resultado, onConcluido, onCancelar }: Props) {
  const { user } = useAuthStore();
  const [step, setStep] = useState(1);
  const [salvando, setSalvando] = useState(false);
  const [erroApi, setErroApi] = useState("");

  const [premissa, setPremissa] = useState("");
  const [risco, setRisco] = useState("");
  const [hipotese, setHipotese] = useState("");
  const [decisao, setDecisao] = useState("");

  const salvar = async () => {
    setSalvando(true);
    setErroApi("");
    try {
      await api.post("/v1/registrar_decisao", {
        query,
        premissas: premissa.trim() ? [premissa.trim()] : [],
        riscos: risco.trim() ? [risco.trim()] : [],
        resultado_ia: resultado.resposta,
        grau_consolidacao: resultado.grau_consolidacao ?? "",
        contra_tese: resultado.forca_corrente_contraria ?? "",
        criticidade: resultado.criticidade ?? "informativo",
        hipotese_gestor: hipotese.trim(),
        decisao_final: decisao.trim(),
        user_id: user?.id ?? null,
      });
      onConcluido();
    } catch (e: unknown) {
      const detail =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setErroApi(
        typeof detail === "string"
          ? detail
          : "Erro ao registrar a análise. Verifique os campos e tente novamente."
      );
    } finally {
      setSalvando(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Cabeçalho */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium">Registrando sua análise</p>
          <p className="text-xs text-muted-foreground">3 passos rápidos — sua decisão ficará protegida.</p>
        </div>
        <button onClick={onCancelar} className="text-muted-foreground hover:text-foreground cursor-pointer">
          <X size={16} />
        </button>
      </div>

      {/* Indicador de steps */}
      <div className="flex items-center gap-2 flex-wrap">
        {STEPS.map((s, i) => (
          <div key={s.num} className="flex items-center gap-2">
            <StepDot num={s.num} ativo={step === s.num} concluido={step > s.num} />
            <span className={`text-xs ${step === s.num ? "text-foreground font-medium" : "text-muted-foreground"}`}>
              {s.label}
            </span>
            {i < STEPS.length - 1 && (
              <div className={`h-px w-5 ${step > s.num ? "bg-primary" : "bg-border"}`} />
            )}
          </div>
        ))}
      </div>

      {/* ── STEP 1: Contexto ── */}
      {step === 1 && (
        <div className="space-y-3">
          <div>
            <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              O que é verdade na sua situação?
            </label>
            <Textarea
              value={premissa}
              onChange={(e) => setPremissa(e.target.value)}
              placeholder="Ex: Somos do Lucro Real, operamos em SP e RJ, operação predominantemente B2B..."
              className="mt-1 min-h-20 bg-input border-border text-sm resize-none"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              O que você teme que aconteça?
            </label>
            <Textarea
              value={risco}
              onChange={(e) => setRisco(e.target.value)}
              placeholder="Ex: Perder créditos de IBS se não adequarmos o processo de compras a tempo..."
              className="mt-1 min-h-20 bg-input border-border text-sm resize-none"
            />
          </div>
          <div className="flex justify-end">
            <Button
              onClick={() => setStep(2)}
              disabled={!premissa.trim() && !risco.trim()}
              className="bg-primary hover:bg-primary/90"
            >
              Próximo →
            </Button>
          </div>
        </div>
      )}

      {/* ── STEP 2: Hipótese ── */}
      {step === 2 && (
        <div className="space-y-3">
          <div>
            <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Antes da IA: qual era seu palpite?
            </label>
            <p className="text-xs text-muted-foreground mt-0.5">
              Registre o que você achava antes de ver a análise. Isso protege seu raciocínio independente.
            </p>
            <Textarea
              value={hipotese}
              onChange={(e) => setHipotese(e.target.value)}
              placeholder="Ex: Achei que o impacto seria neutro porque somos atacadistas, mas não tinha certeza sobre o split payment..."
              className="mt-2 min-h-24 bg-input border-border text-sm resize-none"
            />
          </div>
          <div className="flex justify-between">
            <Button variant="ghost" onClick={() => setStep(1)} className="text-muted-foreground">← Voltar</Button>
            <Button
              onClick={() => setStep(3)}
              disabled={!hipotese.trim()}
              className="bg-primary hover:bg-primary/90"
            >
              Próximo →
            </Button>
          </div>
        </div>
      )}

      {/* ── STEP 3: Decisão ── */}
      {step === 3 && (
        <div className="space-y-3">
          <div>
            <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              O que você vai fazer com isso?
            </label>
            <Textarea
              value={decisao}
              onChange={(e) => setDecisao(e.target.value)}
              placeholder="Ex: Vou revisar os contratos com fornecedores para incluir cláusula de repasse de IBS/CBS. Prazo: antes de julho/2026..."
              className="mt-1 min-h-24 bg-input border-border text-sm resize-none"
            />
          </div>

          <div className="p-3 bg-muted/40 rounded-md text-xs text-muted-foreground space-y-0.5">
            <p className="font-medium text-foreground mb-1">O que será registrado:</p>
            <p>📋 Sua pergunta + análise da IA</p>
            <p>📝 Contexto e preocupações declarados</p>
            <p>💡 Seu palpite antes da IA</p>
            <p>✅ Sua decisão</p>
            <p>🔒 Legal Hold ativo — imutável e defensável perante o Fisco</p>
          </div>

          {erroApi && (
            <div className="flex gap-2 items-start p-3 bg-red-50 border border-red-200 rounded-md">
              <AlertCircle size={14} className="text-red-500 mt-0.5 shrink-0" />
              <p className="text-xs text-red-600">{erroApi}</p>
            </div>
          )}

          <div className="flex justify-between">
            <Button variant="ghost" onClick={() => setStep(2)} className="text-muted-foreground">← Voltar</Button>
            <Button
              onClick={salvar}
              disabled={!decisao.trim() || salvando}
              className="bg-primary hover:bg-primary/90"
            >
              {salvando ? "Registrando…" : "Registrar análise"}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
