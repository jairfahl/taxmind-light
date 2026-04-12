/**
 * GuiaSimulador — painel de ajuda contextual por aba.
 * Exibido abaixo do botão Simular. Colapsável. Abre por padrão.
 */
"use client";
import { useState } from "react";
import { ChevronDown, ChevronUp, HelpCircle } from "lucide-react";
import { cn } from "@/lib/utils";

interface CampoGuia {
  campo: string;
  descricao: string;
  exemplo?: string;
}

interface Props {
  campos: CampoGuia[];
  observacao?: string;
  alertaCritico?: string;
}

export function GuiaSimulador({ campos, observacao, alertaCritico }: Props) {
  const [aberto, setAberto] = useState(true);

  return (
    <div className="mt-4 border border-border rounded-lg overflow-hidden">

      {/* Header — sempre visível */}
      <button
        onClick={() => setAberto(!aberto)}
        className="w-full flex items-center justify-between px-4 py-3 bg-muted/30 hover:bg-muted/50 transition-colors text-left"
      >
        <div className="flex items-center gap-2">
          <HelpCircle size={14} className="text-primary" />
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Como usar este simulador
          </span>
        </div>
        {aberto
          ? <ChevronUp size={14} className="text-muted-foreground" />
          : <ChevronDown size={14} className="text-muted-foreground" />
        }
      </button>

      {/* Conteúdo colapsável */}
      {aberto && (
        <div className="px-4 py-4 space-y-4">

          {/* Alerta crítico (ex: IS sem regulamentação) */}
          {alertaCritico && (
            <div className="p-3 bg-red-950/40 border border-red-800/40 rounded-md">
              <p className="text-xs text-red-400 font-medium">🔴 {alertaCritico}</p>
            </div>
          )}

          {/* Tabela de campos */}
          <div className="space-y-2">
            {campos.map((c, i) => (
              <div key={i} className="grid grid-cols-[180px_1fr] gap-3 text-xs">
                <span className="font-medium text-foreground pt-0.5">{c.campo}</span>
                <div>
                  <span className="text-muted-foreground">{c.descricao}</span>
                  {c.exemplo && (
                    <span className="text-muted-foreground/70 italic"> Ex: {c.exemplo}</span>
                  )}
                </div>
              </div>
            ))}
          </div>

          {/* Observação geral */}
          {observacao && (
            <p className="text-xs text-muted-foreground border-t border-border pt-3 italic">
              ⚠ {observacao}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
