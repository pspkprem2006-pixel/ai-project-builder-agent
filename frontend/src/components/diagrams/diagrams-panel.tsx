"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Check, ChevronDown, Copy, Download, FileCode2, Loader2, RefreshCw } from "lucide-react";
import { Badge, Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Mermaid } from "@/components/mermaid";
import { DIAGRAM_CATEGORY_LABELS, getDiagramSource, listDiagrams, type DiagramInfo, type DiagramSource } from "@/lib/diagrams";

function downloadBlob(filename: string, blob: Blob) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function downloadText(filename: string, text: string) {
  downloadBlob(filename, new Blob([text], { type: "text/plain;charset=utf-8" }));
}

function serializeSvg(svg: SVGSVGElement): string {
  const clone = svg.cloneNode(true) as SVGSVGElement;
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  return new XMLSerializer().serializeToString(clone);
}

async function downloadPng(svg: SVGSVGElement, filename: string) {
  const width = Number(svg.getAttribute("width")) || 1200;
  const height = Number(svg.getAttribute("height")) || 800;
  const scale = 2;
  const blob = new Blob([serializeSvg(svg)], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const image = new Image();
  await new Promise((resolve, reject) => {
    image.onload = resolve;
    image.onerror = reject;
    image.src = url;
  });
  const canvas = document.createElement("canvas");
  canvas.width = width * scale;
  canvas.height = height * scale;
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    URL.revokeObjectURL(url);
    return;
  }
  ctx.scale(scale, scale);
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, width, height);
  ctx.drawImage(image, 0, 0, width, height);
  URL.revokeObjectURL(url);
  const pngBlob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/png"));
  if (pngBlob) downloadBlob(filename, pngBlob);
}

interface DiagramTileProps {
  info: DiagramInfo;
  expanded: boolean;
  source: DiagramSource | null;
  loading: boolean;
  error: string | null;
  onToggle: () => void;
}

function DiagramTile({ info, expanded, source, loading, error, onToggle }: DiagramTileProps) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [copied, setCopied] = useState(false);
  const [showSource, setShowSource] = useState(false);
  const filename = `blueprint-${info.id}`;

  const handleCopy = useCallback(async () => {
    if (!source) return;
    await navigator.clipboard.writeText(source.source);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [source]);

  const handleExportSvg = useCallback(() => {
    if (svgRef.current) downloadBlob(`${filename}.svg`, new Blob([serializeSvg(svgRef.current)], { type: "image/svg+xml;charset=utf-8" }));
  }, [filename]);

  const handleExportPng = useCallback(() => {
    if (svgRef.current) void downloadPng(svgRef.current, `${filename}.png`);
  }, [filename]);

  const handleExportMmd = useCallback(() => {
    if (source) downloadText(`${filename}.mmd`, source.source);
  }, [filename, source]);

  const handleRendered = useCallback((svg: SVGSVGElement) => {
    svgRef.current = svg;
  }, []);

  return (
    <Card className={expanded ? "shadow-lg" : ""}>
      <CardHeader className="cursor-pointer pb-3" onClick={onToggle}>
        <div className="flex items-start justify-between gap-2">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              {info.label}
              <Badge tone="info">{DIAGRAM_CATEGORY_LABELS[info.category] ?? info.category}</Badge>
            </CardTitle>
            <p className="mt-1 text-xs text-muted-foreground">{info.description}</p>
          </div>
          <ChevronDown className={`h-4 w-4 shrink-0 text-muted-foreground transition-transform ${expanded ? "rotate-180" : ""}`} />
        </div>
      </CardHeader>
      {expanded && (
        <CardContent className="pt-0">
          {loading && (
            <div className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Generating diagram from blueprint…
            </div>
          )}
          {!loading && error && <p className="py-4 text-sm text-destructive">{error}</p>}
          {!loading && !error && source && (
            <>
              <Mermaid
                chart={source.source}
                title={`${source.title} · live from blueprint`}
                onRendered={handleRendered}
              />
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <Button size="sm" variant="outline" onClick={handleExportMmd}>
                  <Download className="h-3.5 w-3.5" /> .mmd
                </Button>
                <Button size="sm" variant="outline" onClick={handleExportSvg}>
                  <Download className="h-3.5 w-3.5" /> .svg
                </Button>
                <Button size="sm" variant="outline" onClick={handleExportPng}>
                  <Download className="h-3.5 w-3.5" /> .png
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setShowSource((v) => !v)}>
                  <FileCode2 className="h-3.5 w-3.5" /> Source
                </Button>
                <Button size="sm" variant="ghost" onClick={handleCopy}>
                  {copied ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />} Copy
                </Button>
              </div>
              {showSource && (
                <pre className="mt-3 max-h-64 overflow-auto rounded-md bg-slate-900 p-3 text-xs leading-relaxed text-slate-100">
                  {source.source}
                </pre>
              )}
            </>
          )}
        </CardContent>
      )}
    </Card>
  );
}

