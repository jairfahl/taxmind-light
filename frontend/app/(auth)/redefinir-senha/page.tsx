"use client";
import { useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Eye, EyeOff, CheckCircle, AlertCircle, Loader2 } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import api from "@/lib/api";

const schema = z.object({
  nova_senha: z
    .string()
    .min(8, "Mínimo de 8 caracteres")
    .max(128)
    .regex(/[A-Z]/, "Inclua ao menos uma letra maiúscula")
    .regex(/[a-z]/, "Inclua ao menos uma letra minúscula")
    .regex(/\d/, "Inclua ao menos um número")
    .regex(/[!@#$%^&*()\-_=+\[\]{};:'",.<>?/\\|`~]/, "Inclua ao menos um caractere especial"),
  confirmar: z.string().min(1, "Confirme a nova senha"),
}).refine((d) => d.nova_senha === d.confirmar, {
  message: "As senhas não coincidem.",
  path: ["confirmar"],
});
type Form = z.infer<typeof schema>;

function SenhaRequisitos({ senha }: { senha: string }) {
  const checks = [
    { ok: senha.length >= 8,                                              label: "8+ caracteres" },
    { ok: /[A-Z]/.test(senha),                                           label: "Maiúscula" },
    { ok: /[a-z]/.test(senha),                                           label: "Minúscula" },
    { ok: /\d/.test(senha),                                              label: "Número" },
    { ok: /[!@#$%^&*()\-_=+\[\]{};:'",.<>?/\\|`~]/.test(senha),        label: "Especial" },
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

function RedefinirSenhaContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";

  const [showPass, setShowPass]     = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [senhaAtual, setSenhaAtual] = useState("");
  const [sucesso, setSucesso]       = useState(false);
  const [erro, setErro]             = useState("");

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<Form>({ resolver: zodResolver(schema) });

  if (!token) {
    return (
      <div className="text-center">
        <AlertCircle size={40} className="mx-auto mb-4" style={{ color: "#dc2626" }} />
        <h2 className="text-xl font-bold mb-2 text-foreground">Link inválido</h2>
        <p className="text-sm mb-4 text-muted-foreground">Token não encontrado na URL.</p>
        <Link href="/recuperar-senha" className="text-sm font-semibold" style={{ color: "#2E75B6" }}>
          Solicitar novo link →
        </Link>
      </div>
    );
  }

  const onSubmit = async (data: Form) => {
    setErro("");
    try {
      await api.post("/v1/auth/reset-password", { token, nova_senha: data.nova_senha });
      setSucesso(true);
      setTimeout(() => router.push("/login"), 3000);
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number; data?: { detail?: string } } })?.response?.status;
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      if (status === 404) {
        setErro(detail ?? "Link inválido ou expirado. Solicite um novo.");
      } else {
        setErro("Erro ao redefinir senha. Tente novamente.");
      }
    }
  };

  return sucesso ? (
    <div className="text-center">
      <div className="w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-4" style={{ background: "#dcfce7" }}>
        <CheckCircle size={30} style={{ color: "#16a34a" }} />
      </div>
      <h2 className="text-xl font-bold mb-2 text-foreground">Senha redefinida!</h2>
      <p className="text-sm mb-4 text-muted-foreground">Redirecionando para o login…</p>
      <div className="w-full h-1 rounded-full overflow-hidden" style={{ background: "#e2e8f0" }}>
        <div
          className="h-1 rounded-full"
          style={{
            background: "linear-gradient(90deg, #2E75B6, #1F3864)",
            animation: "progress 3s linear forwards",
            width: "0%",
          }}
        />
      </div>
      <style>{`@keyframes progress { from { width: 0% } to { width: 100% } }`}</style>
    </div>
  ) : (
    <>
      <div className="mb-6">
        <h2 className="text-2xl font-bold mb-1 text-foreground">Nova senha</h2>
        <p className="text-sm text-muted-foreground">Escolha uma senha forte para sua conta.</p>
      </div>

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        {/* Nova senha */}
        <div>
          <label className="block text-xs font-semibold uppercase tracking-wider mb-1.5" style={{ color: "#475569" }}>
            Nova senha <span className="text-red-500">*</span>
          </label>
          <div className="relative">
            <Input
              {...register("nova_senha")}
              type={showPass ? "text" : "password"}
              placeholder="Mínimo 8 caracteres"
              className="h-11 bg-slate-50 border-slate-200 text-slate-900 placeholder:text-slate-500 focus:border-blue-500 focus:ring-blue-500/20 pr-11"
              autoComplete="new-password"
              onChange={(e) => { setSenhaAtual(e.target.value); register("nova_senha").onChange(e); }}
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
          {errors.nova_senha && <p className="text-xs text-red-500 mt-1">{errors.nova_senha.message}</p>}
        </div>

        {/* Confirmar */}
        <div>
          <label className="block text-xs font-semibold uppercase tracking-wider mb-1.5" style={{ color: "#475569" }}>
            Confirmar senha <span className="text-red-500">*</span>
          </label>
          <div className="relative">
            <Input
              {...register("confirmar")}
              type={showConfirm ? "text" : "password"}
              placeholder="Repita a nova senha"
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
          {errors.confirmar && <p className="text-xs text-red-500 mt-1">{errors.confirmar.message}</p>}
        </div>

        {erro && (
          <div className="p-3 rounded-lg" style={{ background: "#fef2f2", border: "1px solid #fecaca" }}>
            <p className="text-xs font-medium text-red-600">{erro}</p>
            {erro.includes("inválido") && (
              <Link href="/recuperar-senha" className="text-xs font-semibold mt-1 block" style={{ color: "#2E75B6" }}>
                Solicitar novo link →
              </Link>
            )}
          </div>
        )}

        <Button
          type="submit"
          disabled={isSubmitting}
          className="w-full h-11 font-semibold text-white text-sm cursor-pointer"
          style={{
            background: "linear-gradient(135deg, #2E75B6 0%, #1F3864 100%)",
            boxShadow: "0 4px 14px rgba(30,77,150,.30)",
          }}
        >
          {isSubmitting ? "Salvando…" : "Salvar nova senha"}
        </Button>
      </form>
    </>
  );
}

export default function RedefinirSenhaPage() {
  return (
    <div
      className="min-h-screen flex items-center justify-center p-8"
      style={{ background: "linear-gradient(155deg, #1e4d96 0%, #1F3864 55%, #0e1f3a 100%)" }}
    >
      <div
        className="w-full max-w-[420px] rounded-2xl p-10"
        style={{
          background: "#ffffff",
          boxShadow: "0 8px 40px rgba(15,32,68,0.25)",
          border: "1px solid rgba(226,232,240,0.8)",
        }}
      >
        {/* Logo */}
        <div className="mb-8 text-center">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/logo.png" alt="Orbis.tax" style={{ height: "48px", width: "auto", margin: "0 auto" }} />
        </div>

        <Suspense fallback={
          <div className="flex justify-center py-8">
            <Loader2 size={32} className="animate-spin" style={{ color: "#2E75B6" }} />
          </div>
        }>
          <RedefinirSenhaContent />
        </Suspense>
      </div>
    </div>
  );
}
