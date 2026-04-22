import { create } from "zustand";
import type { ResultadoAnalise } from "@/types";

interface ProtocoloState {
  // Controle
  stepAtual: number;
  caseId: string | null;
  interactionId: string | null;
  // P1
  query: string;
  metodos: string[];
  topK: number;
  // P2
  premissas: string[];
  riscos: string[];
  // P3
  resultadoIA: ResultadoAnalise | null;
  grauConsolidacao: string;
  contraTese: string;
  criticidade: string;
  // P4
  hipoteseGestor: string;
  // P5
  decisaoFinal: string;
  carimboPct: number | null;
  carimboAlertId: number | null;
  // Actions
  setStep: (n: number) => void;
  set: (patch: Partial<ProtocoloState>) => void;
  reset: () => void;
}

const INITIAL: Omit<ProtocoloState, "setStep" | "set" | "reset"> = {
  stepAtual: 1,
  caseId: null,
  interactionId: null,
  query: "",
  metodos: [],
  topK: 5,
  premissas: [],
  riscos: [],
  resultadoIA: null,
  grauConsolidacao: "",
  contraTese: "",
  criticidade: "",
  hipoteseGestor: "",
  decisaoFinal: "",
  carimboPct: null,
  carimboAlertId: null,
};

export const useProtocoloStore = create<ProtocoloState>((setState) => ({
  ...INITIAL,
  setStep: (stepAtual) => setState((s) => ({ ...s, stepAtual })),
  set: (patch) => setState((s) => ({ ...s, ...patch })),
  reset: () => setState((s) => ({ ...s, ...INITIAL })),
}));
