import { AlertTriangle, Info, AlertCircle } from "lucide-react";
import type { Criticidade } from "@/types";

const CONFIG = {
  critico: {
    label: "CRÍTICO",
    icon: AlertTriangle,
    cls: "bg-red-950 text-red-400 border-red-800",
    shadow: "shadow-[0_2px_8px_rgba(239,68,68,.25)]",
  },
  atencao: {
    label: "ATENÇÃO",
    icon: AlertCircle,
    cls: "bg-amber-950 text-amber-400 border-amber-800",
    shadow: "shadow-[0_2px_8px_rgba(245,158,11,.25)]",
  },
  informativo: {
    label: "INFORMATIVO",
    icon: Info,
    cls: "bg-blue-950 text-blue-400 border-blue-800",
    shadow: "shadow-[0_2px_8px_rgba(46,117,182,.20)]",
  },
};

export function BadgeCriticidade({
  nivel,
  compacto = false,
}: {
  nivel: Criticidade;
  compacto?: boolean;
}) {
  const c = CONFIG[nivel] ?? CONFIG.informativo;
  const Icon = c.icon;

  if (compacto) {
    return (
      <span
        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-bold border ${c.cls}`}
      >
        <Icon size={11} />
        {c.label}
      </span>
    );
  }

  return (
    <div className={`flex items-center gap-3 px-4 py-1.5 rounded-lg border ${c.cls} ${c.shadow}`}>
      <Icon size={16} className="shrink-0" />
      <p className="text-sm font-bold">{c.label}</p>
    </div>
  );
}
