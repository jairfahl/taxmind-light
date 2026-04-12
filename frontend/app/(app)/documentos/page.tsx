"use client";
import { useEffect, useState, useMemo } from "react";
import { FolderOpen, Lock, X, ChevronRight, Search } from "lucide-react";
import { Card } from "@/components/shared/Card";
import api from "@/lib/api";

const CLASSES: Record<string, { emoji: string; label: string }> = {
  alerta:                  { emoji: "🔔", label: "Alerta" },
  nota_trabalho:           { emoji: "📝", label: "Nota de Trabalho" },
  recomendacao_formal:     { emoji: "📋", label: "Recomendação Formal" },
  dossie_decisao:          { emoji: "📁", label: "Dossiê de Decisão" },
  material_compartilhavel: { emoji: "📤", label: "Material Compartilhável" },
};

const LEGAL_HOLD_CLASSES = new Set(["dossie_decisao", "recomendacao_formal", "material_compartilhavel"]);

interface CaseRow {
  case_id: number;
  titulo: string;
  status: string;
  passo_atual: number;
  created_at: string;
}

interface OutputRow {
  id: number;
  case_id: number;
  classe: string;
  titulo: string;
  conteudo: string | Record<string, unknown> | null;
  materialidade?: number;
  disclaimer?: string;
  created_at: string;
  stakeholder_views?: { stakeholder: string; resumo: string }[];
}

interface DocumentoView extends OutputRow {
  case_titulo: string;
}

function extrairTexto(conteudo: OutputRow["conteudo"]): string {
  if (!conteudo) return "";
  if (typeof conteudo === "string") return conteudo;
  return Object.values(conteudo as Record<string, unknown>)
    .filter((v) => typeof v === "string")
    .join("\n\n");
}

