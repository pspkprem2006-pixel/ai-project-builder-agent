/**
 * Security regression tests for the Mermaid renderer.
 *
 * Mermaid diagram source is AI-generated, persisted and rendered for every
 * viewer, so it must be treated as untrusted input:
 *  1. Mermaid runs in `securityLevel: "strict"`.
 *  2. Suspicious sources (script / event handlers / javascript:) are refused
 *     before rendering.
 *  3. The rendered SVG is sanitized with DOMPurify (svg profile) before it is
 *     assigned to the DOM; foreignObject payloads are dropped.
 *
 * Executable content must never reach the DOM.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { isSuspiciousDiagramSource, Mermaid, sanitizeSvg } from "./mermaid";

const actEnvironment = globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean };

const mermaidMock = vi.hoisted(() => ({
  initialize: vi.fn(),
  render: vi.fn(),
}));

vi.mock("mermaid", () => ({ default: mermaidMock }));

const SAFE_SOURCE = "graph TD\n    A[User] --> B[API]\n    B --> C[Database]";
const BENIGN_SVG = `<svg xmlns="http://www.w3.org/2000/svg" width="100"><g><rect x="0" y="0" width="50" height="30"/><text x="5" y="20">A</text></g></svg>`;

describe("isSuspiciousDiagramSource", () => {
  it("accepts a normal diagram", () => {
    expect(isSuspiciousDiagramSource(SAFE_SOURCE)).toBe(false);
    expect(isSuspiciousDiagramSource("graph TD\nA --> B")).toBe(false);
  });

  it("rejects <script> content", () => {
    expect(isSuspiciousDiagramSource("<script>alert(1)</script>")).toBe(true);
    expect(isSuspiciousDiagramSource("graph TD\nA --> B\n<script>alert(1)</script>")).toBe(true);
  });

  it("rejects event handler attributes", () => {
    expect(isSuspiciousDiagramSource("graph TD\nA --> B\n<img src=x onerror=alert(1)>")).toBe(true);
    expect(isSuspiciousDiagramSource("<svg onload=alert(1)>")).toBe(true);
    expect(isSuspiciousDiagramSource('A["<div onclick=\\"alert(1)\\">"] --> B')).toBe(true);
  });

  it("rejects javascript: URLs", () => {
    expect(isSuspiciousDiagramSource("javascript:alert(1)")).toBe(true);
    expect(isSuspiciousDiagramSource("A --> B\nclick A javascript:alert(1)")).toBe(true);
  });

  it("does not reject benign labels containing similar words", () => {
    expect(isSuspiciousDiagramSource('graph TD\nA["Configuration"] --> B["Loading"]')).toBe(false);
    expect(isSuspiciousDiagramSource("graph TD\nA[onboarding] --> B[download]")).toBe(false);
  });
});

describe("sanitizeSvg", () => {
  it("passes through a benign SVG", () => {
    const clean = sanitizeSvg(BENIGN_SVG);
    expect(clean).toContain("<svg");
    expect(clean).toContain("<g>");
  });

  it("removes <script> elements", () => {
    const clean = sanitizeSvg(`${BENIGN_SVG}<script>alert(1)</script><script src="https://evil.example/x.js"></script>`);
    expect(clean).not.toContain("<script");
    expect(clean).not.toContain("alert(");
  });

  it("removes event handler attributes (onerror/onload/onclick)", () => {
    const malicious = `<svg onload="alert(1)"><img onerror="alert(2)"><circle onclick="alert(3)"/></svg>`;
    const clean = sanitizeSvg(malicious);
    expect(clean).not.toMatch(/on(?:error|load|click)\s*=/i);
  });

  it("removes javascript: URLs", () => {
    const malicious = `<svg xmlns="http://www.w3.org/2000/svg"><a xlink:href="javascript:alert(1)"><text>click</text></a></svg>`;
    const clean = sanitizeSvg(malicious);
    expect(clean.toLowerCase()).not.toContain("javascript:");
  });

  it("drops foreignObject payloads", () => {
    const malicious = `<svg xmlns="http://www.w3.org/2000/svg"><foreignObject><div onclick="alert(1)"><script>alert(2)</script>text</div></foreignObject><text>ok</text></svg>`;
    const clean = sanitizeSvg(malicious);
    expect(clean).not.toMatch(/foreignObject/i);
    expect(clean).not.toContain("<div");
    expect(clean).not.toContain("onclick");
    expect(clean).not.toContain("<script");
  });
});

describe("Mermaid component", () => {
  let container: HTMLDivElement;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    actEnvironment.IS_REACT_ACT_ENVIRONMENT = true;
    mermaidMock.initialize.mockClear();
    mermaidMock.render.mockReset();
    mermaidMock.render.mockResolvedValue({ svg: BENIGN_SVG });
  });

  afterEach(() => {
    document.body.removeChild(container);
    delete actEnvironment.IS_REACT_ACT_ENVIRONMENT;
  });

  async function renderChart(chart: string) {
    const root = createRoot(container);
    await act(async () => {
      root.render(<Mermaid chart={chart} />);
    });
    await act(async () => {});
    return root;
  }

  it("runs mermaid in securityLevel strict", async () => {
    await renderChart(SAFE_SOURCE);
    expect(mermaidMock.initialize).toHaveBeenCalledWith(
      expect.objectContaining({ securityLevel: "strict" }),
    );
  });

  it("renders a legitimate diagram", async () => {
    await renderChart(SAFE_SOURCE);
    expect(mermaidMock.render).toHaveBeenCalledTimes(1);
    expect(mermaidMock.render).toHaveBeenCalledWith(expect.stringMatching(/^mermaid-/), SAFE_SOURCE);
    expect(container.innerHTML).toContain("<svg");
  });

  it("sanitizes the SVG produced by the renderer before inserting it into the DOM", async () => {
    mermaidMock.render.mockResolvedValue({
      svg: `<svg onload="alert(1)"><script>alert(2)</script>${BENIGN_SVG.slice(0, BENIGN_SVG.indexOf(">") + 1)}<g><text>A</text></g></svg>`,
    });
    await renderChart(SAFE_SOURCE);
    const html = container.innerHTML;
    expect(html).toContain("<svg");
    expect(html).not.toMatch(/<script/i);
    expect(html).not.toMatch(/on(?:error|load|click)\s*=/i);
    expect(html.toLowerCase()).not.toContain("javascript:");
  });

  it("refuses to render sources containing executable content", async () => {
    const evil = "<script>alert(1)</script>\ngraph TD\nA --> B";
    await renderChart(evil);
    expect(mermaidMock.render).not.toHaveBeenCalled();
    // The rejected source is shown as escaped text only; no executable markup
    // reaches the DOM.
    expect(container.innerHTML).not.toMatch(/<script/i);
    expect(container.querySelector("script, svg, img, [onload], [onerror], [onclick]")).toBeNull();
  });

  it("refuses sources with event handlers or javascript: URLs", async () => {
    for (const evil of ["graph TD\n<img src=x onerror=alert(1)>", "graph TD\nA --> B\nclick A javascript:alert(1)"]) {
      mermaidMock.render.mockClear();
      await renderChart(evil);
      expect(mermaidMock.render).not.toHaveBeenCalled();
      // The rejected source is only ever shown as escaped text; no executable
      // markup (elements or handler attributes) reaches the DOM.
      expect(container.querySelector("svg, img, script, [onerror], [onload], [onclick]")).toBeNull();
      expect(container.innerHTML).not.toMatch(/<script/i);
    }
  });

  it("does not leave raw executable payloads in the fallback error view", async () => {
    const evil = '<script>alert(1)</script><svg onload="alert(2)">';
    await renderChart(evil);
    const html = container.innerHTML;
    // React escapes the payload (<script> becomes &lt;script&gt;), so it is
    // inert text: no script/svg elements and no handler attributes exist.
    expect(html).not.toMatch(/<script/i);
    expect(html).not.toMatch(/<svg/i);
    expect(container.querySelector("script, svg, [onload], [onerror], [onclick]")).toBeNull();
  });

  it("calls onRendered with the sanitized svg element", async () => {
    const onRendered = vi.fn();
    const root = createRoot(container);
    await act(async () => {
      root.render(<Mermaid chart={SAFE_SOURCE} onRendered={onRendered} />);
    });
    await act(async () => {});
    expect(onRendered).toHaveBeenCalledTimes(1);
    const svg = onRendered.mock.calls[0][0] as SVGSVGElement;
    expect(svg.tagName.toLowerCase()).toBe("svg");
    expect(svg.outerHTML).not.toMatch(/<script/i);
  });

  it("round-trips through DOMPurify without throwing on empty input", () => {
    expect(sanitizeSvg("")).toBe("");
  });
});