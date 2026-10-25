"use client";

import { useRef, useState, type DragEvent } from "react";
import type { UploadEntry } from "@/lib/types";

type Props = {
  files: UploadEntry[];
  processing: boolean;
  locked?: boolean;
  notice: string;
  error: boolean;
  progress: string;
  onAdd: (files: FileList | File[]) => void;
  onRemove: (id: string) => void;
  onProcess: () => void;
};

function fileSize(bytes: number): string {
  return bytes < 1024 * 1024
    ? `${Math.max(1, Math.round(bytes / 1024))} KB`
    : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function UploadScreen({
  files, processing, locked = false, notice, error, progress, onAdd, onRemove, onProcess,
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [listOpen, setListOpen] = useState(false);
  const unavailable = processing || locked;

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    if (!unavailable) onAdd(event.dataTransfer.files);
  };

  return (
    <main className="mx-auto w-full max-w-[1200px] px-4 py-5 sm:px-6 sm:py-8 lg:px-8">
      <div className="mb-5">
        <h1 className="text-xl font-semibold uppercase tracking-[0.14em] text-[#0e2b4d]">Admission workflow</h1>
        <p className="mt-1 text-sm font-bold tracking-tight text-[#416998] sm:text-l">Upload admission documents</p>
      </div>

      <div
        onDragOver={event => { event.preventDefault(); }}
        onDrop={onDrop}
        className={`rounded-2xl border-2 border-dashed px-4 py-8 text-center transition sm:px-8 sm:py-12 ${
          unavailable ? "border-line bg-slate-50 opacity-70" : "border-[#9bb8da] bg-white hover:border-brand hover:bg-blue-50/50"
        }`}
      >
        <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-blue-50 text-brand">
          <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" className="h-7 w-7" stroke="currentColor" strokeWidth="1.8">
            <path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M5 14.5v4A1.5 1.5 0 0 0 6.5 20h11a1.5 1.5 0 0 0 1.5-1.5v-4" strokeLinecap="round" />
          </svg>
        </div>
        <h3 className="mt-4 text-lg font-semibold text-slate-800">Drag and drop your documents</h3>
        <p className="mt-1 text-sm text-muted">PDF, JPG or PNG</p>
        <div className="mt-5 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            disabled={unavailable || files.length >= 20}
            className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-brand px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <span aria-hidden="true" className="text-lg leading-none">+</span>
            Choose files
          </button>
          <span className="text-xs text-muted">or drop files into this area</span>
        </div>
        <input
          ref={inputRef}
          id="file-picker"
          type="file"
          multiple
          accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
          className="sr-only"
          disabled={unavailable || files.length >= 20}
          onChange={event => {
            if (event.target.files) onAdd(event.target.files);
            event.target.value = "";
          }}
        />
      </div>

      <section className="mt-5 overflow-hidden rounded-xl border border-line bg-white shadow-sm">
        <button
          type="button"
          aria-expanded={listOpen}
          onClick={() => setListOpen(value => !value)}
          className="flex min-h-14 w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-slate-50 sm:px-5"
        >
          <span>
            <span className="block text-sm font-semibold text-slate-800">Selected Documents ({files.length})</span>
            <span className="mt-0.5 block text-xs text-muted">{listOpen ? "Hide document details" : "Select the arrow to view document details"}</span>
          </span>
          <svg aria-hidden="true" viewBox="0 0 20 20" fill="none" className={`h-5 w-5 shrink-0 text-muted transition-transform ${listOpen ? "rotate-180" : ""}`}>
            <path d="m5 7.5 5 5 5-5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>

        {listOpen && (
          files.length === 0 ? (
            <p className="border-t border-line px-4 py-7 text-center text-sm text-muted">No documents selected yet.</p>
          ) : (
            <ul className="divide-y divide-slate-100 border-t border-line">
              {files.map(file => (
                <li key={file.id} className="flex min-w-0 items-center gap-3 px-4 py-3 sm:px-5">
                  <div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-slate-100 text-xs font-bold uppercase text-slate-600">
                    {file.file.name.split(".").pop()?.slice(0, 4) || "FILE"}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="break-words text-sm font-medium text-slate-800">{file.file.name}</p>
                    <p className="mt-0.5 text-xs text-muted">{fileSize(file.file.size)}</p>
                    {file.error && <p className="mt-1 break-words text-xs text-red-700">{file.error}</p>}
                  </div>
                  <span className={`shrink-0 text-xs font-medium ${file.status === "Extracted" ? "text-emerald-700" : file.error ? "text-red-700" : "text-muted"}`}>
                    {file.status}
                  </span>
                  {!unavailable && !locked && (
                    <button type="button" aria-label={`Remove ${file.file.name}`} onClick={() => onRemove(file.id)} className="grid h-9 w-9 shrink-0 place-items-center rounded-lg text-lg text-slate-500 hover:bg-red-50 hover:text-red-700">×</button>
                  )}
                </li>
              ))}
            </ul>
          )
        )}
      </section>

      <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div aria-live="polite" className={`min-h-6 text-sm leading-5 ${error ? "text-red-700" : "text-slate-600"}`}>
          {notice || progress}
        </div>
        {!locked && (
          <button
            type="button"
            disabled={!files.length || processing}
            onClick={onProcess}
            className="inline-flex min-h-11 w-full items-center justify-center rounded-lg bg-brand px-6 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
          >
            {processing ? "Processing documents…" : "Extract documents"}
          </button>
        )}
      </div>
    </main>
  );
}
