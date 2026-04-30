"use client";
import { AlertTriangle, Sparkles, CheckCircle } from "lucide-react";
import { useAuthStore } from "@/store/auth";

const BLOCKED_STATUSES = ["past_due", "canceled", "inactive"];

const MESSAGES: Record<string, { titulo: string; corpo: string }> = {
  past_due: {
    titulo: "Pagamento não identificado",
    corpo:
      "Não identificamos o pagamento de sua assinatura. Regularize para continuar consultando o Orbis.tax.",
  },
  canceled: {
    titulo: "Assinatura encerrada",
    corpo:
      "Sua assinatura foi cancelada. Para reativar o acesso, assine novamente.",
  },
  inactive: {
    titulo: "Acesso inativo",
    corpo:
      "Seu acesso está inativo. Assine um plano para continuar utilizando o Orbis.tax.",
  },
};

const BENEFICIOS = [
  "Respostas jurídicas precisas com indicação da lei consultada",
  "Mapa de decisão com 6 passos auditáveis",
  "Simuladores IBS, CBS e Split Payment",
  "Outputs acionáveis em 5 formatos",
  "Histórico completo de consultas e decisões",
];

function TrialExpiradoScreen() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[80vh] px-4">
      <div
        className="w-full max-w-lg rounded-2xl p-8 text-center"
        style={{
          background: "var(--card)",
          border: "1px solid var(--border)",
          boxShadow: "var(--shadow-card)",
        }}
      >
        {/* Ícone */}
        <div className="flex justify-center mb-5">
          <span
            className="inline-flex items-center justify-center w-16 h-16 rounded-full"
            style={{ background: "rgba(46,117,182,.12)" }}
          >
            <Sparkles size={28} style={{ color: "#2E75B6" }} />
          </span>
        </div>

        {/* Título */}
        <h2 className="text-xl font-bold text-foreground mb-2">
          Seu período gratuito encerrou
        </h2>
        <p className="text-muted-foreground text-sm mb-6 leading-relaxed">
          Você experimentou o poder da inteligência tributária do Orbis.tax.
          Agora é hora de continuar — sem interrupções, com análises ilimitadas
          e segurança jurídica na palma da mão.
        </p>

        {/* Benefícios */}
        <ul className="text-left space-y-2 mb-7">
          {BENEFICIOS.map((b) => (
            <li key={b} className="flex items-center gap-2 text-sm text-foreground">
              <CheckCircle size={16} style={{ color: "#2E75B6", flexShrink: 0 }} />
              {b}
            </li>
          ))}
        </ul>

        {/* Preço */}
        <div className="mb-6">
          <span className="text-3xl font-extrabold text-foreground">R$ 297</span>
          <span className="text-muted-foreground text-sm ml-1">/ 2 meses</span>
          <p className="text-xs text-muted-foreground mt-1">
            Depois R$ 497/mês — cancele quando quiser
          </p>
        </div>

        {/* CTA */}
        <a
          href="/assinar"
          className="inline-flex items-center justify-center w-full h-12 rounded-xl font-semibold text-sm text-white cursor-pointer"
          style={{
            background: "linear-gradient(135deg, #2E75B6 0%, #1F3864 100%)",
            boxShadow: "0 4px 14px rgba(30,77,150,.30)",
          }}
        >
          Assinar agora e continuar
        </a>

        {/* WhatsApp */}
        <p className="text-xs text-muted-foreground mt-4">
          Tem dúvidas?{" "}
          <a
            href="https://wa.me/5511972521970?text=Ol%C3%A1%2C+meu+trial+encerrou+e+quero+saber+mais+sobre+a+assinatura+do+Orbis.tax."
            target="_blank"
            rel="noopener noreferrer"
            className="underline"
          >
            Fale com a gente no WhatsApp
          </a>
        </p>
      </div>
    </div>
  );
}

export function SubscriptionBlocker({ children }: { children: React.ReactNode }) {
  const { user } = useAuthStore();
  const status = user?.subscription_status ?? null;

  // Trial expirado: status ainda é "trial" mas trial_ends_at já passou
  if (status === "trial" && user?.trial_ends_at) {
    const expirou = new Date(user.trial_ends_at) < new Date();
    if (expirou) return <TrialExpiradoScreen />;
  }

  if (!status || !BLOCKED_STATUSES.includes(status)) {
    return <>{children}</>;
  }

  const msg = MESSAGES[status] ?? MESSAGES.inactive;

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] px-4">
      <div
        className="w-full max-w-md rounded-xl p-6 text-center"
        style={{
          background: "var(--card)",
          border: "1px solid var(--border)",
          boxShadow: "var(--shadow-card)",
        }}
      >
        <div className="flex justify-center mb-4">
          <span
            className="inline-flex items-center justify-center w-12 h-12 rounded-full"
            style={{ background: "rgba(239,68,68,.10)" }}
          >
            <AlertTriangle size={24} style={{ color: "#ef4444" }} />
          </span>
        </div>

        <h2 className="text-lg font-bold text-foreground mb-2">{msg.titulo}</h2>
        <p className="text-sm text-muted-foreground mb-6">{msg.corpo}</p>

        <a
          href="/assinar"
          className="inline-flex items-center justify-center w-full h-11 rounded-lg font-semibold text-sm text-white cursor-pointer"
          style={{
            background: "linear-gradient(135deg, #2E75B6 0%, #1F3864 100%)",
            boxShadow: "0 4px 14px rgba(30,77,150,.30)",
          }}
        >
          Regularizar assinatura
        </a>

        <p className="text-xs text-muted-foreground mt-4">
          Dúvidas?{" "}
          <a
            href="https://wa.me/5511972521970?text=Ol%C3%A1%2C+preciso+de+ajuda+com+minha+assinatura+Orbis.tax."
            target="_blank"
            rel="noopener noreferrer"
            className="underline"
          >
            Fale conosco no WhatsApp
          </a>
        </p>
      </div>
    </div>
  );
}
