"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { CheckCircle, CreditCard, Smartphone } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/shared/Card";
import { useAuthStore } from "@/store/auth";
import api from "@/lib/api";

const BENEFICIOS = [
  "1 usuário ativo (acesso exclusivo por dispositivo)",
  "Protocolo auditável P1→P6 completo",
  "Análise RAG ilimitada com citação de fonte",
  "Simuladores tributários (IBS, CBS, Split Payment)",
  "Outputs acionáveis em 5 formatos",
  "Suporte via WhatsApp",
];

export default function AssinarPage() {
  const router = useRouter();
  const { user } = useAuthStore();
  const [billingType, setBillingType] = useState<"CREDIT_CARD" | "PIX">("PIX");
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState("");

  const onAssinar = async () => {
    if (!user?.tenant_id) {
      setErro("Tenant não identificado. Entre em contato com o suporte.");
      return;
    }
    setLoading(true);
    setErro("");
    try {
      const res = await api.post<{ invoice_url: string; valor: number; desconto_percentual: number }>(
        "/v1/billing/subscribe",
        { tenant_id: user.tenant_id, billing_type: billingType }
      );
      if (res.data.invoice_url) {
        window.location.href = res.data.invoice_url;
      } else {
        setErro("Não foi possível gerar o link de pagamento. Tente novamente.");
      }
    } catch (err: unknown) {
      const axiosErr = err as { response?: { status?: number; data?: { detail?: string } } };
      if (axiosErr.response?.status === 409) {
        setErro("Você já possui uma assinatura ativa. Entre em contato com o suporte.");
      } else {
        setErro("Erro ao processar assinatura. Tente novamente em instantes.");
      }
    } finally {
      setLoading(false);
    }
  };

  const isTrial = !user?.subscription_status || user.subscription_status === "trial";

  return (
    <div className="max-w-md mx-auto px-4 py-10">
      {/* Badge trial */}
      {isTrial && user?.trial_ends_at && (
        <div
          className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-semibold mb-6"
          style={{ background: "rgba(59,130,246,.10)", border: "1px solid rgba(59,130,246,.25)", color: "#2563eb" }}
        >
          <span className="w-1.5 h-1.5 rounded-full bg-blue-400 shrink-0" />
          Trial ativo
        </div>
      )}

      <h1 className="text-2xl font-bold mb-1" style={{ color: "#0f2040" }}>
        Plano Starter
      </h1>
      <p className="text-sm mb-6" style={{ color: "#64748b" }}>
        Tudo que você precisa para decisões tributárias fundamentadas.
      </p>

      <Card>
        <div className="p-6">
          {/* Preço */}
          <div className="flex items-baseline gap-1 mb-6">
            <span className="text-3xl font-extrabold" style={{ color: "#0f2040" }}>R$ 497</span>
            <span className="text-sm" style={{ color: "#64748b" }}>/mês</span>
          </div>

          {/* Benefícios */}
          <ul className="space-y-3 mb-8">
            {BENEFICIOS.map((b) => (
              <li key={b} className="flex items-center gap-2.5 text-sm" style={{ color: "#334155" }}>
                <CheckCircle size={14} className="text-emerald-500 shrink-0" />
                {b}
              </li>
            ))}
          </ul>

          {/* Seletor de pagamento */}
          <p className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: "#475569" }}>
            Forma de pagamento
          </p>
          <div className="flex gap-3 mb-6">
            {(["PIX", "CREDIT_CARD"] as const).map((tipo) => (
              <button
                key={tipo}
                type="button"
                onClick={() => setBillingType(tipo)}
                className="flex-1 flex items-center justify-center gap-2 py-2.5 px-3 rounded-lg border text-sm font-medium transition-all cursor-pointer"
                style={
                  billingType === tipo
                    ? { background: "#eff6ff", border: "1.5px solid #3b82f6", color: "#1d4ed8" }
                    : { background: "#f8fafc", border: "1px solid #e2e8f0", color: "#64748b" }
                }
              >
                {tipo === "PIX" ? <Smartphone size={14} /> : <CreditCard size={14} />}
                {tipo === "PIX" ? "PIX" : "Cartão"}
              </button>
            ))}
          </div>

          {/* Erro */}
          {erro && (
            <div className="mb-4 p-3 rounded-lg" style={{ background: "#fef2f2", border: "1px solid #fecaca" }}>
              <p className="text-xs font-medium" style={{ color: "#dc2626" }}>{erro}</p>
            </div>
          )}

          <Button
            onClick={onAssinar}
            disabled={loading}
            className="w-full h-11 font-semibold text-white text-sm cursor-pointer"
            style={{
              background: "linear-gradient(135deg, #2E75B6 0%, #1F3864 100%)",
              boxShadow: "0 4px 14px rgba(30,77,150,.30)",
            }}
          >
            {loading ? "Processando…" : "Assinar agora"}
          </Button>

          <p className="text-center text-xs mt-4" style={{ color: "#94a3b8" }}>
            Você será redirecionado para a página de pagamento segura.
          </p>
        </div>
      </Card>

      <p className="text-center text-xs mt-6" style={{ color: "#94a3b8" }}>
        Dúvidas?{" "}
        <a
          href="https://wa.me/5511999999999?text=Quero+assinar+o+Orbis.tax"
          target="_blank"
          rel="noopener noreferrer"
          className="underline"
        >
          Fale conosco no WhatsApp
        </a>
      </p>
    </div>
  );
}
