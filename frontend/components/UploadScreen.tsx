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
    <main className="upload-page mx-auto w-full max-w-[1500px] px-4 py-5 sm:px-6 sm:py-8 lg:px-8">
      <div className="upload-hero mb-6">
        <div className="upload-heading relative z-10">
          <h2 className="workflow-title"><span>Admission</span> <span className="workflow-accent">Workflow</span></h2>
          <p className="upload-hero-title"><span className="upload-word">Upload</span> <span className="typing-gradient">admission documents</span><span className="typing-cursor" aria-hidden="true" /></p>
        </div>

        <div className="upload-hero-scene">
          <div className="ambient-doc ambient-doc-one" aria-hidden="true"><span>PDF</span><i /><i /><i /></div>
          <div className="ambient-doc ambient-doc-two" aria-hidden="true"><i /><i /><i /></div>
          <div className="ambient-doc ambient-doc-three" aria-hidden="true"><i /><i /><i /></div>
          <div className="upload-dropzone relative overflow-hidden rounded-[28px] border-2 border-dashed px-4 py-8 text-center transition sm:px-8 sm:py-12"
            onDragOver={event => { event.preventDefault(); }} onDrop={onDrop}>
            <div className="upload-orbit" aria-hidden="true" />
            <div className="relative z-[1] mx-auto grid h-16 w-16 place-items-center rounded-2xl upload-icon">
              <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" className="h-8 w-8" stroke="currentColor" strokeWidth="1.8"><path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5" strokeLinecap="round" strokeLinejoin="round" /><path d="M5 14.5v4A1.5 1.5 0 0 0 6.5 20h11a1.5 1.5 0 0 0 1.5-1.5v-4" strokeLinecap="round" /></svg>
            </div>
            <h3 className="relative z-[1] mt-4 text-lg font-semibold">Drag and drop your documents</h3>
            <p className="relative z-[1] mt-1 text-sm upload-muted">PDF, JPG or PNG (Max 10MB each)</p>
            <div className="relative z-[1] mt-5 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <button type="button" onClick={() => inputRef.current?.click()} disabled={unavailable || files.length >= 20} className="upload-primary inline-flex min-h-12 items-center justify-center gap-2 rounded-full px-7 py-3 text-sm font-bold disabled:cursor-not-allowed disabled:opacity-50">
                <span aria-hidden="true" className="text-xl leading-none">+</span>Choose Files
              </button>
              <span className="text-xs upload-muted">or drop files into this area</span>
            </div>
            <input ref={inputRef} id="file-picker" type="file" multiple accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png" className="sr-only" disabled={unavailable || files.length >= 20} onChange={event => { if (event.target.files) onAdd(event.target.files); event.target.value = ""; }} />
          </div>
          <div className="robot-stage" aria-hidden="true"><img src="/admission-robot.png" alt="" className="admission-robot" width="480" height="495" /></div>
        </div>
      </div>

      <section className="documents-panel mt-5 overflow-hidden rounded-2xl border shadow-sm">
        <button type="button" aria-expanded={listOpen} onClick={() => setListOpen(value => !value)} className="documents-toggle flex min-h-16 w-full items-center justify-between gap-3 px-4 py-3 text-left sm:px-5">
          <span><span className="block text-sm font-semibold">Selected Documents ({files.length})</span><span className="mt-0.5 block text-xs upload-muted">{listOpen ? "Hide document details" : "Select the arrow to view document details"}</span></span>
          <svg aria-hidden="true" viewBox="0 0 20 20" fill="none" className={`h-5 w-5 shrink-0 transition-transform ${listOpen ? "rotate-180" : ""}`}><path d="m5 7.5 5 5 5-5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>
        </button>
        {listOpen && (files.length === 0 ? <p className="documents-empty border-t px-4 py-7 text-center text-sm">No documents selected yet.</p> : <ul className="documents-list divide-y border-t">{files.map(file => <li key={file.id} className="document-row flex min-w-0 items-center gap-3 px-4 py-3 sm:px-5"><div className="file-type grid h-10 w-10 shrink-0 place-items-center rounded-lg text-xs font-bold uppercase">{file.file.name.split(".").pop()?.slice(0, 4) || "FILE"}</div><div className="min-w-0 flex-1"><p className="break-words text-sm font-medium">{file.file.name}</p><p className="mt-0.5 text-xs upload-muted">{fileSize(file.file.size)}</p>{file.error && <p className="mt-1 break-words text-xs text-red-500">{file.error}</p>}</div><span className={`shrink-0 text-xs font-medium ${file.status === "Extracted" ? "text-emerald-500" : file.error ? "text-red-500" : "upload-muted"}`}>{file.status}</span>{!unavailable && !locked && <button type="button" aria-label={`Remove ${file.file.name}`} onClick={() => onRemove(file.id)} className="remove-file grid h-9 w-9 shrink-0 place-items-center rounded-lg text-lg">×</button>}</li>)}</ul>)}
      </section>

      <div className="upload-footer mt-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div aria-live="polite" className={`min-h-6 text-sm leading-5 ${error ? "text-red-500" : "upload-muted"}`}>{notice || progress}</div>
        {!locked && <button type="button" disabled={!files.length || processing} onClick={onProcess} className="upload-primary inline-flex min-h-12 w-full items-center justify-center rounded-full px-7 py-2.5 text-sm font-bold disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto">{processing ? "Processing documents…" : "Extract documents"}</button>}
      </div>
    </main>
  );
}
