"use client";
import { useState } from "react";
import { FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import Link from "next/link";
import { FluxoDocumentacao } from "./FluxoDocumentacao";
import type { ResultadoAnalise } from "@/types";

interface Props {
  query: string;
  resultado: ResultadoAnalise;
}

export function CTADocumentar({ query, resultado }: Props) {
  const [expandido, setExpandido] = useState(false);
  const [concluido, setConcluido] = useState(false);

  if (concluido) {
    return (
      <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-lg">
        <p className="text-sm font-medium text-emerald-700">
          ✅ Análise registrada e protegida.
        </p>
        <p className="text-xs text-emerald-600 mt-1">
          🔒 Legal Hold ativo · Imutável · Defensável perante o Fisco
        </p>
        <Link
          href="/documentos"
          className="text-xs text-primary hover:underline mt-2 inline-block"
        >
          Ver em Documentos →
        </Link>
      </div>
    );
  }

  return (
    <div className="border border-border rounded-lg overflow-hidden">
      {/* Header do CTA */}
      <div className="p-4 bg-muted/30 flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <FileText size={16} className="text-primary mt-0.5 shrink-0" />
          <div>
            <p className="text-sm font-medium">Quer documentar esta análise?</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              Registre sua decisão em 3 passos. Gera trilha de auditoria imutável.
            </p>
          </div>
        </div>
        {!expandido && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => setExpandido(true)}
            className="shrink-0 text-xs"
          >
            Documentar →
          </Button>
        )}
      </div>

      {/* Fluxo de documentação expandido */}
      {expandido && (
        <div className="p-4 border-t border-border">
          <FluxoDocumentacao
            query={query}
            resultado={resultado}
            onConcluido={() => setConcluido(true)}
            onCancelar={() => setExpandido(false)}
          />
        </div>
      )}
    </div>
  );
}
