"use client";

import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { cn } from "@/lib/utils";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  ChevronDown,
  Search,
  Copy,
  Download,
  Check,
  X,
  Zap,
} from "lucide-react";
import { AIActionsPanel } from "./ai-actions";

type Json = Record<string, unknown>;

interface ModuleProps {
  id: string;
  title: string;
  sectionKey: string;
  data: Json | null;
  renderContent: (data: Json) => React.ReactNode;
  generationStatus?: "pending" | "complete" | "failed";
  onAction?: (actionId: string, sectionKey: string) => void;
  busyAction?: string | null;
  implementedActions?: Set<string>;
  initiallyExpanded?: boolean;
}

const STORAGE_KEY = "blueprint_module_expansion";

function getExpansionState(): Record<string, boolean> {
  if (typeof window === "undefined") return {};
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored ? JSON.parse(stored) : {};
  } catch {
    return {};
  }
}

function setExpansionState(state: Record<string, boolean>) {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // ignore
  }
}

export function Module({
  id,
  title,
  sectionKey,
  data,
  renderContent,
  generationStatus = "complete",
  onAction,
  busyAction = null,
  implementedActions,
  initiallyExpanded = false,
}: ModuleProps) {
  const [expanded, setExpanded] = useState(() => {
    const saved = getExpansionState();
    return saved[id] ?? initiallyExpanded;
  });
  const [searchQuery, setSearchQuery] = useState("");
  const [copied, setCopied] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const saved = getExpansionState();
    setExpansionState({ ...saved, [id]: expanded });
  }, [expanded, id]);

  const toggleExpanded = useCallback(() => {
    setExpanded((prev) => !prev);
  }, []);

  const handleCopy = useCallback(async () => {
    if (!data || !contentRef.current) return;
    try {
      const text = contentRef.current.innerText;
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // fallback
      const textarea = document.createElement("textarea");
      textarea.value = contentRef.current.innerText;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [data]);

  const handleExport = useCallback(() => {
    if (!data) return;
    const json = JSON.stringify(data, null, 2);
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${sectionKey}-${Date.now()}.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }, [data, sectionKey]);

  const filteredData = useMemo(() => {
    if (!searchQuery || !data) return data;
    const query = searchQuery.toLowerCase();
    const searchJson = (obj: Json): boolean => {
      for (const [key, value] of Object.entries(obj)) {
        if (key.toLowerCase().includes(query)) return true;
        if (typeof value === "string" && value.toLowerCase().includes(query)) return true;
        if (Array.isArray(value)) {
          if (value.some((v) => typeof v === "string" && v.toLowerCase().includes(query))) return true;
          if (value.some((v) => typeof v === "object" && v && searchJson(v as Json))) return true;
        }
        if (typeof value === "object" && value && searchJson(value as Json)) return true;
      }
      return false;
    };
    return searchJson(data) ? data : null;
  }, [data, searchQuery]);

  const statusConfig = {
    complete: { tone: "success" as const, label: "Ready", icon: <Check className="h-3 w-3" /> },
    pending: { tone: "warning" as const, label: "Generating...", icon: <Zap className="h-3 w-3 animate-pulse" /> },
    failed: { tone: "danger" as const, label: "Failed", icon: <X className="h-3 w-3" /> },
  };

  const { tone, label, icon } = statusConfig[generationStatus];

  return (
    <Card id={id} className={cn("overflow-hidden transition-all duration-200", expanded ? "shadow-lg" : "")}>
      <CardHeader className="pb-3 cursor-pointer" onClick={toggleExpanded}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <ChevronDown
              className={cn("h-5 w-5 text-muted-foreground transition-transform", expanded && "rotate-180")}
              aria-hidden="true"
            />
            <CardTitle className="text-lg">{title}</CardTitle>
            <Badge tone={tone} className="gap-1">
              {icon} {label}
            </Badge>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="icon"
              onClick={handleCopy}
              disabled={!data}
              title="Copy section content"
            >
              {copied ? <Check className="h-4 w-4 text-emerald-500" /> : <Copy className="h-4 w-4" />}
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={handleExport}
              disabled={!data}
              title="Export section as JSON"
            >
              <Download className="h-4 w-4" />
            </Button>
          </div>
        </div>
        {expanded && (
          <div className="mt-3">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                type="search"
                placeholder="Search within this section..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9 pr-4 py-2 text-sm"
              />
            </div>
          </div>
        )}
      </CardHeader>
      <CardContent className={cn("pt-0 transition-all duration-200", expanded ? "opacity-100" : "opacity-0 h-0")}>
        {expanded && (
          <>
            <AIActionsPanel
              sectionKey={sectionKey as any}
              onAction={onAction}
              busyAction={busyAction}
              implementedActions={implementedActions}
            />
            <div ref={contentRef} className="mt-4">
              {filteredData ? renderContent(filteredData) : (
                <div className="text-center py-8 text-muted-foreground">
                  {searchQuery ? "No matches found" : "No data available"}
                </div>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}