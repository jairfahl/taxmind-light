"use client";
import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ShieldCheck, AlertCircle, Loader2 } from "lucide-react";
import Link from "next/link";
import { useAuthStore } from "@/store/auth";
import api from "@/lib/api";

interface VerifyResponse {
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

export default function VerifyEmailPage() {
  const router        = useRouter();
  const searchParams  = useSearchParams();
  const { setAuth }   = useAuthStore();

  const [estado, setEstado] = useState<"loading" | "sucesso" | "erro">("loading");
  const [mensagem, setMensagem] = useState("");

  useEffect(() => {
    const token = searchParams.get("token");
    if (!token) {
      setEstado("erro");
      setMensagem("Token de verificação não encontrado na URL.");
      return;
    }

    api
      .get<VerifyResponse>(`/v1/auth/verify-email?token=${encodeURIComponent(token)}`)
      .then((res) => {
        const { tenant_id, ...rest } = res.data.user;
        setAuth({ ...rest, tenant_id: tenant_id ?? "" }, res.data.access_token);
        setEstado("sucesso");
        setTimeout(() => router.push("/analisar"), 2000);
      })
      .catch(() => {
        setEstado("erro");
        setMensagem("Link inválido ou já utilizado. Solicite um novo cadastro ou entre em contato com o suporte.");
      });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div
      className="min-h-screen flex items-center justify-center p-8"
      style={{ background: "linear-gradient(155deg, #1e4d96 0%, #1F3864 55%, #0e1f3a 100%)" }}
    >
      <div
        className="w-full max-w-[420px] rounded-2xl p-10 text-center"
        style={{
          background: "#ffffff",
          boxShadow: "0 8px 40px rgba(15,32,68,0.25)",
          border: "1px solid rgba(226,232,240,0.8)",
        }}
      >
        {/* Logo */}
        <div className="mb-8">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/logo.png" alt="Orbis.tax" style={{ height: "40px", width: "auto", margin: "0 auto" }} />
        </div>

        {estado === "loading" && (
          <>
            <Loader2 size={40} className="mx-auto mb-4 animate-spin" style={{ color: "#2E75B6" }} />
            <h2 className="text-lg font-bold mb-2" style={{ color: "#0f2040" }}>
              Verificando seu e-mail…
            </h2>
            <p className="text-sm" style={{ color: "#64748b" }}>
              Aguarde um instante.
            </p>
          </>
        )}

        {estado === "sucesso" && (
          <>
            <div
              className="w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-4"
              style={{ background: "#dcfce7" }}
            >
              <ShieldCheck size={30} style={{ color: "#16a34a" }} />
            </div>
            <h2 className="text-xl font-bold mb-2" style={{ color: "#0f2040" }}>
              E-mail confirmado!
            </h2>
            <p className="text-sm mb-6" style={{ color: "#64748b" }}>
              Sua conta está ativa. Redirecionando para a plataforma…
            </p>
            <div className="w-full h-1 rounded-full overflow-hidden" style={{ background: "#e2e8f0" }}>
              <div
                className="h-1 rounded-full"
                style={{
                  background: "linear-gradient(90deg, #2E75B6, #1F3864)",
                  animation: "progress 2s linear forwards",
                  width: "0%",
                }}
              />
            </div>
            <style>{`@keyframes progress { from { width: 0% } to { width: 100% } }`}</style>
          </>
        )}

        {estado === "erro" && (
          <>
            <div
              className="w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-4"
              style={{ background: "#fef2f2" }}
            >
              <AlertCircle size={30} style={{ color: "#dc2626" }} />
            </div>
            <h2 className="text-xl font-bold mb-2" style={{ color: "#0f2040" }}>
              Verificação falhou
            </h2>
            <p className="text-sm mb-6" style={{ color: "#64748b" }}>
              {mensagem}
            </p>
            <Link
              href="/login"
              className="inline-block text-sm font-semibold"
              style={{ color: "#2E75B6" }}
            >
              Voltar para o login →
            </Link>
          </>
        )}
      </div>
    </div>
  );
}