function extrairPreview(conteudo: OutputRow["conteudo"], titulo: string): string {
  const txt = extrairTexto(conteudo);
  return (
    txt.split("\n").map((l) => l.replace(/^#+\s*/, "").trim()).find((l) => l.length > 0) ?? titulo
  );
}

/* ── Modal de detalhes ─────────────────────────────────────────── */
function DocumentoModal({ doc, onClose }: { doc: DocumentoView; onClose: () => void }) {
  const cls = CLASSES[doc.classe] ?? { emoji: "📄", label: doc.classe };
  const legalHold = LEGAL_HOLD_CLASSES.has(doc.classe);
  const data = new Date(doc.created_at).toLocaleDateString("pt-BR", {
    day: "2-digit", month: "long", year: "numeric",
  });
  const textoCompleto = extrairTexto(doc.conteudo);

  /* Fechar com Escape */
  useEffect(() => {
    const fn = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", fn);
    return () => window.removeEventListener("keydown", fn);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 p-4 overflow-y-auto"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="bg-background rounded-xl shadow-2xl w-full max-w-2xl my-8 flex flex-col">
        {/* Cabeçalho */}
        <div className="flex items-start gap-3 p-5 border-b border-border">
          <span className="text-2xl mt-0.5">{cls.emoji}</span>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs font-medium text-muted-foreground">{cls.label}</span>
              <span className="text-xs text-muted-foreground">· {data}</span>
              {legalHold && (
                <span className="inline-flex items-center gap-1 text-xs text-blue-700 bg-blue-50 border border-blue-200 px-2 py-0.5 rounded-full">
                  <Lock size={9} />Legal Hold
                </span>
              )}
              {doc.classe === "dossie_decisao" && (
                <span className="text-xs text-purple-700 bg-purple-50 border border-purple-200 px-2 py-0.5 rounded-full">
                  🧠 Memória de Decisão
                </span>
              )}
            </div>
            <p className="text-base font-semibold text-foreground mt-1">{doc.titulo}</p>
            <p className="text-xs text-muted-foreground/70 mt-0.5">Caso: {doc.case_titulo}</p>
          </div>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground p-1 shrink-0 cursor-pointer"
          >
            <X size={18} />
          </button>
        </div>

        {/* Corpo */}
        <div className="p-5 space-y-5 overflow-y-auto max-h-[70vh]">
          {textoCompleto ? (
            <div>
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                Conteúdo
              </p>
              <p className="text-sm leading-relaxed whitespace-pre-wrap text-foreground">
                {textoCompleto}
              </p>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground italic">Conteúdo não disponível.</p>
          )}

          {/* Stakeholders */}
          {doc.stakeholder_views && doc.stakeholder_views.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                Visões por Área
              </p>
              <div className="space-y-3">
                {doc.stakeholder_views.map((sv, i) => (
                  <div key={i} className="bg-muted/50 rounded-md p-3">
                    <p className="text-xs font-semibold text-muted-foreground mb-1">{sv.stakeholder}</p>
                    <p className="text-sm leading-relaxed whitespace-pre-wrap text-foreground">{sv.resumo}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Materialidade */}
          {doc.materialidade != null && (
            <div className="flex items-center gap-2 text-sm">
              <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Materialidade:</span>
              <span className="font-medium">{doc.materialidade}/5</span>
            </div>
          )}

          {/* Disclaimer */}
          {doc.disclaimer && (
            <div className="bg-amber-50 border border-amber-200 rounded-md p-3">
              <p className="text-xs text-amber-700">{doc.disclaimer}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ── Página principal ──────────────────────────────────────────── */
export default function DocumentosPage() {
  const [documentos, setDocumentos] = useState<DocumentoView[]>([]);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState("");
  const [selecionado, setSelecionado] = useState<DocumentoView | null>(null);
  const [busca, setBusca] = useState("");

  useEffect(() => {
    async function carregar() {
      try {
        const casesRes = await api.get<CaseRow[]>("/v1/cases");
        const cases = casesRes.data;

        if (cases.length === 0) { setDocumentos([]); return; }

        const outputsPerCase = await Promise.all(
          cases.map((c) =>
            api
              .get<OutputRow[]>(`/v1/cases/${c.case_id}/outputs`)
              .then((r) => r.data.map((o) => ({ ...o, case_titulo: c.titulo })))
              .catch(() => [] as DocumentoView[])
          )
        );

        const flat = outputsPerCase
          .flat()
          .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());

        setDocumentos(flat);
      } catch {
        setErro("Erro ao carregar documentos.");
      } finally {
        setLoading(false);
      }
    }
    carregar();
  }, []);

  const documentosFiltrados = useMemo(() => {
    if (!busca.trim()) return documentos;
    const q = busca.toLowerCase();
    return documentos.filter(
      (d) =>
        d.titulo?.toLowerCase().includes(q) ||
        d.case_titulo?.toLowerCase().includes(q) ||
        CLASSES[d.classe]?.label.toLowerCase().includes(q) ||
        extrairTexto(d.conteudo).toLowerCase().includes(q)
    );
  }, [documentos, busca]);

  if (loading)
    return <p className="text-sm text-muted-foreground">Carregando…</p>;

  return (
    <>
      {selecionado && (
        <DocumentoModal doc={selecionado} onClose={() => setSelecionado(null)} />
      )}

      <div className="space-y-5">
        <div>
          <h1 className="text-2xl font-semibold">Documentos</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Histórico de análises. Dossiês de Decisão são imutáveis com Legal Hold ativo.
          </p>
        </div>

        {/* Filtro de busca */}
        {documentos.length > 0 && (
          <div className="relative">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground/60" />
            <input
              type="text"
              placeholder="Buscar por título, tipo ou conteúdo…"
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              className="w-full pl-9 pr-4 py-2 text-sm border border-border rounded-lg bg-background focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
        )}

        {erro && <p className="text-sm text-red-600">{erro}</p>}

        {documentosFiltrados.length === 0 && !erro ? (
          <div className="text-center py-16 text-muted-foreground">
            <FolderOpen size={36} className="mx-auto mb-3 opacity-40" />
            <p className="text-sm">Nenhum documento ainda.</p>
            <p className="text-xs mt-1">
              Complete o protocolo P1→P6 para gerar o primeiro dossiê.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {documentosFiltrados.map((d) => {
              const cls = CLASSES[d.classe] ?? { emoji: "📄", label: d.classe };
              const legalHold = LEGAL_HOLD_CLASSES.has(d.classe);
              const data = new Date(d.created_at).toLocaleDateString("pt-BR");
              const preview = extrairPreview(d.conteudo, d.titulo);

              return (
                <button
                  key={d.id}
                  onClick={() => setSelecionado(d)}
                  className="w-full text-left cursor-pointer group"
                >
                  <Card acento={legalHold ? "primary" : "muted"}>
                    <div className="flex items-start gap-3">
                      <span className="text-lg mt-0.5">{cls.emoji}</span>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-sm font-medium">{cls.label}</span>
                          <span className="text-xs text-muted-foreground">· {data}</span>
                          {legalHold && (
                            <span className="inline-flex items-center gap-1 text-xs text-blue-700 bg-blue-50 border border-blue-200 px-2 py-0.5 rounded-full">
                              <Lock size={9} />Legal Hold
                            </span>
                          )}
                          {d.classe === "dossie_decisao" && (
                            <span className="text-xs text-purple-700 bg-purple-50 border border-purple-200 px-2 py-0.5 rounded-full">
                              🧠 Memória de Decisão
                            </span>
                          )}
                        </div>

                        {d.titulo && (
                          <p className="text-sm font-medium text-foreground mt-1.5 line-clamp-1">
                            {d.titulo}
                          </p>
                        )}

                        {preview && preview !== d.titulo && (
                          <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
                            {preview}
                          </p>
                        )}

                        <p className="text-xs text-muted-foreground/60 mt-1">
                          Caso: {d.case_titulo}
                        </p>
                      </div>
                      <ChevronRight
                        size={15}
                        className="text-muted-foreground/40 group-hover:text-muted-foreground mt-1 shrink-0 transition-colors"
                      />
                    </div>
                  </Card>
                </button>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}
