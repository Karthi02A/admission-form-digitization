export type StudentDocument = {
  document_id: string;
  original_filename: string;
  content_type: string;
  status: string;
  error?: string | null;
  fields: Record<string, string>;
  field_confidence?: Record<string, number>;
};

export type UploadEntry = {
  id: string;
  file: File;
  status: string;
  documentId?: string;
  error?: string;
};

export type SaveState = "saving" | "saved" | "failed";
