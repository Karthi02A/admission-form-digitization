"use client";

import { useEffect, useRef, useState } from "react";
import Image from "next/image";

type Props = { sourceUrl: string; filename: string };
type PdfPageProxy = {
  getViewport: (options: { scale: number }) => { width: number; height: number };
  render: (options: { canvas?: HTMLCanvasElement; canvasContext: CanvasRenderingContext2D; viewport: { width: number; height: number } }) => { promise: Promise<void>; cancel?: () => void };
};
type PdfDocument = {
  numPages: number;
  getPage: (page: number) => Promise<PdfPageProxy>;
};

function PdfPage({ pdf, pageNumber, availableWidth, zoom }: {
  pdf: PdfDocument; pageNumber: number; availableWidth: number; zoom: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const renderToken = useRef(0);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const token = ++renderToken.current;
    let renderTask: { cancel?: () => void } | undefined;

    async function render() {
      try {
        const page = await pdf.getPage(pageNumber);
        if (cancelled || token !== renderToken.current || !canvasRef.current) return;
        const base = page.getViewport({ scale: 1 });
        const fitScale = Math.min(Math.max(220, availableWidth - 24) / base.width, 1.8);
        const viewport = page.getViewport({ scale: fitScale * zoom });
        const canvas = canvasRef.current;
        const ratio = window.devicePixelRatio || 1;
        canvas.width = Math.floor(viewport.width * ratio);
        canvas.height = Math.floor(viewport.height * ratio);
        canvas.style.width = `${viewport.width}px`;
        canvas.style.height = `${viewport.height}px`;
        const context = canvas.getContext("2d");
        if (!context) throw new Error("Canvas is unavailable");
        context.setTransform(ratio, 0, 0, ratio, 0, 0);
        renderTask = page.render({ canvas, canvasContext: context, viewport });
        await (renderTask as { promise: Promise<void> }).promise;
        if (!cancelled) setError(false);
      } catch {
        if (!cancelled) setError(true);
      }
    }
    void render();
    return () => {
      cancelled = true;
      renderTask?.cancel?.();
    };
  }, [pdf, pageNumber, availableWidth, zoom]);

  return (
    <article className="w-full rounded-xl border border-line bg-white p-2 shadow-sm sm:p-3">
      <div className="mb-2 flex items-center justify-between px-1">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted">Page {pageNumber}</span>
      </div>
      {error ? (
        <p role="alert" className="p-6 text-center text-sm text-red-700">This page could not be rendered.</p>
      ) : (
        <div className="flex justify-center overflow-x-auto">
          <canvas ref={canvasRef} aria-label={`Page ${pageNumber}`} className="h-auto max-w-none" />
        </div>
      )}
    </article>
  );
}

export default function DocumentViewer({ sourceUrl, filename }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [pdf, setPdf] = useState<PdfDocument | null>(null);
  const [availableWidth, setAvailableWidth] = useState(640);
  const [zoom, setZoom] = useState(1);
  const [error, setError] = useState("");
  const isPdf = filename.toLowerCase().endsWith(".pdf");

  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;
    const update = () => setAvailableWidth(element.clientWidth || 640);
    update();
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    let cancelled = false;
    setError("");
    setPdf(null);
    setZoom(1);
    if (!isPdf) return;

    import("pdfjs-dist").then(async pdfjs => {
      if (cancelled) return;
      pdfjs.GlobalWorkerOptions.workerSrc = "/pdf-worker.min.mjs";
      const loaded = await pdfjs.getDocument({ url: sourceUrl }).promise;
      if (!cancelled) setPdf(loaded as unknown as PdfDocument);
    }).catch(() => {
      if (!cancelled) setError("The original PDF could not be displayed. You can still download it from the API.");
    });
    return () => { cancelled = true; };
  }, [isPdf, sourceUrl]);

  return (
    <section className="flex min-h-0 min-w-0 flex-none flex-col">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-3 py-3 sm:px-4">
        <div className="min-w-0 flex-1">
          <h2 className="text-sm font-semibold text-slate-800">Original document</h2>
          <p className="mt-0.5 break-all text-xs text-muted" title={filename}>{filename}</p>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <button type="button" onClick={() => setZoom(value => Math.max(0.6, +(value - 0.1).toFixed(2)))} aria-label="Zoom out" className="grid h-9 w-9 place-items-center rounded-lg border border-line text-base hover:bg-slate-50">−</button>
          <span className="min-w-12 text-center text-xs tabular-nums text-muted">{Math.round(zoom * 100)}%</span>
          <button type="button" onClick={() => setZoom(value => Math.min(1.8, +(value + 0.1).toFixed(2)))} aria-label="Zoom in" className="grid h-9 w-9 place-items-center rounded-lg border border-line text-base hover:bg-slate-50">+</button>
          <button type="button" onClick={() => setZoom(1)} className="min-h-9 rounded-lg border border-line px-3 text-xs font-medium hover:bg-slate-50">Fit</button>
        </div>
      </div>
      <div ref={containerRef} className="flex min-h-[360px] min-w-0 flex-col gap-4 overflow-visible bg-slate-100 p-3 sm:p-4">
        {error ? (
          <p role="alert" className="m-auto max-w-sm text-center text-sm text-red-700">{error}</p>
        ) : isPdf ? (
          pdf ? Array.from({ length: pdf.numPages }, (_, index) => (
            <PdfPage key={`${sourceUrl}-${index + 1}`} pdf={pdf} pageNumber={index + 1} availableWidth={availableWidth} zoom={zoom} />
          )) : <p className="m-auto text-sm text-muted">Loading original PDF…</p>
        ) : (
          <div className="flex min-h-full justify-center">
            <Image
              src={sourceUrl}
              alt={`Original document ${filename}`}
              width={1600}
              height={2200}
              unoptimized
              onError={() => setError("The original image could not be displayed.")}
              style={{ width: `${Math.min(100, zoom * 100)}%`, height: "auto", objectFit: "contain", alignSelf: "flex-start" }}
              className="shadow-sm"
            />
          </div>
        )}
      </div>
    </section>
  );
}
