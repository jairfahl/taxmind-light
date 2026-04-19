"use client";
import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { useAuthStore } from "@/store/auth";
import api from "@/lib/api";

export function OnboardingModal() {
  const { user, setAuth } = useAuthStore();
  const token = useAuthStore((s) => s.token);
  const [step, setStep] = useState<number | null>(null);

  useEffect(() => {
    if (!user?.id) return;
    api
      .get<{
        onboarding_step: number;
        subscription_status?: string | null;
        trial_ends_at?: string | null;
      }>("/v1/auth/me", { params: { user_id: user.id } })
      .then((r) => {
        setStep(r.data.onboarding_step ?? 0);
        // Atualiza store com dados de trial vindos do backend
        if (r.data.trial_ends_at !== undefined || r.data.subscription_status !== undefined) {
          setAuth(
            {
              ...user,
              subscription_status: r.data.subscription_status ?? null,
              trial_ends_at: r.data.trial_ends_at ?? null,
            },
            token ?? ""
          );
        }
      })
      .catch(() => setStep(99)); // on error, skip modal
  }, [user?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // null = loading, 0 = show modal, anything else = done
  if (step === null || step !== 0) return null;

  return (
    <div className="fixed inset-0 bg-background/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-card border border-border rounded-xl p-8 w-full max-w-md shadow-lg">
        <h2 className="text-lg font-semibold mb-1">Antes de começar</h2>
        <p className="text-sm text-muted-foreground mb-6">
          Dois campos rápidos para personalizar sua experiência.
        </p>
        <OnboardingStep0 userId={user!.id} onComplete={() => setStep(1)} />
      </div>
    </div>
  );
}

function OnboardingStep0({
  userId,
  onComplete,
}: {
  userId: string;
  onComplete: () => void;
}) {
  const [tipo, setTipo] = useState("");
  const [cargo, setCargo] = useState("");
  const [loading, setLoading] = useState(false);

  const salvar = async () => {
    if (!tipo || !cargo) return;
    setLoading(true);
    try {
      await api.patch("/v1/auth/onboarding", {
        user_id: userId,
        tipo_atuacao: tipo,
        cargo_responsavel: cargo,
        onboarding_step: 1,
      });
      onComplete();
    } finally {
      setLoading(false);
    }
  };

  const SELECT_CLS =
    "w-full bg-input border border-border rounded-md px-3 py-2 text-sm mt-1 text-foreground";
  const LABEL_CLS = "text-xs font-medium text-muted-foreground uppercase tracking-wider";

  return (
    <div className="space-y-4">
      <div>
        <label className={LABEL_CLS}>Como você usa o Orbis.tax? ✱</label>
        <select value={tipo} onChange={(e) => setTipo(e.target.value)} className={SELECT_CLS}>
          <option value="">Selecionar…</option>
          <option>Empresa (uso interno)</option>
          <option>Consultoria</option>
          <option>Escritório (contabilidade/advocacia)</option>
          <option>BPO Tributário</option>
        </select>
      </div>

      <div>
        <label className={LABEL_CLS}>Qual é o seu cargo? ✱</label>
        <select value={cargo} onChange={(e) => setCargo(e.target.value)} className={SELECT_CLS}>
          <option value="">Selecionar…</option>
          <option>Gestor / Gerente Tributário</option>
          <option>Analista Tributário</option>
          <option>Consultor</option>
          <option>Sócio / Diretor</option>
          <option>CFO / Controller</option>
          <option>Outro</option>
        </select>
      </div>

      <Button
        onClick={salvar}
        className="w-full bg-primary text-primary-foreground"
        disabled={!tipo || !cargo || loading}
      >
        {loading ? "Salvando…" : "Confirmar e entrar"}
      </Button>
    </div>
  );
}
