import Link from "next/link";
import { CheckCircle, FileSearch, Layers, BarChart3, ArrowRight } from "lucide-react";

const FEATURES = [
  {
    icon: FileSearch,
    titulo: "Análise RAG em segundos",
    desc: "Fundamentação legal instantânea com base em LC 214/2025, EC 132/2023 e LC 227/2026. Anti-alucinação em 4 camadas.",
  },
  {
    icon: Layers,
    titulo: "Protocolo de Decisão P1→P6",
    desc: "Processo auditável de 6 passos: classifique, estruture, analise, formule hipótese, decida e monitore.",
  },
  {
    icon: BarChart3,
    titulo: "Simuladores Tributários",
    desc: "Calcule o impacto do IBS/CBS, Split Payment, IS Seletivo e reestruturação societária com dados reais.",
  },
];

const BULLETS = [
  "Baseado em LC 214/2025, EC 132/2023 e LC 227/2026",
  "Protocolo de decisão auditável P1→P6",
  "Anti-alucinação em 4 camadas (M1–M4)",
  "Documentos acionáveis com visão por stakeholder",
];

export default function LandingPage() {
  return (
    <div className="min-h-screen flex flex-col bg-background font-sans">

      {/* ── HERO ──────────────────────────────────────────────────────── */}
      <section
        className="flex flex-col items-center justify-center text-center px-6 py-24 md:py-36"
        style={{ background: "var(--gradient-primary)" }}
      >
        {/* Logo */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/logo.png"
          alt="Tribus-AI"
          className="h-20 w-auto mb-8 drop-shadow-lg"
        />

        {/* Headline */}
        <h1 className="text-4xl md:text-5xl font-extrabold text-white leading-tight mb-4 max-w-2xl">
          Inteligência Tributária para a Reforma
        </h1>
        <p className="text-white/70 text-lg md:text-xl mb-10 max-w-xl">
          Análise, protocolo de decisão e simuladores para navegar a
          Reforma Tributária brasileira com segurança e fundamentação legal.
        </p>

        {/* CTAs */}
        <div className="flex flex-col sm:flex-row gap-3 items-center">
          <Link
            href="/login"
            className="inline-flex items-center gap-2 px-8 py-3 rounded-lg font-semibold text-white bg-primary hover:bg-primary/90 transition-all shadow-lg"
          >
            Entrar na plataforma
            <ArrowRight size={16} />
          </Link>
          <a
            href="https://wa.me/5511999999999?text=Quero+saber+mais+sobre+o+Tribus-AI"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 px-6 py-3 rounded-lg font-medium text-white/85 border border-white/30 hover:border-white/60 hover:text-white transition-all"
          >
            Falar com especialista
          </a>
        </div>
      </section>

      {/* ── BULLETS ───────────────────────────────────────────────────── */}
      <section className="bg-muted border-y border-border py-6 px-6">
        <ul className="flex flex-wrap justify-center gap-x-8 gap-y-3 max-w-4xl mx-auto">
          {BULLETS.map((item) => (
            <li key={item} className="flex items-center gap-2 text-sm text-muted-foreground">
              <CheckCircle size={14} className="text-primary shrink-0" />
              {item}
            </li>
          ))}
        </ul>
      </section>

      {/* ── FEATURES ──────────────────────────────────────────────────── */}
      <section className="py-20 px-6">
        <div className="max-w-5xl mx-auto">
          <p className="tm-label text-center mx-auto block w-fit mb-4">Funcionalidades</p>
          <h2 className="text-2xl md:text-3xl font-bold text-center mb-12">
            Tudo que você precisa para a Reforma Tributária
          </h2>

          <div className="grid md:grid-cols-3 gap-6">
            {FEATURES.map(({ icon: Icon, titulo, desc }) => (
              <div key={titulo} className="tm-card flex flex-col gap-4">
                <div
                  className="w-10 h-10 rounded-lg flex items-center justify-center"
                  style={{ background: "var(--color-primary-light)" }}
                >
                  <Icon size={20} style={{ color: "var(--color-primary)" }} />
                </div>
                <div>
                  <h3 className="text-base font-semibold mb-1">{titulo}</h3>
                  <p className="text-sm text-muted-foreground leading-relaxed">{desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA FINAL ─────────────────────────────────────────────────── */}
      <section className="py-16 px-6 text-center border-t border-border">
        <h2 className="text-2xl font-bold mb-3">Pronto para começar?</h2>
        <p className="text-muted-foreground mb-8 max-w-md mx-auto">
          Acesse a plataforma e analise cenários tributários complexos em segundos.
        </p>
        <Link
          href="/login"
          className="inline-flex items-center gap-2 px-8 py-3 rounded-lg font-semibold text-white bg-primary hover:bg-primary/90 transition-all shadow-lg"
        >
          Entrar na plataforma
          <ArrowRight size={16} />
        </Link>
      </section>

      {/* ── FOOTER ────────────────────────────────────────────────────── */}
      <footer className="mt-auto border-t border-border py-6 px-6 text-center">
        <p className="text-xs text-muted-foreground">
          Tribus-AI © 2026 · Não constitui parecer jurídico ·{" "}
          <a href="/login" className="hover:underline">
            Acessar plataforma
          </a>
        </p>
      </footer>

    </div>
  );
}
