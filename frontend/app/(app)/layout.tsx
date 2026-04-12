"use client";
import { useState, useEffect } from "react";
import { usePathname } from "next/navigation";
import { Menu } from "lucide-react";
import { Sidebar } from "@/components/layout/Sidebar";
import { AuthGuard } from "@/components/layout/AuthGuard";
import { OnboardingModal } from "@/components/layout/OnboardingModal";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const pathname = usePathname();

  // Fecha sidebar ao navegar (mobile)
  useEffect(() => {
    setSidebarOpen(false);
  }, [pathname]);

  return (
    <AuthGuard>
      <div className="flex h-screen overflow-hidden bg-background">
        {/* Overlay mobile */}
        {sidebarOpen && (
          <div
            className="fixed inset-0 bg-black/50 z-40 md:hidden"
            onClick={() => setSidebarOpen(false)}
            aria-hidden="true"
          />
        )}

        {/* Sidebar — deslizante no mobile, fixo no desktop */}
        <div
          className={[
            "fixed md:relative inset-y-0 left-0 z-50 md:z-auto",
            "transition-transform duration-300 ease-in-out",
            sidebarOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0",
          ].join(" ")}
        >
          <Sidebar />
        </div>

        {/* Conteúdo principal */}
        <main className="flex-1 overflow-y-auto min-w-0">
          {/* Header mobile com hamburguer */}
          <div className="md:hidden flex items-center gap-3 px-4 py-3 border-b border-border bg-card sticky top-0 z-30">
            <button
              onClick={() => setSidebarOpen(true)}
              className="p-1 rounded-md text-muted-foreground hover:text-foreground transition-colors"
              aria-label="Abrir menu"
            >
              <Menu size={20} />
            </button>
            <span className="font-semibold text-sm text-foreground">Tribus-AI</span>
          </div>

          <div className="px-4 md:px-6 py-6 max-w-5xl mx-auto">
            {children}
          </div>
        </main>
      </div>
      <OnboardingModal />
    </AuthGuard>
  );
}
