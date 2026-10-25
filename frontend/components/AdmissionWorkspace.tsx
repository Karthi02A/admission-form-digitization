"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import ReviewScreen from "@/components/ReviewScreen";
import UploadScreen from "@/components/UploadScreen";
import { apiUrl, request } from "@/lib/api";
import type { SaveState, StudentDocument, UploadEntry } from "@/lib/types";

type BatchResponse = { batch_id: string };
type UploadResponse = {
  results: Array<{ filename: string; status: string; error?: string; document_id?: string }>;
  documents: StudentDocument[];
};
type BatchProgressResponse = {
  batch_id: string;
  status: string;
  documents: StudentDocument[];
  processing_progress?: {
    total: number;
    completed: number;
    succeeded: number;
    failed: number;
    needs_template_review: number;
    processing?: number;
    percent: number;
    current_document_id?: string | null;
  };
};
type SavePayload = { documentId: string; field: string; value: string };

const allowedExtensions = new Set([".pdf", ".jpg", ".jpeg", ".png"]);
const maxFiles = 20;
const maxBytes = 15 * 1024 * 1024;

function extensionOf(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot >= 0 ? name.slice(dot).toLowerCase() : "";
}

function responseDocument(document: StudentDocument, error?: string): StudentDocument {
  return {
    ...document,
    error: error || document.error || null,
    status: error ? "failed" : document.status,
  };
}

