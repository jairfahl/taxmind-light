"use client";
import { useState } from "react";
import { useProtocoloStore } from "@/store/protocolo";
import { Card } from "@/components/shared/Card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { X, Plus } from "lucide-react";
import api from "@/lib/api";

const MIN = 3;

const EXEMPLOS_PREMISSAS = [
  "Ex.: Empresa enquadrada no Lucro Real desde 2023",
  "Ex.: Operação de venda interestadual com diferencial de alíquota",
  "Ex.: Contribuinte possui créditos de IBS acumulados",
  "Ex.: Regime especial de split payment ativo desde jan/2026",
];

const EXEMPLOS_RISCOS = [
  "Ex.: Risco de autuação por classificação incorreta da operação",
  "Ex.: Possibilidade de dupla tributação IBS/CBS na cadeia",
  "Ex.: Perda de créditos tributários na transição para o IVA dual",
  "Ex.: Glosa de despesas por falta de documentação fiscal",
];

function ListaEditavel({
  items,
  onChange,
  placeholder,
}: {
  items: string[];
  onChange: (items: string[]) => void;
  placeholder: string;
}) {
  const [draft, setDraft] = useState("");

  const add = () => {
    const v = draft.trim();
    if (v && !items.includes(v)) { onChange([...items, v]); setDraft(""); }
  };

  return (
    <div className="space-y-2">
      {items.map((item, i) => (
        <div key={i} className="flex items-center gap-2 text-sm bg-muted rounded px-3 py-1.5">
          <span className="flex-1">{item}</span>
          <button onClick={() => onChange(items.filter((_, j) => j !== i))} className="text-muted-foreground hover:text-red-500 cursor-pointer">
            <X size={12} />
          </button>
        </div>
      ))}
      <div className="flex gap-2">
        <Input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }}
          placeholder={placeholder}
          className="text-sm bg-input border-border"
        />
        <Button variant="outline" size="icon" onClick={add} disabled={!draft.trim()}>
          <Plus size={14} />
        </Button>
      </div>
    </div>
  );
}

export function P2Estruturacao() {
  const { caseId, query, premissas, riscos, set, setStep } = useProtocoloStore();
  const [loading, setLoading] = useState(false);
  const [tentouAvancar, setTentouAvancar] = useState(false);
  const [erro, setErro] = useState("");

  const podeAvancar = premissas.length >= MIN && riscos.length >= MIN;

  const avancar = async () => {
    setTentouAvancar(true);
    if (!podeAvancar) return;
    if (!caseId) { setErro("Caso não encontrado. Volte ao P1."); return; }

    setLoading(true);
    setErro("");
    try {
      // Submeter passo 1 com premissas
      await api.post(`/v1/cases/${caseId}/steps/1`, {
        dados: {
          titulo: query.slice(0, 120),
          descricao: query,
          contexto_fiscal: query,
          premissas,
          periodo_fiscal: new Date().getFullYear().toString(),
        },
        acao: "avancar",
      });
      // Submeter passo 2 com riscos
      await api.post(`/v1/cases/${caseId}/steps/2`, {
        dados: { riscos, dados_qualidade: "Preenchido pelo usuário via protocolo React" },
        acao: "avancar",
      });
      setStep(3);
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setErro(typeof msg === "string" ? msg : "Erro ao salvar estruturação.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card titulo="P2 — Premissas e Riscos">
      <div className="space-y-5">
        {/* Premissas */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Premissas — fatos e condições da sua situação
            </p>
            <span className={`text-xs font-semibold ${premissas.length >= MIN ? "text-emerald-600" : "text-red-500"}`}>
              {premissas.length}/{MIN} mínimo
            </span>
          </div>
          <p className="text-xs text-muted-foreground mb-2">
            Liste fatos concretos: tipo de empresa, regime tributário, operação, legislação aplicável.
          </p>
          <ListaEditavel
            items={premissas}
            onChange={(v) => set({ premissas: v })}
            placeholder={EXEMPLOS_PREMISSAS[premissas.length % EXEMPLOS_PREMISSAS.length]}
          />
          {tentouAvancar && premissas.length < MIN && (
            <p className="text-xs text-red-600 mt-1">Adicione ao menos {MIN} premissas para continuar.</p>
          )}
        </div>

        {/* Riscos */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Riscos — consequências que você quer avaliar
            </p>
            <span className={`text-xs font-semibold ${riscos.length >= MIN ? "text-emerald-600" : "text-red-500"}`}>
              {riscos.length}/{MIN} mínimo
            </span>
          </div>
          <p className="text-xs text-muted-foreground mb-2">
            Descreva riscos tributários ou operacionais: autuação, dupla tributação, perda de crédito, etc.
          </p>
          <ListaEditavel
            items={riscos}
            onChange={(v) => set({ riscos: v })}
            placeholder={EXEMPLOS_RISCOS[riscos.length % EXEMPLOS_RISCOS.length]}
          />
          {tentouAvancar && riscos.length < MIN && (
            <p className="text-xs text-red-600 mt-1">Adicione ao menos {MIN} riscos para continuar.</p>
          )}
        </div>

        {erro && <p className="text-xs text-red-600">{erro}</p>}

        <div className="flex gap-3">
          <Button variant="outline" onClick={() => setStep(1)}>← Anterior</Button>
          <Button
            onClick={avancar}
            disabled={loading}
            className={`flex-1 ${podeAvancar ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"}`}
          >
            {loading ? "Salvando…" : podeAvancar ? "Analisar →" : `Mínimo: ${MIN} premissas + ${MIN} riscos`}
          </Button>
        </div>
      </div>
    </Card>
  );
}
