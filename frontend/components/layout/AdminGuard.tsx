"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/store/auth";

export function AdminGuard({ children }: { children: React.ReactNode }) {
  const { user, isAuthenticated } = useAuthStore();
  const router = useRouter();

  useEffect(() => {
    if (!isAuthenticated || user?.perfil !== "ADMIN") {
      router.push("/analisar");
    }
  }, [isAuthenticated, user, router]);

  if (!isAuthenticated || user?.perfil !== "ADMIN") return null;
  return <>{children}</>;
}
