"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Search,
  GitBranch,
  BarChart2,
  FolderOpen,
  BookOpen,
  Settings,
  LogOut,
  CheckCircle,
} from "lucide-react";
import { useAuthStore } from "@/store/auth";
import { cn } from "@/lib/utils";


function diasRestantes(trialEndsAt: string): number {
  const hoje = new Date();
  hoje.setHours(0, 0, 0, 0);
  const fim = new Date(trialEndsAt);
  fim.setHours(0, 0, 0, 0);
  return Math.max(0, Math.round((fim.getTime() - hoje.getTime()) / 86_400_000));
}

const NAV = [
  { href: "/analisar",          label: "Analisar",       icon: Search,    destaque: true },
  { href: "/documentos",        label: "Documentos",     icon: FolderOpen, destaque: true },
  { href: "/simuladores",       label: "Simuladores",    icon: BarChart2,  destaque: true },
  { href: "/base-conhecimento", label: "Base de Normas", icon: BookOpen,   destaque: true },
  { href: "/protocolo",         label: "Modo Avançado",  icon: GitBranch,  destaque: false },
];

function getInitials(nome: string): string {
  return nome
    .split(" ")
    .map((n) => n[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

export function Sidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuthStore();

  return (
    <aside
      className="w-60 shrink-0 flex flex-col h-full"
      style={{ backgroundColor: "var(--color-bg-sidebar, #1a2f4e)" }}
    >
      {/* Logo */}
      <div className="px-5 pt-6 pb-5" style={{ borderBottom: "1px solid rgba(255,255,255,.12)" }}>
        <Link href="/analisar" className="flex flex-col items-center gap-2 group">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/logo.png"
            alt="Orbis.tax"
            className="h-20 w-auto drop-shadow-md group-hover:scale-105 transition-transform duration-200"
          />
          <div className="text-center">
            <span className="block font-extrabold text-lg tracking-tight text-white leading-none">
              Orbis<span style={{ color: "var(--color-accent-vivid, #3B9EE8)" }}>.tax</span>
            </span>
            <span className="block text-[10px] tracking-widest uppercase mt-0.5" style={{ color: "rgba(255,255,255,.55)" }}>
              Inteligência Tributária
            </span>
          </div>
        </Link>
      </div>

      {/* Navegação */}
      <nav className="flex-1 p-3 space-y-0.5">
        {NAV.map(({ href, label, icon: Icon, destaque }) => {
          const active = pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 px-3 py-2.5 rounded-md text-sm transition-all duration-[180ms]",
                active
                  ? "font-semibold text-white border-l-[3px]"
                  : destaque
                  ? "hover:translate-x-0.5"
                  : "hover:translate-x-0.5"
              )}
              style={
                active
                  ? {
                      background: "linear-gradient(90deg, rgba(46,117,182,.45) 0%, rgba(46,117,182,.08) 100%)",
                      borderLeftColor: "var(--color-accent-vivid, #3B9EE8)",
                    }
                  : destaque
                  ? { color: "rgba(255,255,255,.70)" }
                  : { color: "rgba(255,255,255,.45)" }
              }
              onMouseEnter={(e) => {
                if (!active) {
                  (e.currentTarget as HTMLElement).style.color = "rgba(255,255,255,.92)";
                  (e.currentTarget as HTMLElement).style.background = "rgba(255,255,255,.07)";
                }
              }}
              onMouseLeave={(e) => {
                if (!active) {
                  (e.currentTarget as HTMLElement).style.color = destaque
                    ? "rgba(255,255,255,.70)"
                    : "rgba(255,255,255,.45)";
                  (e.currentTarget as HTMLElement).style.background = "";
                }
              }}
            >
              <Icon size={destaque ? 16 : 14} />
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Rodapé */}
      <div className="p-4 space-y-3" style={{ borderTop: "1px solid rgba(255,255,255,.12)" }}>
        <div className="flex items-center gap-2 text-xs" style={{ color: "rgba(255,255,255,.55)" }}>
          <CheckCircle size={12} className="text-emerald-400" />
          Sistema operacional
        </div>

        {/* Trial banner — visível apenas durante o período de trial */}
        {user?.trial_ends_at && (!user.subscription_status || user.subscription_status === "trial") && (() => {
          const dias = diasRestantes(user.trial_ends_at!);
          const msg = dias === 0
            ? "Seu trial encerra hoje."
            : dias === 1
            ? "Último dia de trial."
            : `${dias} dias de trial restantes.`;
          return (
            <Link
              href="/assinar"
              className="block rounded-lg px-3 py-2.5 text-center transition-opacity hover:opacity-90 cursor-pointer"
              style={{ background: dias <= 2 ? "rgba(220,38,38,.25)" : "rgba(59,158,232,.18)", border: `1px solid ${dias <= 2 ? "rgba(220,38,38,.45)" : "rgba(59,158,232,.35)"}` }}
            >
              <p className="text-[11px] font-medium leading-snug mb-1.5" style={{ color: dias <= 2 ? "#fca5a5" : "rgba(255,255,255,.80)" }}>
                {msg}
              </p>
              <span
                className="inline-block text-[10px] font-semibold px-3 py-1 rounded-full"
                style={{ background: dias <= 2 ? "rgba(220,38,38,.40)" : "rgba(59,158,232,.35)", color: "#fff" }}
              >
                Vamos assinar?!
              </span>
            </Link>
          );
        })()}

        {user && (
          <div className="flex items-center gap-2 min-w-0">
            <div
              className="w-7 h-7 rounded-full flex items-center justify-center text-[10px] font-bold text-white shrink-0"
              style={{ background: "var(--gradient-primary, linear-gradient(135deg,#2E75B6,#1F3864))" }}
            >
              {getInitials(user.nome)}
            </div>
            <div className="text-xs min-w-0">
              <p className="font-medium truncate" style={{ color: "rgba(255,255,255,.90)" }}>{user.nome}</p>
              <p className="truncate" style={{ color: "rgba(255,255,255,.50)" }}>{user.email}</p>
            </div>
          </div>
        )}

        <div className="flex gap-3">
          {user?.perfil === "ADMIN" && (
            <Link
              href="/admin"
              className="text-xs flex items-center gap-1 transition-colors duration-150"
              style={{ color: "rgba(255,255,255,.55)" }}
              onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.color = "rgba(255,255,255,.90)")}
              onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.color = "rgba(255,255,255,.55)")}
            >
              <Settings size={11} />
              Admin
            </Link>
          )}
          <button
            onClick={logout}
            className="text-xs flex items-center gap-1 ml-auto cursor-pointer transition-colors duration-150 hover:text-red-400"
            style={{ color: "rgba(255,255,255,.55)" }}
          >
            <LogOut size={11} />
            Sair
          </button>
        </div>
      </div>
    </aside>
  );
}
