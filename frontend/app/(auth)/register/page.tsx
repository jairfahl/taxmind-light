"use client";
import { useState } from "react";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Eye, EyeOff, ShieldCheck, Clock, Lock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import api from "@/lib/api";

const schema = z.object({
  nome:             z.string().min(2, "Nome deve ter ao menos 2 caracteres"),
  email:            z.string().email("E-mail inválido"),
  senha: z
    .string()
    .min(8, "Mínimo de 8 caracteres")
    .max(128, "Máximo de 128 caracteres")
    .regex(/[A-Z]/, "Inclua ao menos uma letra maiúscula")
    .regex(/[a-z]/, "Inclua ao menos uma letra minúscula")
    .regex(/\d/, "Inclua ao menos um número")
    .regex(/[!@#$%^&*()\-_=+\[\]{};:'",.<>?/\\|`~]/, "Inclua ao menos um caractere especial"),
  confirmar_senha:  z.string().min(1, "Confirme sua senha"),
  razao_social:     z.string().min(2, "Informe o nome da empresa"),
  documento:          z.string().optional().refine(
    (v) => !v || [11, 14].includes(v.replace(/\D/g, "").length),
    "Informe um CPF (11 dígitos) ou CNPJ (14 dígitos)."
  ),
  marketing_consent:  z.boolean().optional(),
  lgpd_consent:       z.boolean().refine((v) => v === true, {
    message: "Você precisa aceitar o tratamento de dados para continuar.",
  }),
}).refine((d) => d.senha === d.confirmar_senha, {
  message: "As senhas não coincidem.",
  path: ["confirmar_senha"],
});
type Form = z.infer<typeof schema>;

const BULLETS = [
  {
    icon: <Clock size={16} className="text-blue-300" />,
    text: "7 dias grátis — sem cartão de crédito",
  },
  {
    icon: <ShieldCheck size={16} className="text-blue-300" />,
    text: "Normas da Reforma Tributária interpretadas e verificadas",
  },
  {
    icon: <Lock size={16} className="text-blue-300" />,
    text: "Dados protegidos pela LGPD · Sem compartilhamento",
  },
];

function SenhaRequisitos({ senha }: { senha: string }) {
  const checks = [
    { ok: senha.length >= 8,          label: "8+ caracteres" },
    { ok: /[A-Z]/.test(senha),        label: "Maiúscula" },
    { ok: /[a-z]/.test(senha),        label: "Minúscula" },
    { ok: /\d/.test(senha),           label: "Número" },
    { ok: /[!@#$%^&*()\-_=+\[\]{};:'",.<>?/\\|`~]/.test(senha), label: "Caractere especial" },
  ];
  return (
    <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1.5">
      {checks.map(({ ok, label }) => (
        <span key={label} className="flex items-center gap-1 text-[11px]" style={{ color: ok ? "#16a34a" : "#94a3b8" }}>
          <span style={{ fontSize: "10px" }}>{ok ? "✓" : "○"}</span>
          {label}
        </span>
      ))}
    </div>
  );
}

export default function RegisterPage() {
  const [showPass, setShowPass]         = useState(false);
  const [showConfirm, setShowConfirm]   = useState(false);
  const [senhaAtual, setSenhaAtual]     = useState("");
  const [docTipo, setDocTipo]           = useState<"CPF" | "CNPJ" | null>(null);

  const formatarDocumento = (raw: string): string => {
    const d = raw.replace(/\D/g, "").slice(0, 14);
    if (d.length <= 11) {
      // CPF: 000.000.000-00
      return d
        .replace(/(\d{3})(\d)/, "$1.$2")
        .replace(/(\d{3})(\d)/, "$1.$2")
        .replace(/(\d{3})(\d{1,2})$/, "$1-$2");
    }
    // CNPJ: 00.000.000/0000-00
    return d
      .replace(/(\d{2})(\d)/, "$1.$2")
      .replace(/(\d{3})(\d)/, "$1.$2")
      .replace(/(\d{3})(\d)/, "$1/$2")
      .replace(/(\d{4})(\d{1,2})$/, "$1-$2");
  };
  const [erro, setErro] = useState("");
  const [sucesso, setSucesso] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<Form>({ resolver: zodResolver(schema) });

  const onSubmit = async (data: Form) => {
    setErro("");
    try {
      await api.post("/v1/auth/register", {
        nome:         data.nome,
        email:        data.email,
        senha:        data.senha,
        razao_social: data.razao_social,
        cnpj_raiz:         data.documento ? data.documento.replace(/\D/g, "") : undefined,
        lgpd_consent:      data.lgpd_consent,
        marketing_consent: data.marketing_consent ?? false,
      });
      setSucesso(true);
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number; data?: { detail?: string } } })?.response?.status;
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      if (status === 409) {
        setErro(detail ?? "E-mail ou CNPJ já cadastrado.");
      } else {
        setErro(detail ?? "Erro ao realizar cadastro. Tente novamente.");
      }
    }
  };

  return (
    <div className="min-h-screen flex">

      {/* ── PAINEL ESQUERDO ───────────────────────────────────────── */}
      <div
        className="hidden lg:flex flex-col justify-between px-14 py-12 w-[46%] relative overflow-hidden"
        style={{ background: "linear-gradient(155deg, #1e4d96 0%, #1F3864 55%, #0e1f3a 100%)" }}
      >
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
          <img src="/logo-dark.png" alt="Orbis.tax" style={{ width: "180px", height: "auto" }} />
        </div>

        {/* Conteúdo central */}
        <div className="relative">
          <div
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-semibold mb-8"
            style={{ background: "rgba(255,255,255,0.10)", color: "rgba(255,255,255,0.75)" }}
          >
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shrink-0" />
            Trial gratuito · 7 dias · Sem cartão
          </div>

          <h1 className="text-[2.8rem] font-extrabold text-white leading-[1.18] mb-5 tracking-tight">
            Comece agora<br />e domine a<br />
            <span style={{ color: "rgba(147,197,253,0.9)" }}>Reforma Tributária.</span>
          </h1>

          <p className="text-base mb-10 max-w-[320px] leading-relaxed" style={{ color: "rgba(255,255,255,0.55)" }}>
            Crie sua conta em menos de 1 minuto e acesse o protocolo cognitivo P1→P6 com corpus curado e trilha de auditoria.
          </p>

          <ul className="space-y-4">
            {BULLETS.map(({ icon, text }) => (
              <li key={text} className="flex items-center gap-3">
                <div
                  className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
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

        <p className="relative text-xs" style={{ color: "rgba(255,255,255,0.25)" }}>
          © 2026 Orbis.tax · Não constitui parecer jurídico
        </p>
      </div>

      {/* ── PAINEL DIREITO ────────────────────────────────────────── */}
      <div className="flex-1 flex items-center justify-center p-8" style={{ background: "#f1f5f9" }}>
        <div className="w-full max-w-[440px]">

          {/* Logo mobile */}
          <div className="lg:hidden mb-8 text-center">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/logo.png" alt="Orbis.tax" style={{ height: "44px", width: "auto", margin: "0 auto 8px" }} />
            <p className="text-sm text-slate-500">7 dias grátis · sem cartão</p>
          </div>

          {/* Card */}
          <div
            className="rounded-2xl p-8"
            style={{
              background: "#ffffff",
              boxShadow: "0 4px 32px rgba(15,32,68,0.10), 0 1px 4px rgba(15,32,68,0.06)",
              border: "1px solid rgba(226,232,240,0.8)",
            }}
          >
            {sucesso ? (
              /* ── Estado de sucesso ── */
              <div className="text-center py-4">
                <div
                  className="w-14 h-14 rounded-full flex items-center justify-center mx-auto mb-4"
                  style={{ background: "#dcfce7" }}
                >
                  <ShieldCheck size={26} style={{ color: "#16a34a" }} />
                </div>
                <h2 className="text-xl font-bold mb-2" style={{ color: "#0f2040" }}>
                  Cadastro realizado!
                </h2>
                <p className="text-sm mb-6" style={{ color: "#64748b" }}>
                  Enviamos um e-mail de confirmação para o endereço informado.
                  Verifique sua caixa de entrada (e spam) e clique no link para ativar sua conta.
                </p>
                <Link
                  href="/login"
                  className="text-sm font-semibold"
                  style={{ color: "#2E75B6" }}
                >
                  Voltar para o login →
                </Link>
              </div>
            ) : (
              /* ── Formulário ── */
              <>
                <div className="mb-6">
                  <h2 className="text-2xl font-bold mb-1" style={{ color: "#0f2040" }}>
                    Criar conta grátis
                  </h2>
                  <p className="text-sm" style={{ color: "#64748b" }}>
                    7 dias de trial · sem cartão de crédito
                  </p>
                </div>

                <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
                  {/* Nome */}
                  <div>
                    <label className="block text-xs font-semibold uppercase tracking-wider mb-1.5" style={{ color: "#475569" }}>
                      Nome completo <span className="text-red-500">*</span>
                    </label>
                    <Input
                      {...register("nome")}
                      type="text"
                      placeholder="João da Silva"
                      className="h-11 bg-slate-50 border-slate-200 text-slate-900 placeholder:text-slate-500 focus:border-blue-500 focus:ring-blue-500/20"
                      autoComplete="name"
                    />
                    {errors.nome && <p className="text-xs text-red-500 mt-1">{errors.nome.message}</p>}
                  </div>

                  {/* E-mail */}
                  <div>
                    <label className="block text-xs font-semibold uppercase tracking-wider mb-1.5" style={{ color: "#475569" }}>
                      E-mail <span className="text-red-500">*</span>
                    </label>
                    <Input
                      {...register("email")}
                      type="email"
                      placeholder="joao@empresa.com.br"
                      className="h-11 bg-slate-50 border-slate-200 text-slate-900 placeholder:text-slate-500 focus:border-blue-500 focus:ring-blue-500/20"
                      autoComplete="email"
                    />
                    {errors.email && <p className="text-xs text-red-500 mt-1">{errors.email.message}</p>}
                  </div>

                  {/* Senha */}
                  <div>
                    <label className="block text-xs font-semibold uppercase tracking-wider mb-1.5" style={{ color: "#475569" }}>
                      Senha <span className="text-red-500">*</span>
                    </label>
                    <div className="relative">
                      <Input
                        {...register("senha")}
                        type={showPass ? "text" : "password"}
                        placeholder="Mínimo 8 caracteres"
                        className="h-11 bg-slate-50 border-slate-200 text-slate-900 placeholder:text-slate-500 focus:border-blue-500 focus:ring-blue-500/20 pr-11"
                        autoComplete="new-password"
                        onChange={(e) => {
                          setSenhaAtual(e.target.value);
                          register("senha").onChange(e);
                        }}
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
                    <SenhaRequisitos senha={senhaAtual} />
                    {errors.senha && <p className="text-xs text-red-500 mt-1">{errors.senha.message}</p>}
                  </div>

                  {/* Confirmar Senha */}
                  <div>
                    <label className="block text-xs font-semibold uppercase tracking-wider mb-1.5" style={{ color: "#475569" }}>
                      Confirmar senha <span className="text-red-500">*</span>
                    </label>
                    <div className="relative">
                      <Input
                        {...register("confirmar_senha")}
                        type={showConfirm ? "text" : "password"}
                        placeholder="Repita a senha"
                        className="h-11 bg-slate-50 border-slate-200 text-slate-900 placeholder:text-slate-500 focus:border-blue-500 focus:ring-blue-500/20 pr-11"
                        autoComplete="new-password"
                      />
                      <button
                        type="button"
                        onClick={() => setShowConfirm(!showConfirm)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 transition-colors cursor-pointer"
                        aria-label={showConfirm ? "Ocultar senha" : "Mostrar senha"}
                      >
                        {showConfirm ? <EyeOff size={15} /> : <Eye size={15} />}
                      </button>
                    </div>
                    {errors.confirmar_senha && <p className="text-xs text-red-500 mt-1">{errors.confirmar_senha.message}</p>}
                  </div>

                  {/* Empresa */}
                  <div>
                    <label className="block text-xs font-semibold uppercase tracking-wider mb-1.5" style={{ color: "#475569" }}>
                      Empresa (Razão Social) <span className="text-red-500">*</span>
                    </label>
                    <Input
                      {...register("razao_social")}
                      type="text"
                      placeholder="Empresa Ltda."
                      className="h-11 bg-slate-50 border-slate-200 text-slate-900 placeholder:text-slate-500 focus:border-blue-500 focus:ring-blue-500/20"
                      autoComplete="organization"
                    />
                    {errors.razao_social && <p className="text-xs text-red-500 mt-1">{errors.razao_social.message}</p>}
                  </div>

                  {/* CPF / CNPJ (opcional) */}
                  <div>
                    <label className="block text-xs font-semibold uppercase tracking-wider mb-1.5 flex items-center gap-2" style={{ color: "#475569" }}>
                      CPF ou CNPJ
                      {docTipo && (
                        <span
                          className="text-[10px] font-bold px-1.5 py-0.5 rounded"
                          style={{ background: docTipo === "CPF" ? "#e0f2fe" : "#ede9fe", color: docTipo === "CPF" ? "#0369a1" : "#7c3aed" }}
                        >
                          {docTipo}
                        </span>
                      )}
                      <span className="font-normal normal-case" style={{ color: "#94a3b8" }}>(opcional)</span>
                    </label>
                    <Input
                      {...register("documento")}
                      type="text"
                      placeholder="000.000.000-00 ou 00.000.000/0000-00"
                      maxLength={18}
                      className="h-11 bg-slate-50 border-slate-200 text-slate-900 placeholder:text-slate-500 focus:border-blue-500 focus:ring-blue-500/20"
                      onChange={(e) => {
                        const digits = e.target.value.replace(/\D/g, "");
                        const formatted = formatarDocumento(e.target.value);
                        e.target.value = formatted;
                        setDocTipo(digits.length === 0 ? null : digits.length <= 11 ? "CPF" : "CNPJ");
                        // sync react-hook-form com valor formatado
                        (register("documento").onChange as (e: React.ChangeEvent<HTMLInputElement>) => void)(e);
                      }}
                    />
                    {errors.documento && <p className="text-xs text-red-500 mt-1">{errors.documento.message}</p>}
                  </div>

                  {/* Checkboxes de consentimento */}
                  <div className="space-y-3 pt-1">
                    {/* Marketing — opcional */}
                    <div className="flex items-start gap-3">
                      <input
                        {...register("marketing_consent")}
                        type="checkbox"
                        id="marketing"
                        className="mt-0.5 w-4 h-4 rounded border-slate-300 accent-blue-600 cursor-pointer shrink-0"
                      />
                      <label htmlFor="marketing" className="text-xs leading-relaxed cursor-pointer" style={{ color: "#64748b" }}>
                        Concordo em receber comunicações e novidades da Orbis.tax por e-mail.{" "}
                        <span style={{ color: "#94a3b8" }}>(opcional)</span>
                      </label>
                    </div>

                    {/* LGPD — obrigatório */}
                    <div className="flex items-start gap-3">
                      <input
                        {...register("lgpd_consent")}
                        type="checkbox"
                        id="lgpd"
                        className="mt-0.5 w-4 h-4 rounded border-slate-300 accent-blue-600 cursor-pointer shrink-0"
                      />
                      <label htmlFor="lgpd" className="text-xs leading-relaxed cursor-pointer" style={{ color: "#64748b" }}>
                        Autorizo o tratamento dos meus dados conforme a{" "}
                        <span className="font-semibold" style={{ color: "#2E75B6" }}>LGPD (Lei 13.709/2018)</span>.{" "}
                        <span className="font-semibold" style={{ color: "#dc2626" }}>*</span>
                      </label>
                    </div>
                    {errors.lgpd_consent && (
                      <p className="text-xs text-red-500">{errors.lgpd_consent.message}</p>
                    )}
                  </div>

                  {/* Erro geral */}
                  {erro && (
                    <div className="p-3 rounded-lg" style={{ background: "#fef2f2", border: "1px solid #fecaca" }}>
                      <p className="text-xs font-medium" style={{ color: "#dc2626" }}>{erro}</p>
                    </div>
                  )}

                  <Button
                    type="submit"
                    className="w-full h-11 font-semibold text-white text-sm mt-1 cursor-pointer"
                    style={{
                      background: "linear-gradient(135deg, #2E75B6 0%, #1F3864 100%)",
                      boxShadow: "0 4px 14px rgba(30,77,150,0.35)",
                    }}
                    disabled={isSubmitting}
                  >
                    {isSubmitting ? "Criando conta…" : "Criar conta grátis"}
                  </Button>
                </form>

                <p className="text-center text-xs mt-5" style={{ color: "#94a3b8" }}>
                  Já tem conta?{" "}
                  <Link href="/login" className="font-semibold" style={{ color: "#2E75B6" }}>
                    Entrar
                  </Link>
                </p>
              </>
            )}
          </div>

          <p className="text-center text-xs mt-6" style={{ color: "#94a3b8" }}>
            Orbis.tax © 2026 · Não constitui parecer jurídico
          </p>
        </div>
      </div>
    </div>
  );
}
