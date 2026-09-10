export type Course = {
  id: string;
  user_id: string;
  name: string;
  code?: string | null;
  term?: string | null;
  color?: string | null;
  grading_schema_json?: unknown | null;
  source_type?: string | null;
  source_ref?: string | null;
  created_at: string;
  updated_at: string;
};

export type Task = {
  id: string;
  user_id: string;
  course_id: string | null;
  title: string;
  description?: string | null;
  purpose?: string | null;
  logistics_json?: Record<string, unknown> | null;
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
  user_id: string;
  course_id: string | null;
  /** Set when this file was embedded in another resource, e.g. a Canvas page. */
  parent_resource_id?: string | null;
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
  parse_error_code: string | null;
  index_error_code: string | null;
  content_sha256?: string | null;
  parse_pipeline_version?: string | null;
  chunking_version?: string | null;
  indexed_at?: string | null;
  last_lifecycle_event_at: string | null;
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

export type CanvasStatus = {
  connected: boolean;
  base_url?: string | null;
  last_validated_at?: string | null;
  last_synced_at?: string | null;
  last_sync_status?: string | null;
  last_sync_error?: string | null;
  canvas_user_name?: string | null;
  auth_mode?: string | null;
  oauth_configured?: boolean;
  default_base_url?: string | null;
};

export type CanvasSyncResult = {
  courses_upserted: number;
  assignments_upserted: number;
  syllabi_upserted: number;
  files_upserted?: number;
  notebooks_upserted?: number;
  errors: string[];
};

export type StudyFlowStep = {
  id: string;
  step_key: string;
  step_index: number;
  status: string;
  payload_json?: Record<string, unknown> | null;
  completed_at?: string | null;
};

export type StudyFlowRun = {
  id: string;
  flow_id: string;
  resource_id?: string | null;
  current_step_key: string;
  progress_json?: Record<string, unknown> | null;
  status: string;
  started_at: string;
  completed_at?: string | null;
  steps: StudyFlowStep[];
};

export type StudyFlow = {
  id: string;
  course_id: string;
  name: string;
  template_key: string;
  status: string;
  active_run?: StudyFlowRun | null;
};

export type PlannerLabel = {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
};

export type ResourceChunk = {
  id: string;
  chunk_index: number;
  page_number?: number | null;
  text_preview: string;
  text?: string | null;
};


