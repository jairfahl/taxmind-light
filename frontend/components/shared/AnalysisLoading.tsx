"use client";
import { useEffect, useState } from "react";

const MENSAGENS = [
  "Consultando LC 214/2025…",
  "Cruzando EC 132/2023…",
  "Aplicando protocolo P1→P6…",
  "Estruturando resposta…",
];

export function AnalysisLoading() {
  const [idx, setIdx] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setIdx((i) => (i + 1) % MENSAGENS.length);
    }, 3000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="flex flex-col items-center justify-center py-12 gap-5">
      {/* Spinner SVG com cores da marca */}
      <svg
        className="animate-spin"
        width="48"
        height="48"
        viewBox="0 0 48 48"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-label="Carregando"
      >
        <circle cx="24" cy="24" r="20" stroke="#E8F0FA" strokeWidth="4" />
        <path
          d="M44 24a20 20 0 0 0-20-20"
          stroke="url(#tm-spin-grad)"
          strokeWidth="4"
          strokeLinecap="round"
        />
        <defs>
          <linearGradient id="tm-spin-grad" x1="24" y1="4" x2="44" y2="24" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#2E75B6" />
            <stop offset="100%" stopColor="#1F3864" />
          </linearGradient>
        </defs>
      </svg>

      {/* Mensagem rotativa */}
      <p
        key={idx}
        className="text-sm text-muted-foreground transition-opacity duration-500"
      >
        {MENSAGENS[idx]}
      </p>
    </div>
  );
}
