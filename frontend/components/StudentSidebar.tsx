"use client";

import type { StudentDocument } from "@/lib/types";

type Props = {
  documents: StudentDocument[];
  selectedId: string;
  collapsed: boolean;
  onToggle: () => void;
  onSelect: (id: string) => void;
};

export default function StudentSidebar({ documents, selectedId, collapsed, onToggle, onSelect }: Props) {
  return (
    <aside className={`min-w-0 bg-slate-50 p-2.5 ${collapsed ? "w-14" : "w-full md:w-52"}`}>
      <div className={`mb-2 flex items-center ${collapsed ? "justify-center" : "justify-between"}`}>
        {!collapsed && <span className="text-xs font-bold uppercase tracking-wide text-muted">Documents</span>}
        <button type="button" onClick={onToggle} aria-label={collapsed ? "Expand student sidebar" : "Collapse student sidebar"} className="rounded px-2 py-1 text-slate-600 hover:bg-slate-200">
          {collapsed ? "»" : "«"}
        </button>
      </div>
      <nav aria-label="Students" className="grid gap-1">
        {documents.map((document, index) => {
          const selected = document.document_id === selectedId;
          const failed = document.status === "failed" || Boolean(document.error);
          return (
            <button
              key={document.document_id}
              type="button"
              onClick={() => onSelect(document.document_id)}
              title={collapsed ? `${index + 1}. ${document.original_filename}` : undefined}
              aria-current={selected ? "page" : undefined}
              className={`flex min-w-0 items-center gap-2 rounded-md px-2 py-2 text-left text-xs ${selected ? "bg-blue-100 font-semibold text-blue-800" : "text-slate-700 hover:bg-slate-200"}`}
            >
              <span className={`h-2 w-2 shrink-0 rounded-full ${failed ? "bg-gray-600" : document.status === "extracted" || document.status === "reviewed" ? "bg-emerald-600" : "bg-[dimgray]"}`} />
              {!collapsed && <span className="min-w-0 flex-1 truncate">{index + 1}. {document.original_filename}</span>}
            </button>
          );
        })}
      </nav>
    </aside>
  );
}
