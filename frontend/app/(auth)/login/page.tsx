"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Eye, EyeOff, CheckCircle } from "lucide-react";
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
  "Baseado em LC 214/2025",
  "Protocolo auditável P1→P6",
  "Análise em segundos",
];

export default function LoginPage() {
  const router = useRouter();
  const { setAuth } = useAuthStore();
  const [showPass, setShowPass] = useState(false);
  const [erro, setErro] = useState("");

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
    <div className="min-h-screen flex flex-col md:flex-row">
      {/* Painel esquerdo — dark navy (desktop only) */}
      <div
        className="hidden md:flex flex-col justify-center px-12 py-16 md:w-2/5"
        style={{ background: "var(--gradient-primary, linear-gradient(135deg,#2E75B6 0%,#1F3864 100%))" }}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/logo.png" alt="Tribus-AI" className="h-24 w-auto mb-8 drop-shadow-lg" />
        <h2 className="text-3xl font-extrabold text-white leading-tight mb-2">
          Inteligência<br />Tributária
        </h2>
        <p className="text-white/65 text-sm mb-8">Reforma Tributária 2026</p>
        <ul className="space-y-3">
          {BULLETS.map((item) => (
            <li key={item} className="flex items-center gap-3 text-white/85 text-sm">
              <CheckCircle size={16} className="text-blue-300 shrink-0" />
              {item}
            </li>
          ))}
        </ul>
      </div>

      {/* Painel direito — formulário */}
      <div className="flex-1 flex items-center justify-center p-6 bg-background">
        <div className="w-full max-w-sm space-y-6">

          {/* Logo mobile */}
          <div className="md:hidden text-center">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/logo.png" alt="Tribus-AI" className="h-12 mx-auto mb-2" />
            <p className="text-sm text-muted-foreground">
              Inteligência Tributária · Reforma 2026
            </p>
          </div>

          {/* Card */}
          <div className="bg-card border border-border rounded-xl p-8">
            <h1 className="text-lg font-semibold mb-6 text-foreground">
              Entrar na plataforma
            </h1>

            <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
              {/* E-mail */}
              <div>
                <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  E-mail
                </label>
                <Input
                  {...register("email")}
                  type="email"
                  placeholder="seu@email.com.br"
                  className="mt-1 bg-input border-border"
                  autoComplete="email"
                />
                {errors.email && (
                  <p className="text-xs text-red-500 mt-1">{errors.email.message}</p>
                )}
              </div>

              {/* Senha */}
              <div>
                <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  Senha
                </label>
                <div className="relative mt-1">
                  <Input
                    {...register("senha")}
                    type={showPass ? "text" : "password"}
                    placeholder="••••••••"
                    className="bg-input border-border pr-10"
                    autoComplete="current-password"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPass(!showPass)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground cursor-pointer"
                    aria-label={showPass ? "Ocultar senha" : "Mostrar senha"}
                  >
                    {showPass ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>
                {errors.senha && (
                  <p className="text-xs text-red-500 mt-1">{errors.senha.message}</p>
                )}
              </div>

              {/* Erro de credenciais */}
              {erro && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-md">
                  <p className="text-xs text-red-600">{erro}</p>
                </div>
              )}

              <Button
                type="submit"
                className="w-full bg-primary hover:bg-primary/90 text-primary-foreground"
                disabled={isSubmitting}
              >
                {isSubmitting ? "Entrando…" : "Entrar"}
              </Button>
            </form>
          </div>

          <p className="text-center text-xs text-muted-foreground">
            Tribus-AI © 2026 · Não constitui parecer jurídico
          </p>
        </div>
      </div>
    </div>
  );
}