interface DiagramsPanelProps {
  projectId: number;
  blueprintUpdatedAt: string | null;
}

export function DiagramsPanel({ projectId, blueprintUpdatedAt }: DiagramsPanelProps) {
  const [diagrams, setDiagrams] = useState<DiagramInfo[] | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [sources, setSources] = useState<Record<string, DiagramSource>>({});
  const [loading, setLoading] = useState<Record<string, boolean>>({});
  const [errors, setErrors] = useState<Record<string, string | null>>({});
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    listDiagrams(projectId)
      .then(setDiagrams)
      .catch(() => setDiagrams([]));
  }, [projectId]);

  const fetchSource = useCallback(
    async (diagramId: string) => {
      setLoading((prev) => ({ ...prev, [diagramId]: true }));
      setErrors((prev) => ({ ...prev, [diagramId]: null }));
      try {
        const source = await getDiagramSource(projectId, diagramId);
        setSources((prev) => ({ ...prev, [diagramId]: source }));
      } catch {
        setErrors((prev) => ({ ...prev, [diagramId]: "Could not load diagram." }));
      } finally {
        setLoading((prev) => ({ ...prev, [diagramId]: false }));
      }
    },
    [projectId],
  );

  const toggle = useCallback(
    (diagramId: string) => {
      setExpanded((prev) => {
        const next = new Set(prev);
        if (next.has(diagramId)) next.delete(diagramId);
        else next.add(diagramId);
        return next;
      });
      if (!expanded.has(diagramId) && !sources[diagramId]) {
        void fetchSource(diagramId);
      }
    },
    [expanded, sources, fetchSource],
  );

  useEffect(() => {
    if (expanded.size === 0) return;
    setRefreshing(true);
    Promise.all([...expanded].map((id) => fetchSource(id))).finally(() => setRefreshing(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [blueprintUpdatedAt]);

  const refreshAll = useCallback(() => {
    const ids = [...expanded];
    if (ids.length === 0) return;
    setRefreshing(true);
    Promise.all(ids.map((id) => fetchSource(id))).finally(() => setRefreshing(false));
  }, [expanded, fetchSource]);

  if (!diagrams || diagrams.length === 0) return null;

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2 text-lg">
              Diagrams
              <Badge tone="success">synchronized with blueprint</Badge>
            </CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">
              Generated live from the current blueprint — expand a diagram to preview, export it as Mermaid source, SVG or PNG.
            </p>
          </div>
          {expanded.size > 0 && (
            <Button variant="outline" size="sm" onClick={refreshAll} loading={refreshing}>
              {refreshing ? null : <RefreshCw className="h-3.5 w-3.5" />} Refresh
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {diagrams.map((info) => (
            <DiagramTile
              key={info.id}
              info={info}
              expanded={expanded.has(info.id)}
              source={sources[info.id] ?? null}
              loading={Boolean(loading[info.id])}
              error={errors[info.id] ?? null}
              onToggle={() => toggle(info.id)}
            />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
