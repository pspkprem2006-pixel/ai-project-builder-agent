"use client";

import { useEffect, useId, useRef, useState } from "react";
import DOMPurify from "dompurify";
import mermaid from "mermaid";

let initialized = false;

// Mermaid diagrams are treated as UNTRUSTED INPUT: their source comes from
// AI-generated blueprint content that is persisted and rendered for every
// viewer. Executable constructs are refused at the source level...
const EXECUTABLE_SOURCE_PATTERNS = [
  /<script[\s>]/i,
  /\bon(?:error|click|load|mouseover|focus|keydown|submit)\s*=/i,
  /\bjavascript\s*:/i,
];

export function isSuspiciousDiagramSource(chart: string): boolean {
  return EXECUTABLE_SOURCE_PATTERNS.some((pattern) => pattern.test(String(chart ?? "")));
}

// ...and the rendered SVG is sanitized with DOMPurify before it is assigned
// to the DOM (defense in depth: strict Mermaid rendering + output sanitizer).
// foreignObject is additionally dropped because it can smuggle arbitrary
// HTML payloads into an SVG document.
export function sanitizeSvg(svg: string): string {
  const clean = DOMPurify.sanitize(svg, {
    USE_PROFILES: { svg: true, svgFilters: true },
  });
  return clean
    .replace(/<foreignObject[\s\S]*?<\/foreignObject>/gi, "")
    .replace(/<foreignObject[^>]*\/>/gi, "");
}

export function Mermaid({
  chart,
  title,
  onRendered,
}: {
  chart: string;
  title?: string;
  onRendered?: (svg: SVGSVGElement) => void;
}) {
  const id = useId().replace(/:/g, "");
  const ref = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isSuspiciousDiagramSource(chart)) {
      setError("Diagram source contains unsupported executable content and was not rendered.");
      return;
    }
    setError(null);
    if (!initialized) {
      mermaid.initialize({
        startOnLoad: false,
        theme: "default",
        securityLevel: "strict",
        fontFamily: "var(--font-inter), sans-serif",
      });
      initialized = true;
    }
    let cancelled = false;
    mermaid
      .render(`mermaid-${id}`, chart)
      .then(({ svg }) => {
        if (cancelled || !ref.current) return;
        const safeSvg = sanitizeSvg(svg);
        ref.current.innerHTML = safeSvg;
        const rendered = ref.current.querySelector("svg");
        if (rendered) onRendered?.(rendered);
      })
      .catch(() => {
        if (!cancelled) setError("Diagram could not be rendered");
      });
    return () => {
      cancelled = true;
    };
  }, [chart, id, onRendered]);

  if (error) {
    // chart is rendered as escaped text (React), never as markup.
    return <pre className="overflow-x-auto rounded-md bg-slate-100 p-3 text-xs">{chart}</pre>;
  }
  return (
    <div className="rounded-lg border bg-white p-4">
      {title && <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</p>}
      <div ref={ref} className="overflow-x-auto [&_svg]:mx-auto" />
    </div>
  );
}