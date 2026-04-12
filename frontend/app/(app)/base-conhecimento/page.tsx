"use client";
import { useEffect, useRef, useState } from "react";
import { Upload, Trash2, FileText, CheckCircle, Loader2, AlertCircle, Globe, ExternalLink, X } from "lucide-react";
import { Card } from "@/components/shared/Card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import api from "@/lib/api";

const TIPOS = ["IN", "Resolucao", "Parecer", "Manual", "Outro"];
const EXTENSOES = ".pdf,.docx,.xlsx,.html,.htm,.txt,.md,.csv";

interface NormaRow {
  id: number;
  codigo: string;
  nome: string;
  tipo: string;
  ano: number;
  vigente: boolean;
  created_at: string | null;
  total_chunks: number;
}

type JobStatus = "pending" | "processing" | "done" | "error";

interface MonitorResultado {
  fonte: string;
  tipo: string;
  novos: number;
  encontrados: number;
  erro: string | null;
}

interface DocPendente {
  id: number;
  titulo: string;
  url: string;
  data_publicacao: string | null;
  resumo: string | null;
  fonte: string;
  tipo: string;
  detectado_em: string;
}

export default function BaseConhecimentoPage() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [nome, setNome] = useState("");
  const [tipo, setTipo] = useState("IN");
  const [enviando, setEnviando] = useState(false);
  const [jobStatus, setJobStatus] = useState<JobStatus | null>(null);
  const [jobMsg, setJobMsg] = useState("");
  const [normas, setNormas] = useState<NormaRow[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [removendo, setRemovendo] = useState<number | null>(null);
  const [erroRemover, setErroRemover] = useState<string | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Monitor de fontes
  const [verificando, setVerificando] = useState(false);
  const [monitorResultados, setMonitorResultados] = useState<MonitorResultado[] | null>(null);
  const [docsPendentes, setDocsPendentes] = useState<DocPendente[]>([]);
  const [descartando, setDescartando] = useState<number | null>(null);

  const carregarNormas = async () => {
    try {
      const res = await api.get<NormaRow[]>("/v1/ingest/normas");
      setNormas(res.data);
    } finally {
      setCarregando(false);
    }
  };

  const carregarPendentes = async () => {
    try {
      const res = await api.get<{ documentos: DocPendente[] }>("/v1/monitor/pendentes");
      setDocsPendentes(res.data.documentos);
    } catch { /* silencioso */ }
  };

  useEffect(() => {
    carregarNormas();
    carregarPendentes();
    return () => { if (pollingRef.current) clearInterval(pollingRef.current); };
  }, []);

  const verificarFontes = async () => {
    setVerificando(true);
    setMonitorResultados(null);
    try {
      const res = await api.post<{ resultados: MonitorResultado[] }>("/v1/monitor/verificar");
      setMonitorResultados(res.data.resultados);
      await carregarPendentes();
    } catch {
      setMonitorResultados([]);
    } finally {
      setVerificando(false);
    }
  };

  const descartarDoc = async (id: number) => {
    setDescartando(id);
    try {
      await api.patch(`/v1/monitor/documentos/${id}`, { status: "descartado" });
      setDocsPendentes((prev) => prev.filter((d) => d.id !== id));
    } finally {
      setDescartando(null);
    }
  };

  const handleArquivo = (file: File) => {
    setArquivo(file);
    if (!nome) setNome(file.name.replace(/\.[^.]+$/, ""));
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) handleArquivo(file);
  };

  const iniciarPolling = (jobId: string) => {
    pollingRef.current = setInterval(async () => {
      try {
        const res = await api.get<{ status: JobStatus; message: string }>(`/v1/ingest/jobs/${jobId}`);
        setJobStatus(res.data.status);
        setJobMsg(res.data.message);
        if (res.data.status === "done" || res.data.status === "error") {
          clearInterval(pollingRef.current!);
          pollingRef.current = null;
          setEnviando(false);
          if (res.data.status === "done") {
            setArquivo(null);
            setNome("");
            setTipo("IN");
            if (fileInputRef.current) fileInputRef.current.value = "";
            carregarNormas();
          }
        }
      } catch {
        clearInterval(pollingRef.current!);
        pollingRef.current = null;
        setEnviando(false);
        setJobStatus("error");
        setJobMsg("Erro ao verificar status do processamento.");
      }
    }, 2000);
  };

  const enviar = async () => {
    if (!arquivo || !nome.trim()) return;
    setEnviando(true);
    setJobStatus("pending");
    setJobMsg("");

    const form = new FormData();
    form.append("file", arquivo);
    form.append("nome", nome.trim());
    form.append("tipo", tipo);

    try {
      const res = await api.post<{ job_id: string; status: JobStatus }>("/v1/ingest/upload", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setJobStatus(res.data.status);
      iniciarPolling(res.data.job_id);
    } catch (e: unknown) {
      setEnviando(false);
      setJobStatus("error");
      const msg =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        "Erro ao enviar o arquivo.";
      setJobMsg(msg);
    }
  };

  const remover = async (id: number) => {
    if (!confirm("Remover esta norma e todos os seus trechos da base?")) return;
    setRemovendo(id);
    setErroRemover(null);
    try {
      await api.delete(`/v1/ingest/normas/${id}`);
      setNormas((prev) => prev.filter((n) => n.id !== id));
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setErroRemover(detail ?? "Erro ao remover. Tente novamente.");
    } finally {
      setRemovendo(null);
    }
  };

  const statusColor: Record<JobStatus, string> = {
    pending: "text-muted-foreground",
    processing: "text-amber-600",
    done: "text-emerald-600",
    error: "text-red-600",
  };

  const statusLabel: Record<JobStatus, string> = {
    pending: "Aguardando processamento…",
    processing: "Processando…",
    done: "Documento incluído com sucesso.",
    error: jobMsg || "Erro no processamento.",
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold">Adicionar Norma</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Adicione INs, Resoluções, Pareceres ou Manuais à base de conhecimento.
        </p>
      </div>

      {/* Upload */}
      <Card>
        {/* Drop zone */}
        <div
          className="border-2 border-dashed border-border rounded-md p-8 text-center cursor-pointer hover:border-primary/50 transition-colors"
          onDragOver={(e) => e.preventDefault()}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
        >
          <Upload size={28} className="mx-auto mb-2 text-muted-foreground" />
          {arquivo ? (
            <p className="text-sm font-medium text-foreground">{arquivo.name}</p>
          ) : (
            <>
              <p className="text-sm font-medium">Arraste o arquivo aqui ou clique para selecionar</p>
              <p className="text-xs text-muted-foreground mt-1">
                Máx. 50 MB · PDF, DOCX, XLSX, HTML, TXT, MD, CSV
              </p>
            </>
          )}
          <input
            ref={fileInputRef}
            type="file"
            accept={EXTENSOES}
            className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) handleArquivo(f); }}
          />
        </div>

        {/* Campos */}
        <div className="mt-4 grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div className="sm:col-span-2 space-y-1">
            <label className="text-xs font-medium text-muted-foreground">Nome do documento</label>
            <Input
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              placeholder="Ex: IN RFB 2184/2024"
              className="text-sm"
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">Tipo</label>
            <select
              value={tipo}
              onChange={(e) => setTipo(e.target.value)}
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
            >
              {TIPOS.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
        </div>

        {/* Status do job */}
        {jobStatus && (
          <div className={`flex items-center gap-2 mt-4 text-sm ${statusColor[jobStatus]}`}>
            {jobStatus === "processing" || jobStatus === "pending" ? (
              <Loader2 size={14} className="animate-spin" />
            ) : jobStatus === "done" ? (
              <CheckCircle size={14} />
            ) : (
              <AlertCircle size={14} />
            )}
            {statusLabel[jobStatus]}
          </div>
        )}

        <div className="mt-4 flex justify-end">
          <Button
            onClick={enviar}
            disabled={enviando || !arquivo || !nome.trim()}
            className="bg-primary hover:bg-primary/90 text-primary-foreground gap-2"
          >
            {enviando ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
            {enviando ? "Processando…" : "Incluir na base"}
          </Button>
        </div>
      </Card>

      {/* Monitor de Fontes Oficiais */}
      <div className="border-t border-border pt-6">
        <div className="flex items-start justify-between gap-4 mb-4">
          <div>
            <h2 className="text-base font-semibold flex items-center gap-2">
              <Globe size={16} className="text-primary" />
              Monitor de Fontes Oficiais
            </h2>
            <p className="text-sm text-muted-foreground mt-1">
              Verifica DOU, Planalto, CGIBS, Portal NF-e e Receita Federal em busca de novos documentos sobre a Reforma Tributária.
            </p>
          </div>
          <Button
            onClick={verificarFontes}
            disabled={verificando}
            variant="outline"
            className="shrink-0 gap-2"
          >
            {verificando ? <Loader2 size={14} className="animate-spin" /> : <Globe size={14} />}
            {verificando ? "Verificando…" : "Verificar agora"}
          </Button>
        </div>

        {/* Resultado da varredura */}
        {monitorResultados !== null && (
          <div className="mb-4 space-y-2">
            {monitorResultados.length === 0 ? (
              <p className="text-sm text-muted-foreground">Nenhum resultado retornado.</p>
            ) : (
              monitorResultados.map((r, i) => (
                <div key={i} className="flex items-center gap-3 text-sm py-2 px-3 rounded-md bg-muted/50">
                  <span className="font-medium flex-1 truncate">{r.fonte}</span>
                  <span className="text-xs text-muted-foreground">{r.tipo}</span>
                  {r.erro ? (
                    <span className="text-xs text-red-500 flex items-center gap-1">
                      <AlertCircle size={11} /> Erro
                    </span>
                  ) : (
                    <span className={`text-xs font-medium ${r.novos > 0 ? "text-emerald-600" : "text-muted-foreground"}`}>
                      {r.novos > 0 ? `+${r.novos} novos` : "Sem novidades"}
                    </span>
                  )}
                </div>
              ))
            )}
          </div>
        )}

        {/* Documentos pendentes de revisão */}
        {docsPendentes.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold mb-2 text-amber-700">
              {docsPendentes.length} documento{docsPendentes.length > 1 ? "s" : ""} aguardando revisão
            </h3>
            <div className="space-y-2">
              {docsPendentes.map((d) => (
                <Card key={d.id} acento="muted">
                  <div className="flex items-start gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-medium truncate">{d.titulo}</span>
                        <span className="text-xs text-muted-foreground bg-muted px-1.5 py-0.5 rounded">{d.tipo}</span>
                        <span className="text-xs text-muted-foreground">{d.fonte}</span>
                      </div>
                      {d.resumo && (
                        <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{d.resumo}</p>
                      )}
                      <div className="flex items-center gap-3 mt-2">
                        <a
                          href={d.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs text-primary hover:underline flex items-center gap-1"
                        >
                          <ExternalLink size={11} /> Ver documento
                        </a>
                        {d.data_publicacao && (
                          <span className="text-xs text-muted-foreground">
                            {new Date(d.data_publicacao).toLocaleDateString("pt-BR")}
                          </span>
                        )}
                      </div>
                    </div>
                    <button
                      onClick={() => descartarDoc(d.id)}
                      disabled={descartando === d.id}
                      title="Descartar"
                      className="text-muted-foreground hover:text-red-500 p-1 shrink-0 cursor-pointer"
                    >
                      {descartando === d.id ? <Loader2 size={14} className="animate-spin" /> : <X size={14} />}
                    </button>
                  </div>
                </Card>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Lista de normas */}
      <div>
        <h2 className="text-base font-semibold mb-3">Documentos na base de conhecimento</h2>
        {erroRemover && (
          <div className="flex items-center gap-2 mb-3 text-sm text-red-600 bg-red-50 border border-red-200 rounded-md px-3 py-2">
            <AlertCircle size={14} />
            {erroRemover}
          </div>
        )}
        {carregando ? (
          <p className="text-sm text-muted-foreground">Carregando…</p>
        ) : normas.length === 0 ? (
          <Card>
            <p className="text-sm text-muted-foreground text-center py-4">
              Nenhum documento na base ainda.
            </p>
          </Card>
        ) : (
          <div className="space-y-2">
            {normas.map((n) => (
              <Card key={n.id} acento="muted">
                <div className="flex items-center gap-3">
                  <FileText size={16} className="text-muted-foreground shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-medium truncate">{n.nome}</span>
                      <span className="text-xs text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
                        {n.tipo}
                      </span>
                      {!n.vigente && (
                        <span className="text-xs text-red-600 bg-red-50 border border-red-200 px-1.5 py-0.5 rounded">
                          Revogada
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {n.total_chunks} trechos ·{" "}
                      {n.created_at
                        ? new Date(n.created_at).toLocaleDateString("pt-BR")
                        : "—"}
                    </p>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => remover(n.id)}
                    disabled={removendo === n.id}
                    className="text-muted-foreground hover:text-red-600 hover:bg-red-50 shrink-0"
                  >
                    {removendo === n.id ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : (
                      <Trash2 size={14} />
                    )}
                    <span className="ml-1 text-xs">Remover</span>
                  </Button>
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
