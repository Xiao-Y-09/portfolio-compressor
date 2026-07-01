import type { ConfirmPageClassification, JobStatusResponse } from "@/lib/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL;
const REQUEST_TIMEOUT_MS = 30000;

function getApiUrl(): string {
  if (!API_URL) {
    throw new Error("NEXT_PUBLIC_API_URL is not configured.");
  }
  return API_URL;
}

export function getApiBaseUrl(): string {
  return getApiUrl();
}

async function parseError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string; error?: string };
    return payload.detail ?? payload.error ?? `Request failed with status ${response.status}`;
  } catch {
    return `Request failed with status ${response.status}`;
  }
}

async function fetchWithTimeout(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    const response = await fetch(input, {
      ...init,
      signal: controller.signal,
    });
    return response;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("请求超时，请检查网络后重试。");
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
  }
}

export async function uploadPdf(
  file: File,
  targetSizeMb: number,
): Promise<{ job_id: string; status: string }> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("target_size_mb", String(targetSizeMb));

  const response = await fetchWithTimeout(`${getApiUrl()}/jobs`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw new Error(await parseError(response));
  }

  return (await response.json()) as { job_id: string; status: string };
}

export async function getJobStatus(jobId: string): Promise<JobStatusResponse> {
  const response = await fetchWithTimeout(`${getApiUrl()}/jobs/${jobId}`, {
    method: "GET",
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(await parseError(response));
  }

  return (await response.json()) as JobStatusResponse;
}

export async function confirmJob(
  jobId: string,
  classifications: ConfirmPageClassification[],
): Promise<{ job_id: string; status: string }> {
  const response = await fetchWithTimeout(`${getApiUrl()}/jobs/${jobId}/confirm`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ classifications }),
  });

  if (!response.ok) {
    throw new Error(await parseError(response));
  }

  return (await response.json()) as { job_id: string; status: string };
}
