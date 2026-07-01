export type JobStatus =
  | "received"
  | "classifying"
  | "awaiting_review"
  | "compressing"
  | "complete"
  | "failed";

export type PollingStatus = "received" | "classifying" | "compressing";

export type PageType = "hero" | "process";

export type PageClassificationSummary = {
  page_num: number;
  page_type: PageType;
  confidence: number;
};

export type ConfirmPageClassification = {
  page_num: number;
  page_type: PageType;
};

export type JobStatusResponse = {
  job_id: string;
  status: JobStatus;
  classifications?: PageClassificationSummary[] | null;
  thumbnails?: string[] | null;
  download_url?: string | null;
  final_size_mb?: number | null;
  error?: string | null;
};
