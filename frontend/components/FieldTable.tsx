
"use client";

import type { SaveState } from "@/lib/types";

type Props = {
  fields: Record<string, string>;
  selectedField: string;
  saveStates: Record<string, SaveState>;
  onSelect: (field: string) => void;
  onChange: (field: string, value: string) => void;
  onRetry: (field: string) => void;
};

const multilineFields = new Set([
  "Address",
  "Last Studied Institution with Address",
  "XI Academic Records",
  "XII Academic Records",
  "Identification Mark 1",
  "Identification Mark 2",
]);

export default function FieldTable({
  fields,
  selectedField,
  saveStates,
  onSelect,
  onChange,
  onRetry,
}: Props) {
  return (
    <div className="min-h-0 flex-1 overflow-auto">
      <table className="w-full table-fixed border-collapse text-sm">
        <colgroup>
          <col className="w-[42%] sm:w-[36%]" />
          <col />
        </colgroup>

        <thead className="sticky top-0 z-10 bg-slate-50 text-left text-xs uppercase tracking-wide text-muted">
          <tr>
            <th
              scope="col"
              className="border-b border-line px-2 py-3 sm:px-3"
            >
              Field
            </th>
            <th
              scope="col"
              className="border-b border-line px-2 py-3 sm:px-3"
            >
              Extracted value
            </th>
          </tr>
        </thead>

        <tbody>
          {Object.entries(fields)
            .filter(
              ([field]) =>
                field !== "XI Standard Total Marks" &&
                field !== "XII Standard Total Marks"
            )
            .map(([field, value]) => {
              const status = saveStates[field];
              const missing = !value?.trim();
              const Input = multilineFields.has(field)
                ? "textarea"
                : "input";

              return (
                <tr
                  key={field}
                  className={
                    selectedField === field
                      ? "bg-blue-50"
                      : "hover:bg-slate-50"
                  }
                >
                  <th
                    scope="row"
                    onClick={() => onSelect(field)}
                    className="cursor-pointer break-words [overflow-wrap:break-word] border-b border-slate-100 px-2 py-2.5 text-left align-top font-medium text-slate-700 sm:px-3"
                  >
                    {field}
                  </th>

                  <td
                    onClick={() => onSelect(field)}
                    className="border-b border-slate-100 px-2 py-2 sm:px-3"
                  >
                    <div className="flex min-w-0 items-start gap-1.5 sm:gap-2">
                      <Input
                        value={value || ""}
                        aria-label={`Value for ${field}`}
                        placeholder={
                          missing ? "Not detected — enter value" : ""
                        }
                        rows={Input === "textarea" ? 5 : undefined}
                        onFocus={() => onSelect(field)}
                        onChange={(event) =>
                          onChange(field, event.target.value)
                        }
                        className={`min-w-0 w-full flex-1 resize-y rounded-md border px-2 py-2 text-sm leading-5 outline-none focus:border-brand sm:px-2.5 ${
                          missing
                            ? "border-amber-300 bg-amber-50/50 placeholder:text-amber-800/70"
                            : "border-transparent bg-transparent hover:border-slate-200"
                        } ${Input === "input" ? "h-9" : ""}`}
                      />

                      {status === "saving" && (
                        <span
                          role="status"
                          className="shrink-0 pt-2 text-right text-[11px] text-blue-700"
                        >
                          Saving
                        </span>
                      )}

                      {status === "saved" && (
                        <span
                          role="status"
                          className="shrink-0 pt-2 text-right text-[11px] text-emerald-700"
                        >
                          Saved
                        </span>
                      )}

                      {status === "failed" && (
                        <span className="flex shrink-0 flex-col items-start gap-1 pt-2 sm:flex-row sm:items-center">
                          <span
                            role="status"
                            className="text-[11px] text-red-700"
                          >
                            Save failed
                          </span>
                          <button
                            type="button"
                            onClick={() => onRetry(field)}
                            className="text-[11px] font-semibold text-red-700 underline"
                          >
                            Retry
                          </button>
                        </span>
                      )}
                    </div>

                    {missing && (
                      <span className="px-2 text-[11px] text-amber-800">
                        Needs review
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
        </tbody>
      </table>
    </div>
  );
}
