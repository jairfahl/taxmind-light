"use client";
import { useEffect, useState } from "react";
import { useProtocoloStore } from "@/store/protocolo";
import { useAuthStore } from "@/store/auth";
import { StepIndicator } from "@/components/protocolo/StepIndicator";
import { P1Classificacao } from "@/components/protocolo/P1Classificacao";
import { P2Estruturacao } from "@/components/protocolo/P2Estruturacao";
import { P3Analise } from "@/components/protocolo/P3Analise";
import { P4Hipotese } from "@/components/protocolo/P4Hipotese";
import { P5Decisao } from "@/components/protocolo/P5Decisao";
import { P6Monitoramento } from "@/components/protocolo/P6Monitoramento";
import api from "@/lib/api";

const STEPS = [
  P1Classificacao,
  P2Estruturacao,
  P3Analise,
  P4Hipotese,
  P5Decisao,
  P6Monitoramento,
];

interface LimiteInfo {
  usado: number;
  limite: number;
  subscription_status: string;
}

export default function ProtocoloPage() {
  const { stepAtual, reset } = useProtocoloStore();
  const { user } = useAuthStore();
  const StepComponent = STEPS[stepAtual - 1];
  const [limite, setLimite] = useState<LimiteInfo | null>(null);

  useEffect(() => {
    if (!user?.id) return;
    api.get<LimiteInfo>(`/v1/cases/limite?user_id=${user.id}`)
      .then((r) => setLimite(r.data))
      .catch(() => {/* silencioso — badge é informativo */});
  }, [user?.id]);

  const limiteBadge = () => {
    if (!limite) return null;
    const { usado, limite: lim, subscription_status } = limite;
    if (lim === -1) return null; // ilimitado — não exibir
    const restantes = lim - usado;
    const esgotado = restantes <= 0;
    const alerta = restantes === 1;
    const labelPeriodo = subscription_status === "trial" ? "no trial" : "este mês";
    return (
      <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${
        esgotado
          ? "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400"
          : alerta
          ? "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400"
          : "bg-muted text-muted-foreground"
      }`}>
        {esgotado
          ? `Limite atingido (${usado}/${lim} casos ${labelPeriodo})`
          : `${restantes} caso${restantes !== 1 ? "s" : ""} restante${restantes !== 1 ? "s" : ""} ${labelPeriodo}`}
      </span>
    );
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Protocolo de Decisão</h1>
          <p className="text-sm text-muted-foreground mt-1">
            6 passos — auditável e rastreável.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {limiteBadge()}
          <button
            onClick={reset}
            className="text-xs text-muted-foreground hover:text-foreground cursor-pointer"
          >
            Nova consulta
          </button>
        </div>
      </div>

      <StepIndicator atual={stepAtual} />

      <StepComponent />
    </div>
  );
}
