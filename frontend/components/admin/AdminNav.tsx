"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, Users, Mail, BarChart3 } from "lucide-react";
import { cn } from "@/lib/utils";

const TABS = [
  { href: "/admin",          label: "Visão Geral", icon: LayoutDashboard },
  { href: "/admin/usuarios", label: "Usuários",    icon: Users },
  { href: "/admin/mailing",  label: "Mailing",     icon: Mail },
  { href: "/admin/consumo",  label: "Consumo API", icon: BarChart3 },
];

export function AdminNav() {
  const pathname = usePathname();

  return (
    <nav className="flex gap-1 border-b mb-6" style={{ borderColor: "var(--border, #e2e8f0)" }}>
      {TABS.map(({ href, label, icon: Icon }) => {
        const active = pathname === href;
        return (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors duration-150",
              active
                ? "border-blue-600 text-blue-700"
                : "border-transparent text-muted-foreground hover:text-foreground hover:border-slate-300"
            )}
          >
            <Icon size={14} />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
