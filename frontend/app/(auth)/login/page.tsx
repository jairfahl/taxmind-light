"use client";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Eye, EyeOff, ShieldCheck, FileSearch, BarChart3 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuthStore } from "@/store/auth";
import api from "@/lib/api";

const schema = z.object({
  email: z.string().email("E-mail inválido"),
  senha: z.string().min(1, "Senha obrigatória"),
});
type Form = z.infer<typeof schema>;

interface LoginResponse {
  access_token: string;
  token_type: string;
  user: {
    id: string;
    email: string;
    nome: string;
    perfil: "ADMIN" | "USER";
    tenant_id: string | null;
    onboarding_step: number;
  };
}

const BULLETS = [
  {
    icon: <ShieldCheck size={16} className="text-blue-300" />,
    text: "Baseado em LC 214/2025, EC 132/2023 e LC 227/2026",
  },
  {
    icon: <FileSearch size={16} className="text-blue-300" />,
    text: "Protocolo auditável P1→P6 com trilha de auditoria",
  },
  {
    icon: <BarChart3 size={16} className="text-blue-300" />,
    text: "Análise RAG em segundos com anti-alucinação M1–M4",
  },
];

export default function LoginPage() {
  const router = useRouter();
  const { setAuth } = useAuthStore();
  const [showPass, setShowPass] = useState(false);
  const [erro, setErro] = useState("");
  const [authMsg, setAuthMsg] = useState("");

  useEffect(() => {
    const msg = sessionStorage.getItem("auth_msg");
    if (msg) {
      setAuthMsg(msg);
      sessionStorage.removeItem("auth_msg");
    }
  }, []);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<Form>({ resolver: zodResolver(schema) });

  const onSubmit = async (data: Form) => {
    setErro("");
    try {
      const res = await api.post<LoginResponse>("/v1/auth/login", {
        email: data.email,
        senha: data.senha,
      });
      const { tenant_id, ...rest } = res.data.user;
      setAuth({ ...rest, tenant_id: tenant_id ?? "" }, res.data.access_token);
      router.push("/analisar");
    } catch {
      setErro("E-mail ou senha incorretos.");
    }
  };

  return (
    <div className="min-h-screen flex">

      {/* ── PAINEL ESQUERDO ───────────────────────────────────────── */}
      <div
        className="hidden lg:flex flex-col justify-between px-14 py-12 w-[46%] relative overflow-hidden"
        style={{ background: "linear-gradient(155deg, #1e4d96 0%, #1F3864 55%, #0e1f3a 100%)" }}
      >
        {/* Decoração sutil */}
        <div
          className="absolute -top-40 -right-40 w-[480px] h-[480px] rounded-full"
          style={{ background: "radial-gradient(circle, rgba(96,165,250,0.12) 0%, transparent 70%)" }}
        />
        <div
          className="absolute bottom-0 left-0 w-[340px] h-[340px] rounded-full"
          style={{ background: "radial-gradient(circle, rgba(147,197,253,0.07) 0%, transparent 70%)" }}
        />

        {/* Logo */}
        <div className="relative">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/logo.png"
            alt="Orbis.tax"
            style={{ width: "180px", height: "auto" }}
          />
        </div>

        {/* Conteúdo central */}
        <div className="relative">
          <div
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-semibold mb-8"
            style={{ background: "rgba(255,255,255,0.10)", color: "rgba(255,255,255,0.75)" }}
          >
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shrink-0" />
            Reforma Tributária · Corpus atualizado 2026
          </div>

          <h1 className="text-[2.6rem] font-extrabold text-white leading-[1.15] mb-5 tracking-tight">
            Decisões tributárias<br />documentadas,<br />
            <span style={{ color: "rgba(147,197,253,0.9)" }}>não opiniões genéricas.</span>
          </h1>

          <p className="text-base mb-10 max-w-[320px] leading-relaxed" style={{ color: "rgba(255,255,255,0.55)" }}>
            Análise jurídica fundamentada com citação de fonte, grau de confiança e trilha de auditoria em cada resposta.
          </p>

          <ul className="space-y-4">
            {BULLETS.map(({ icon, text }) => (
              <li key={text} className="flex items-start gap-3">
                <div
                  className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 mt-0.5"
                  style={{ background: "rgba(255,255,255,0.10)" }}
                >
                  {icon}
                </div>
                <span className="text-sm leading-snug" style={{ color: "rgba(255,255,255,0.72)" }}>
                  {text}
                </span>
              </li>
            ))}
          </ul>
        </div>

        {/* Rodapé esquerdo */}
        <p className="relative text-xs" style={{ color: "rgba(255,255,255,0.25)" }}>
          © 2026 Orbis.tax · Não constitui parecer jurídico
        </p>
      </div>

      {/* ── PAINEL DIREITO ────────────────────────────────────────── */}
      <div className="flex-1 flex items-center justify-center p-8" style={{ background: "#f1f5f9" }}>
        <div className="w-full max-w-[420px]">

          {/* Logo mobile */}
          <div className="lg:hidden mb-8 text-center">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/logo.png" alt="Orbis.tax" style={{ height: "36px", width: "auto", margin: "0 auto 8px" }} />
            <p className="text-sm text-slate-500">Inteligência Tributária · Reforma 2026</p>
          </div>

          {/* Card do formulário */}
          <div
            className="rounded-2xl p-8"
            style={{
              background: "#ffffff",
              boxShadow: "0 4px 32px rgba(15,32,68,0.10), 0 1px 4px rgba(15,32,68,0.06)",
              border: "1px solid rgba(226,232,240,0.8)",
            }}
          >
            <div className="mb-8">
              <h2 className="text-2xl font-bold mb-1" style={{ color: "#0f2040" }}>
                Entrar na plataforma
              </h2>
              <p className="text-sm" style={{ color: "#64748b" }}>
                Acesse sua conta para continuar
              </p>
            </div>

            {authMsg && (
              <div className="mb-5 p-3 rounded-lg" style={{ background: "#fffbeb", border: "1px solid #fcd34d" }}>
                <p className="text-xs font-medium" style={{ color: "#92400e" }}>{authMsg}</p>
              </div>
            )}

            <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
              {/* E-mail */}
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider mb-1.5" style={{ color: "#475569" }}>
                  E-mail
                </label>
                <Input
                  {...register("email")}
                  type="email"
                  placeholder="seu@email.com.br"
                  className="h-11 bg-slate-50 border-slate-200 text-slate-900 placeholder:text-slate-400 focus:border-blue-500 focus:ring-blue-500/20"
                  autoComplete="email"
                />
                {errors.email && (
                  <p className="text-xs text-red-500 mt-1">{errors.email.message}</p>
                )}
              </div>

              {/* Senha */}
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider mb-1.5" style={{ color: "#475569" }}>
                  Senha
                </label>
                <div className="relative">
                  <Input
                    {...register("senha")}
                    type={showPass ? "text" : "password"}
                    placeholder="••••••••"
                    className="h-11 bg-slate-50 border-slate-200 text-slate-900 placeholder:text-slate-400 focus:border-blue-500 focus:ring-blue-500/20 pr-11"
                    autoComplete="current-password"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPass(!showPass)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 transition-colors cursor-pointer"
                    aria-label={showPass ? "Ocultar senha" : "Mostrar senha"}
                  >
                    {showPass ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>
                {errors.senha && (
                  <p className="text-xs text-red-500 mt-1">{errors.senha.message}</p>
                )}
              </div>

              {/* Erro de credenciais */}
              {erro && (
                <div className="p-3 rounded-lg" style={{ background: "#fef2f2", border: "1px solid #fecaca" }}>
                  <p className="text-xs font-medium" style={{ color: "#dc2626" }}>{erro}</p>
                </div>
              )}

              <Button
                type="submit"
                className="w-full h-11 font-semibold text-white text-sm mt-2 cursor-pointer"
                style={{
                  background: "linear-gradient(135deg, #2E75B6 0%, #1F3864 100%)",
                  boxShadow: "0 4px 14px rgba(30,77,150,0.35)",
                }}
                disabled={isSubmitting}
              >
                {isSubmitting ? "Entrando…" : "Entrar"}
              </Button>
            </form>
          </div>

          <p className="text-center text-xs mt-6" style={{ color: "#94a3b8" }}>
            Orbis.tax © 2026 · Não constitui parecer jurídico
          </p>
        </div>
      </div>
    </div>
  );
}
