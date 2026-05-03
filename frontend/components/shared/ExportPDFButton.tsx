"use client";
import { useState } from "react";
import { ArrowDownToLine, Loader2, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import api from "@/lib/api";
import axios from "axios";

interface ExportPDFButtonProps {
  sourceType: "analysis" | "dossie";
  sourceId?: string;
  analysisData?: Record<string, unknown>;
  className?: string;
}

export function ExportPDFButton({
  sourceType,
  sourceId,
  analysisData,
  className,
}: ExportPDFButtonProps) {
  const [loading, setLoading] = useState(false);
  const [sucesso, setSucesso] = useState(false);
  const [erro, setErro] = useState(false);

  const handleExport = async () => {
    setLoading(true);
    setErro(false);
    setSucesso(false);
    try {
      const res = await api.post(
        "/v1/export/pdf",
        { source_type: sourceType, source_id: sourceId ?? null, analysis_data: analysisData ?? null },
        { responseType: "blob" }
      );
      const blob = new Blob([res.data], { type: "application/pdf" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      const disposition: string = res.headers["content-disposition"] ?? "";
      const match = disposition.match(/filename=([^\s;]+)/);
      a.download = match ? match[1] : "orbis_documento.pdf";
      a.href = url;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      setSucesso(true);
      setTimeout(() => setSucesso(false), 2500);
    } catch (e: unknown) {
      if (axios.isAxiosError(e) || e) setErro(true);
      setTimeout(() => setErro(false), 4000);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="inline-flex flex-col items-start gap-1">
      <Button
        variant="outline"
        size="default"
        onClick={handleExport}
        disabled={loading}
        className={`border-primary text-primary hover:bg-primary/10 hover:text-primary font-medium gap-2 ${className ?? ""}`}
        title="Baixar como PDF"
      >
        {loading ? (
          <Loader2 size={15} className="animate-spin" />
        ) : sucesso ? (
          <CheckCircle2 size={15} className="text-emerald-500" />
        ) : (
          <ArrowDownToLine size={15} />
        )}
        {loading ? "Gerando…" : sucesso ? "Baixado!" : "Baixar PDF"}
      </Button>
      {erro && (
        <p className="text-xs text-red-600">Não foi possível gerar o PDF. Tente novamente.</p>
      )}
    </div>
  );
}