export default function AdmissionWorkspace() {
  const [files, setFiles] = useState<UploadEntry[]>([]);
  const [documents, setDocuments] = useState<StudentDocument[]>([]);
  const [batchId, setBatchId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [screen, setScreen] = useState<"upload" | "review">("upload");
  const [processing, setProcessing] = useState(false);
  const [progress, setProgress] = useState("");
  const [notice, setNotice] = useState("");
  const [noticeError, setNoticeError] = useState(false);
  const [reviewNotice, setReviewNotice] = useState("");
  const [saveStates, setSaveStates] = useState<Record<string, Record<string, SaveState>>>({});
  const [batchBusy, setBatchBusy] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exported, setExported] = useState(false);
  const batchIdRef = useRef<string | null>(null);
  const pendingSaves = useRef(new Map<string, SavePayload>());
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>());
  const inFlight = useRef(new Map<string, Promise<boolean>>());

  const currentDocument = useMemo(
    () => documents.find(document => document.document_id === selectedId) || documents[0],
    [documents, selectedId],
  );

  const setSaveState = useCallback((documentId: string, field: string, status: SaveState) => {
    setSaveStates(previous => ({
      ...previous,
      [documentId]: { ...previous[documentId], [field]: status },
    }));
  }, []);

  const addFiles = useCallback((incoming: FileList | File[]) => {
    if (processing || batchIdRef.current) return;
    const candidates = Array.from(incoming);
    const added: UploadEntry[] = [];
    let issue = "";
    const remaining = Math.max(0, maxFiles - files.length);
    for (const file of candidates) {
      if (added.length >= remaining) {
        issue = `A batch can contain no more than ${maxFiles} documents.`;
        break;
      }
      if (!allowedExtensions.has(extensionOf(file.name))) {
        issue = `${file.name}: unsupported file type.`;
        continue;
      }
      if (file.size === 0) {
        issue = `${file.name}: file is empty.`;
        continue;
      }
      if (file.size > maxBytes) {
        issue = `${file.name}: file exceeds 15 MB.`;
        continue;
      }
      added.push({ id: crypto.randomUUID(), file, status: "Selected" });
    }
    if (added.length) setFiles(previous => [...previous, ...added]);
    if (issue) {
      setNotice(issue);
      setNoticeError(true);
    } else if (added.length) {
      setNotice("");
      setNoticeError(false);
    }
  }, [files.length, processing]);

  const removeFile = useCallback((id: string) => {
    if (processing || batchIdRef.current) return;
    setFiles(previous => previous.filter(file => file.id !== id));
  }, [processing]);

  const flushField = useCallback(async (key: string): Promise<boolean> => {
    const active = inFlight.current.get(key);
    if (active) {
      const activeResult = await active;
      if (pendingSaves.current.has(key)) return flushField(key);
      return activeResult;
    }

    const payload = pendingSaves.current.get(key);
    if (!payload) return true;
    const batch = batchIdRef.current;
    if (!batch) return false;
    pendingSaves.current.delete(key);

    const operation = (async (): Promise<boolean> => {
      setSaveState(payload.documentId, payload.field, "saving");
      try {
        const saved = await request<{ value: string }>(
          `/api/batches/${encodeURIComponent(batch)}/documents/${encodeURIComponent(payload.documentId)}/fields/${encodeURIComponent(payload.field)}`,
          {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ value: payload.value }),
          },
        );
        const hasNewerValue = pendingSaves.current.has(key);
        if (!hasNewerValue) {
          setDocuments(previous => previous.map(document => document.document_id === payload.documentId
            ? { ...document, fields: { ...document.fields, [payload.field]: saved.value } }
            : document));
        }
        if (hasNewerValue) return true;
        setSaveState(payload.documentId, payload.field, "saved");
        return true;
      } catch {
        if (pendingSaves.current.has(key)) return true;
        pendingSaves.current.set(key, payload);
        setSaveState(payload.documentId, payload.field, "failed");
        return false;
      }
    })();

    inFlight.current.set(key, operation);
    const result = await operation;
    if (inFlight.current.get(key) === operation) inFlight.current.delete(key);
    if (pendingSaves.current.has(key)) return flushField(key);
    return result;
  }, [setSaveState]);

  const flushAll = useCallback(async (): Promise<boolean> => {
    const keys = new Set([
      ...pendingSaves.current.keys(),
      ...timers.current.keys(),
      ...inFlight.current.keys(),
    ]);
    for (const [key, timer] of timers.current) {
      clearTimeout(timer);
      timers.current.delete(key);
    }
    const results = await Promise.all(Array.from(keys, key => flushField(key)));
    return results.every(Boolean);
  }, [flushField]);

  const changeField = useCallback((documentId: string, field: string, value: string) => {
    const key = `${documentId}:${field}`;
    setDocuments(previous => previous.map(document => document.document_id === documentId
      ? { ...document, fields: { ...document.fields, [field]: value } }
      : document));
    pendingSaves.current.set(key, { documentId, field, value });
    setSaveState(documentId, field, "saving");
    const existing = timers.current.get(key);
    if (existing) clearTimeout(existing);
    timers.current.set(key, setTimeout(() => {
      timers.current.delete(key);
      void flushField(key);
    }, 450));
  }, [flushField, setSaveState]);

  const startProcessing = useCallback(async () => {
    if (!files.length || processing) return;
    setProcessing(true);
    setProgress("Creating batch…");
    setNotice("");
    setNoticeError(false);

    try {
      const batch = await request<BatchResponse>("/api/batches", { method: "POST" });
      batchIdRef.current = batch.batch_id;
      setBatchId(batch.batch_id);

      setProgress("Uploading and validating documents…");
      const form = new FormData();
      files.forEach(entry => form.append("files", entry.file));
      const uploaded = await request<UploadResponse>(
        `/api/batches/${encodeURIComponent(batch.batch_id)}/upload`,
        { method: "POST", body: form },
      );

      let nextDocuments = uploaded.documents.map(document => responseDocument(document));
      setDocuments(nextDocuments);
      setFiles(previous => previous.map((entry, index) => {
        const result = uploaded.results[index];
        return {
          ...entry,
          status: result?.status === "failed" ? "Upload failed" : "Uploaded",
          documentId: result?.document_id,
          error: result?.error,
        };
      }));

      const validCount = uploaded.results.filter(result => Boolean(result.document_id)).length;
      if (!validCount) {
        setNotice("No documents passed upload validation. Review the file errors and try again.");
        setNoticeError(true);
        setProgress("Upload validation finished.");
        return;
      }

      setProgress(`Starting batch extraction for ${validCount} document(s)…`);
      await request(`/api/batches/${encodeURIComponent(batch.batch_id)}/extract`, { method: "POST" });

      // The backend owns the batch queue. Poll persisted state rather than issuing one
      // extraction request per document from the browser.
      const pollStartedAt = Date.now();
      const maxPollingMs = 30 * 60 * 1000;
      let terminal = false;

      while (!terminal) {
        // Poll less often to reduce repeated batch-status GET requests; this does not change extraction logic.
        await new Promise(resolve => setTimeout(resolve, 3000));
        const snapshot = await request<BatchProgressResponse>(
          `/api/batches/${encodeURIComponent(batch.batch_id)}`,
        );

        nextDocuments = snapshot.documents.map(document => responseDocument(document));
        setDocuments(nextDocuments);

        const byId = new Map(nextDocuments.map(document => [document.document_id, document]));
        setFiles(previous => previous.map(entry => {
          const doc = entry.documentId ? byId.get(entry.documentId) : undefined;
          if (!doc) return entry;
          const statusLabel =
            doc.status === "processing" ? "Processing" :
            doc.status === "queued" ? "Queued" :
            doc.status === "needs_template_review" ? "Template review needed" :
            doc.status === "failed" ? "Extraction failed" :
            ["extracted", "review_required", "reviewed"].includes(doc.status) ? "Extracted" :
            doc.status;
          return { ...entry, status: statusLabel, error: doc.error || undefined };
        }));

        const p = snapshot.processing_progress;
        if (p) {
          setProgress(
            `Processing: ${p.completed}/${p.total} complete (${p.percent}%). ` +
            `${p.failed} failed; ${p.needs_template_review} need template review.`,
          );
        } else {
          setProgress("Batch extraction is running…");
        }

        terminal = ["completed", "completed_with_errors"].includes(snapshot.status);
        if (!terminal && Date.now() - pollStartedAt > maxPollingMs) {
          throw new Error("Batch processing is taking longer than expected. The saved batch remains available; refresh to check its status.");
        }
      }

      const finalSnapshot = await request<BatchProgressResponse>(
        `/api/batches/${encodeURIComponent(batch.batch_id)}`,
      );
      nextDocuments = finalSnapshot.documents.map(document => responseDocument(document));
      setDocuments(nextDocuments);
      setSelectedId(nextDocuments[0]?.document_id || "");

      const failedUploads = uploaded.results.filter(result => result.status === "failed").length;
      const failedDocs = nextDocuments.filter(document => document.status === "failed").length;
      const succeeded = nextDocuments.filter(document =>
        ["extracted", "review_required", "reviewed"].includes(document.status),
      ).length;

      setProgress(`Batch finished. ${succeeded} extracted; ${failedDocs + failedUploads} failed.`);
      setNotice(nextDocuments.length ? "" : "No documents were successfully uploaded.");
      setNoticeError(!nextDocuments.length);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "The batch could not be processed.");
      setNoticeError(true);
      setProgress("Processing could not finish. Any saved results remain in the batch.");
    } finally {
      setProcessing(false);
    }
  }, [files, processing]);

  const openReview = useCallback(() => {
    if (!documents.length) return;
    setScreen("review");
    setReviewNotice("");
  }, [documents.length]);

  const backToUpload = useCallback(async () => {
    if (!(await flushAll())) {
      setReviewNotice("Some edits could not be saved. Retry them before leaving the review.");
      return;
    }
    setScreen("upload");
  }, [flushAll]);

  const selectDocument = useCallback(async (documentId: string) => {
    if (documentId === selectedId) return;
    if (!(await flushAll())) {
      setReviewNotice("Some edits could not be saved. Retry them before switching documents.");
      return;
    }
    setReviewNotice("");
    setSelectedId(documentId);
  }, [flushAll, selectedId]);

  const retryField = useCallback(async (documentId: string, field: string) => {
    const key = `${documentId}:${field}`;
    if (!(await flushField(key))) {
      setReviewNotice(`Could not save ${field}. Your edit is retained; retry when the API is available.`);
    } else {
      setReviewNotice("");
    }
  }, [flushField]);

  const exportBatch = useCallback(async () => {
    if (!batchId || exporting || exported) return;
    setExporting(true);
    if (!(await flushAll())) {
      setReviewNotice("Export cancelled because some edits could not be saved. Retry failed fields first.");
      setExporting(false);
      return;
    }
    setReviewNotice("");
    try {
      const response = await fetch(apiUrl(`/api/batches/${encodeURIComponent(batchId)}/export.xlsx`));
      if (!response.ok) throw new Error(`Export failed (${response.status}). Please try again.`);
      const blob = await response.blob();
      const disposition = response.headers.get("content-disposition") || "";
      const match = disposition.match(/filename\*?=(?:UTF-8''|")?([^";]+)/i);
      const filename = match ? decodeURIComponent(match[1].replace(/"/g, "")) : "admission-export.xlsx";
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
      setExported(true);
      setReviewNotice("Export completed. Start a New Batch to export another batch.");
    } catch (error) {
      setReviewNotice(error instanceof Error ? error.message : "Export failed. Please try again.");
    } finally {
      setExporting(false);
    }
  }, [batchId, exporting, exported, flushAll]);

  const startNewBatch = useCallback(async () => {
    if (!batchId) return;
    const confirmed = window.confirm(
      `Start a new batch? This permanently deletes the current batch and its ${documents.length} uploaded document(s).`,
    );
    if (!confirmed) return;
    setBatchBusy(true);
    try {
      if (!(await flushAll())) {
        setReviewNotice("A field correction could not be saved. The current batch was kept.");
        return;
      }
      await request(`/api/batches/${encodeURIComponent(batchId)}`, { method: "DELETE" });
      for (const timer of timers.current.values()) clearTimeout(timer);
      timers.current.clear();
      pendingSaves.current.clear();
      inFlight.current.clear();
      batchIdRef.current = null;
      setBatchId(null);
      setExporting(false);
      setExported(false);
      setFiles([]);
      setDocuments([]);
      setSelectedId("");
      setSaveStates({});
      setNotice("");
      setNoticeError(false);
      setProgress("");
      setReviewNotice("");
      setScreen("upload");
    } catch (error) {
      setReviewNotice(`Could not start a new batch: ${error instanceof Error ? error.message : "request failed"}. The current batch was kept.`);
    } finally {
      setBatchBusy(false);
    }
  }, [batchId, documents.length, flushAll]);

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 flex min-h-[70px] flex-wrap items-center justify-between gap-3 border-b border-line bg-white px-4 py-3 shadow-sm md:px-7">
        <div className="flex items-center gap-3">
          <div aria-hidden="true" className="grid h-10 w-10 place-items-center rounded-xl bg-brand text-sm font-extrabold text-white">AD</div>
          <div>
            <h1 className="text-base font-bold tracking-tight">Admission Form Digitization</h1>
            <p className="mt-0.5 text-xs text-muted">Upload, extract, and review admission records.</p>
          </div>
        </div>
        {screen === "review" && currentDocument && (
          <div className="flex flex-wrap items-center justify-end gap-2">
            <button type="button" onClick={() => void backToUpload()} disabled={batchBusy} className="rounded-lg border border-line px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">Back to upload</button>
            <button type="button" onClick={() => void exportBatch()} disabled={batchBusy || exporting || exported} className="rounded-lg bg-brand px-3 py-2 text-sm font-semibold text-white hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-50">{exporting ? "Exporting…" : exported ? "Exported" : "Export Excel"}</button>
            <button type="button" onClick={() => void startNewBatch()} disabled={batchBusy} className="rounded-lg border border-red-200 px-3 py-2 text-sm font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50">{batchBusy ? "Starting…" : "New Batch"}</button>
          </div>
        )}
      </header>

      {screen === "upload" ? (
        <>
          <UploadScreen
            files={files}
            processing={processing}
            locked={Boolean(batchId)}
            notice={notice}
            error={noticeError}
            progress={progress}
            onAdd={addFiles}
            onRemove={removeFile}
            onProcess={() => void startProcessing()}
          />
          {documents.length > 0 && !processing && (
            <div className="mx-auto flex max-w-[1500px] justify-end px-5 pb-7 lg:px-8">
              <button type="button" onClick={openReview} className="rounded-lg bg-brand px-5 py-2.5 text-sm font-semibold text-white hover:bg-blue-800">Review</button>
            </div>
          )}
          {batchId && !processing && (
            <div className="mx-auto flex max-w-[1500px] justify-end px-5 pb-7 lg:px-8">
              <button type="button" onClick={() => void startNewBatch()} disabled={batchBusy} className="rounded-lg border border-red-200 px-4 py-2 text-sm font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50">Discard batch and start over</button>
            </div>
          )}
        </>
      ) : (
        <ReviewScreen
          batchId={batchId || ""}
          documents={documents}
          selectedId={selectedId}
          saveStates={saveStates}
          notice={reviewNotice}
          onSelectDocument={id => void selectDocument(id)}
          onChangeField={changeField}
          onRetryField={(documentId, field) => void retryField(documentId, field)}
        />
      )}
    </div>
  );
}
