export type Course = {
  id: string;
  user_id: string;
  name: string;
  code?: string | null;
  term?: string | null;
  color?: string | null;
  grading_schema_json?: unknown | null;
  created_at: string;
  updated_at: string;
};

export type Task = {
  id: string;
  user_id: string;
  course_id: string;
  title: string;
  description?: string | null;
  task_type?: string | null;
  due_at?: string | null;
  weight?: number | null;
  source_type?: string | null;
  source_ref?: string | null;
  status: string;
  estimated_minutes?: number | null;
  priority_score?: number | null;
  created_at: string;
  updated_at: string;
};

export type Resource = {
  id: string;
  course_id: string | null;
  title: string;
  resource_type?: string | null;
  original_filename?: string | null;
  mime_type?: string | null;
  storage_path?: string | null;
  source_type?: string | null;
  source_ref?: string | null;
  parse_status: string;
  ocr_status: string;
  index_status: string;
  lifecycle_state: string;
  metadata_json?: unknown | null;
  content_sha256?: string | null;
  parse_pipeline_version?: string | null;
  chunking_version?: string | null;
  indexed_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type ResourceBatchUploadResult = {
  filename: string;
  mime_type?: string | null;
  status: "accepted" | "rejected" | string;
  reason?: string | null;
  resource?: Resource | null;
};

export type Notebook = {
  id: string;
  course_id: string | null;
  parent_id?: string | null;
  title: string;
  created_at: string;
  updated_at: string;
};

export type NoteDocument = {
  id: string;
  user_id: string;
  notebook_id: string;
  title: string;
  note_type?: string | null;
  metadata_json?: unknown | null;
  created_at: string;
  updated_at: string;
};

export type NotePage = {
  id: string;
  user_id: string;
  note_document_id: string;
  resource_id: string | null;
  page_index: number;
  page_data_json?: unknown | null;
  extracted_text?: string | null;
  created_at: string;
  updated_at: string;
};

