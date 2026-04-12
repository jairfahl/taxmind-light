import { cn } from "@/lib/utils";

const ACENTOS = {
  primary: "border-t-2 border-t-blue-500",
  success: "border-l-4 border-l-emerald-500",
  warning: "border-l-4 border-l-amber-500",
  danger:  "border-l-4 border-l-red-500 bg-red-50/60",
  muted:   "border-l-4 border-l-slate-400",
};

interface Props {
  children: React.ReactNode;
  className?: string;
  acento?: keyof typeof ACENTOS;
  titulo?: string;
  clickable?: boolean;
}

export function Card({ children, className, acento, titulo, clickable }: Props) {
  return (
    <div
      className={cn(
        "bg-card rounded-lg border border-border p-5",
        "shadow-[var(--shadow-card)] transition-all duration-[180ms]",
        acento && ACENTOS[acento],
        clickable && "hover:shadow-[var(--shadow-card-hover)] hover:-translate-y-0.5 cursor-pointer",
        className
      )}
    >
      {titulo && (
        <p
          className={cn(
            "text-xs font-semibold uppercase tracking-wider mb-4",
            acento === "primary" ? "text-primary" : "text-muted-foreground"
          )}
        >
          {titulo}
        </p>
      )}
      {children}
    </div>
  );
}
