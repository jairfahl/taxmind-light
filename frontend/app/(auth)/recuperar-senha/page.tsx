"use client";
import { useState } from "react";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Mail, ArrowLeft, CheckCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import api from "@/lib/api";

const schema = z.object({
  email: z.string().email("Informe um e-mail válido"),
});
type Form = z.infer<typeof schema>;

export default function RecuperarSenhaPage() {
  const [sucesso, setSucesso] = useState(false);
  const [naoEncontrado, setNaoEncontrado] = useState(false);
  const [erro, setErro] = useState("");

  const {
    register,
    handleSubmit,
    getValues,
    formState: { errors, isSubmitting },
  } = useForm<Form>({ resolver: zodResolver(schema) });

  const onSubmit = async (data: Form) => {
    setErro("");
    setNaoEncontrado(false);
    try {
      await api.post("/v1/auth/forgot-password", { email: data.email });
      setSucesso(true);
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 404) {
        setNaoEncontrado(true);
      } else {
        setErro("Erro ao processar solicitação. Tente novamente.");
      }
    }
  };

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

        {sucesso ? (
          /* ── Sucesso ── */
          <div className="text-center">
            <div
              className="w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-4"
              style={{ background: "#dcfce7" }}
            >
              <CheckCircle size={30} style={{ color: "#16a34a" }} />
            </div>
            <h2 className="text-xl font-bold mb-2 text-foreground">E-mail enviado!</h2>
            <p className="text-sm mb-6 text-muted-foreground">
              Enviamos um link de redefinição para <strong>{getValues("email")}</strong>.
              Verifique sua caixa de entrada e spam.
            </p>
            <Link href="/login" className="text-sm font-semibold" style={{ color: "#2E75B6" }}>
              ← Voltar para o login
            </Link>
          </div>
        ) : naoEncontrado ? (
          /* ── Não encontrado ── */
          <div className="text-center">
            <div
              className="w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-4"
              style={{ background: "#fef9c3" }}
            >
              <Mail size={28} style={{ color: "#ca8a04" }} />
            </div>
            <h2 className="text-xl font-bold mb-2 text-foreground">E-mail não encontrado</h2>
            <p className="text-sm mb-6 text-muted-foreground">
              Não localizamos uma conta com este e-mail.
              Deseja criar uma conta gratuita?
            </p>
            <Link
              href="/register"
              className="block w-full h-11 flex items-center justify-center font-semibold text-white text-sm rounded-lg mb-4"
              style={{
                background: "linear-gradient(135deg, #2E75B6 0%, #1F3864 100%)",
                boxShadow: "0 4px 14px rgba(30,77,150,.30)",
              }}
            >
              Criar conta grátis
            </Link>
            <button
              type="button"
              onClick={() => setNaoEncontrado(false)}
              className="text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              ← Tentar outro e-mail
            </button>
          </div>
        ) : (
          /* ── Formulário ── */
          <>
            <div className="mb-6">
              <h2 className="text-2xl font-bold mb-1 text-foreground">Recuperar senha</h2>
              <p className="text-sm text-muted-foreground">
                Informe seu e-mail e enviaremos um link para redefinir sua senha.
              </p>
            </div>

            <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider mb-1.5" style={{ color: "#475569" }}>
                  E-mail <span className="text-red-500">*</span>
                </label>
                <Input
                  {...register("email")}
                  type="email"
                  placeholder="seu@email.com.br"
                  className="h-11 bg-slate-50 border-slate-200 text-slate-900 placeholder:text-slate-500 focus:border-blue-500 focus:ring-blue-500/20"
                  autoComplete="email"
                  autoFocus
                />
                {errors.email && <p className="text-xs text-red-500 mt-1">{errors.email.message}</p>}
              </div>

              {erro && (
                <div className="p-3 rounded-lg" style={{ background: "#fef2f2", border: "1px solid #fecaca" }}>
                  <p className="text-xs font-medium text-red-600">{erro}</p>
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
                {isSubmitting ? "Enviando…" : "Enviar link de recuperação"}
              </Button>
            </form>

            <Link
              href="/login"
              className="flex items-center justify-center gap-1.5 text-sm mt-6 text-muted-foreground hover:text-foreground transition-colors"
            >
              <ArrowLeft size={14} /> Voltar para o login
            </Link>
          </>
        )}
      </div>
    </div>
  );
}
