import { Shield } from "lucide-react";
import { BadgeGrau } from "./BadgeGrau";
import { Disclaimer } from "./Disclaimer";
import type { GrauConsolidacao, ForcaContraTese, NivelConfianca } from "@/types";

const SCORE_STYLE: Record<NivelConfianca, { text: string; card: string }> = {
  alto:  { text: "text-emerald-700 font-semibold uppercase", card: "bg-emerald-50 border-emerald-200" },
  medio: { text: "text-amber-700 font-semibold uppercase",   card: "bg-amber-50 border-amber-200" },
  baixo: { text: "text-red-700 font-semibold uppercase",     card: "bg-red-50 border-red-200" },
};

interface Props {
  grau: GrauConsolidacao;
  forcaContraTese?: ForcaContraTese;
  scoringConfianca?: NivelConfianca;
  risco?: string;
  mostrarDisclaimer?: boolean;
}

export function PainelGovernanca({
  grau,
  forcaContraTese,
  scoringConfianca,
  risco,
  mostrarDisclaimer = true,
}: Props) {
  return (
    <div className="border-t border-border pt-4 mt-4 space-y-3">
      {/* Header com ícone Shield */}
      <div className="flex items-center gap-2 px-3 py-2 rounded-md bg-blue-50 border border-blue-100">
        <Shield size={14} className="text-primary shrink-0" />
        <p className="text-xs font-semibold text-primary uppercase tracking-wider">
          Governança da Análise
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {/* Grau de Consolidação */}
        <div className="p-3 rounded-lg border bg-blue-50 border-blue-200">
          <p className="text-xs text-muted-foreground mb-1">Grau de Consolidação</p>
          <BadgeGrau grau={grau} />
        </div>

        {/* Força da Contra-Tese */}
        {forcaContraTese && (
          <div className="p-3 rounded-lg border bg-slate-50 border-slate-200">
            <p className="text-xs text-muted-foreground mb-1">Força da Contra-Tese</p>
            <p className="text-sm font-medium text-foreground">{forcaContraTese}</p>
          </div>
        )}

        {/* Scoring de Confiança */}
        {scoringConfianca && (
          <div className={`p-3 rounded-lg border ${SCORE_STYLE[scoringConfianca].card}`}>
            <p className="text-xs text-muted-foreground mb-1">Scoring de Confiança</p>
            <p className={`text-sm ${SCORE_STYLE[scoringConfianca].text}`}>
              {scoringConfianca}
            </p>
          </div>
        )}
      </div>

      {risco && (
        <div className="p-3 bg-amber-50 border border-amber-200 rounded-md">
          <p className="text-xs text-amber-700">⚠ {risco}</p>
        </div>
      )}

      {mostrarDisclaimer && <Disclaimer />}
    </div>
  );
}
