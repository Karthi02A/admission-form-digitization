"use client";

import { useMemo, useState } from "react";
import type { SaveState, StudentDocument } from "@/lib/types";
import DocumentViewer from "@/components/DocumentViewer";
import FieldTable from "@/components/FieldTable";
import StudentSidebar from "@/components/StudentSidebar";
import { apiUrl } from "@/lib/api";

type Props = {
  batchId: string; documents: StudentDocument[]; selectedId: string;
  saveStates: Record<string, Record<string, SaveState>>; notice: string;
  onSelectDocument: (id: string) => void;
  onChangeField: (documentId: string, field: string, value: string) => void;
  onRetryField: (documentId: string, field: string) => void;
};

const descriptions: Record<string, [string, string]> = {
  "Student Name": ["Text", "Student name as written on the admission form."],
  "Course Applied": ["Checkbox / text", "All clearly selected programmes, separated by semicolons."],
  "Gender": ["Checkbox", "Selected gender option."],
  "Community": ["Checkbox / text", "Community or caste category."],
  "Physically Challenged": ["Checkbox", "Selected Yes or No option."],
  "First Graduate": ["Checkbox", "Selected Yes or No option."],
  "XI Academic Records": ["Academic table", "Subject-wise XI-standard marks and subjects."],
  "XII Academic Records": ["Academic table", "Subject-wise XII-standard marks and subjects."],
  "Address": ["Multiline text", "Student communication address."],
  "Email": ["Email", "Student email address."],
  "Mobile Number": ["Phone", "Student mobile number."],
  "Transfer Certificate": ["Certificate status", "Status of the transfer certificate in the corresponding certificate row."],
  "Mark Sheets": ["Certificate status", "Status of the original mark sheets in the corresponding certificate row."],
  "Community Certificate": ["Certificate status", "Status of community certificate proof in the corresponding certificate row."],
  "Income Certificate": ["Certificate status", "Status of the income certificate in the corresponding certificate row."],
  "Passport-size Photo": ["Certificate status", "Status of the required four passport-size photos in the corresponding certificate row."],
  "Aadhaar Proof": ["Certificate status", "Status of Aadhaar proof in the corresponding certificate row."],
  "PAN Proof": ["Certificate status", "Status of PAN proof in the corresponding certificate row."],
  "Bank Passbook Proof": ["Certificate status", "Status of bank passbook proof in the corresponding certificate row."],
};

export default function ReviewScreen({ batchId, documents, selectedId, saveStates, notice, onSelectDocument, onChangeField, onRetryField }: Props) {
  const [collapsed, setCollapsed] = useState(false);
  const [selectedField, setSelectedField] = useState("");
  const document = documents.find(item => item.document_id === selectedId) || documents[0];
  const saveStatus = useMemo(() => document ? saveStates[document.document_id] || {} : {}, [document, saveStates]);
  const currentValue = document?.fields[selectedField] || "";
  const [fieldType, fieldDescription] = descriptions[selectedField] || ["Text", `Value for “${selectedField}” from the fixed admission form.`];

  if (!document) return <main className="p-8 text-sm text-muted">No successfully uploaded documents are available to review.</main>;

  return (
    <main className="mx-auto w-full max-w-[1800px] px-2 py-3 sm:px-4 sm:py-4 lg:px-5">
      <div className={`grid min-h-[calc(100dvh-110px)] w-full min-w-0 overflow-hidden rounded-xl border border-line bg-white shadow-sm ${collapsed ? "grid-cols-[56px_minmax(0,1fr)_minmax(0,1fr)]" : "grid-cols-[190px_minmax(0,1fr)_minmax(0,1fr)]"} max-lg:grid-cols-1`}>
        <div className="min-w-0 border-b border-line lg:border-b-0 lg:border-r lg:border-line">
          <StudentSidebar documents={documents} selectedId={document.document_id} collapsed={collapsed} onToggle={() => setCollapsed(value => !value)} onSelect={onSelectDocument} />
        </div>
        <section className="flex min-h-[420px] min-w-0 flex-col self-start max-lg:border-r-0 max-lg:border-b max-lg:order-2">
          <DocumentViewer sourceUrl={apiUrl(`/api/batches/${encodeURIComponent(batchId)}/documents/${encodeURIComponent(document.document_id)}/file`)} filename={document.original_filename} />
          <section aria-label="Selected field details" className="border-t border-line px-4 py-3">
            <h2 className="mb-2 text-xs font-bold uppercase tracking-wide text-muted">Selected Field Details</h2>
            {selectedField ? <dl className="grid grid-cols-[120px_1fr] gap-x-3 gap-y-1 text-xs"><dt className="text-muted">Field name</dt><dd className="break-words font-medium">{selectedField}</dd><dt className="text-muted">Current value</dt><dd className="break-words">{currentValue || <span className="italic text-amber-800">No value — manual review needed</span>}</dd><dt className="text-muted">Field type</dt><dd>{fieldType}</dd><dt className="text-muted">Description</dt><dd className="text-slate-600">{fieldDescription}</dd></dl> : <p className="text-xs text-muted">Select a field to see its details.</p>}
          </section>
        </section>
        <section className="flex min-h-[420px] min-w-0 flex-col max-lg:order-3">
          <div className="flex min-h-11 items-center justify-between border-b border-line px-4 py-2"><h2 className="text-sm font-semibold">Extracted data</h2>{document.error && <span className="text-xs font-medium text-red-700">Extraction failed</span>}</div>
          {document.error && <p role="alert" className="border-b border-red-100 bg-red-50 px-4 py-2 text-xs text-red-800">{document.error}</p>}
          {notice && <p role="status" className="border-b border-amber-100 bg-amber-50 px-4 py-2 text-xs text-amber-900">{notice}</p>}
          <FieldTable fields={document.fields} selectedField={selectedField} saveStates={saveStatus} onSelect={setSelectedField} onChange={(field, value) => onChangeField(document.document_id, field, value)} onRetry={field => onRetryField(document.document_id, field)} />
        </section>
      </div>
    </main>
  );
}
