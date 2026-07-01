"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { ChangeEvent, DragEvent } from "react";
import { ArrowRight, Check, FileUp } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Toaster } from "@/components/ui/sonner";
import { confirmJob, getApiBaseUrl, getJobStatus, uploadPdf } from "@/lib/api";
import type {
  ConfirmPageClassification,
  PageClassificationSummary,
  PollingStatus,
} from "@/lib/types";

const steps = [
  {
    number: "01",
    title: "上传",
    description: "我们分析每一页的视觉密度、颜色丰富度与版面类型。",
  },
  {
    number: "02",
    title: "审阅",
    description: "你确认 hero / process 分类，关键作品页保持应有的分量。",
  },
  {
    number: "03",
    title: "下载",
    description: "系统将压缩结果收敛到目标大小，便于提交与发送。",
  },
];

const MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024;
const POLLING_INTERVAL_MS = 2000;
const POLLING_TIMEOUT_MS = 3 * 60 * 1000;
const PRESET_TARGETS = [10, 15, 20] as const;

type AppState =
  | { kind: "idle" }
  | { kind: "uploading"; progress: number }
  | { kind: "polling"; jobId: string; status: PollingStatus; startedAt: number }
  | {
      kind: "awaiting_review";
      jobId: string;
      classifications: PageClassificationSummary[];
      thumbnails: string[];
    }
  | { kind: "complete"; jobId: string; downloadUrl: string; finalSizeMb: number }
  | { kind: "error"; message: string };

function getStatusLabel(status: PollingStatus): string {
  switch (status) {
    case "received":
      return "已提交，等待开始处理。";
    case "classifying":
      return "正在分析页面并生成分类。";
    case "compressing":
      return "正在压缩文件。";
  }
}

function isPdfFile(file: File): boolean {
  const lowerName = file.name.toLowerCase();
  return lowerName.endsWith(".pdf") && (file.type === "application/pdf" || file.type === "");
}

function validatePdfFile(file: File): string | null {
  if (!isPdfFile(file)) {
    return "仅支持上传 PDF 文件。";
  }
  if (file.size >= MAX_FILE_SIZE_BYTES) {
    return "文件需小于 100MB。";
  }
  return null;
}

function normalizeTargetSize(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  const parsed = Number(trimmed);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return null;
  }
  return parsed;
}

export default function Home() {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const uploaderRef = useRef<HTMLElement | null>(null);
  const [appState, setAppState] = useState<AppState>({ kind: "idle" });
  const [editableClassifications, setEditableClassifications] = useState<
    PageClassificationSummary[] | null
  >(null);
  const [thumbnailErrors, setThumbnailErrors] = useState<Record<number, boolean>>({});
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [selectedPreset, setSelectedPreset] = useState<number | "custom">(15);
  const [customTarget, setCustomTarget] = useState("");
  const apiBaseUrl = getApiBaseUrl();

  const targetSizeMb = useMemo(() => {
    if (selectedPreset === "custom") {
      return normalizeTargetSize(customTarget);
    }
    return selectedPreset;
  }, [customTarget, selectedPreset]);

  const completeDownloadUrl =
    appState.kind === "complete" && appState.downloadUrl
      ? `${apiBaseUrl}${appState.downloadUrl}`
      : "";

  useEffect(() => {
    if (appState.kind !== "uploading") {
      return undefined;
    }

    const interval = window.setInterval(() => {
      setAppState((current) => {
        if (current.kind !== "uploading") {
          return current;
        }
        const nextProgress = Math.min(current.progress + 12, 92);
        return { kind: "uploading", progress: nextProgress };
      });
    }, 120);

    return () => {
      window.clearInterval(interval);
    };
  }, [appState.kind]);

  useEffect(() => {
    if (appState.kind !== "polling") {
      return undefined;
    }

    const interval = window.setInterval(async () => {
      try {
        if (Date.now() - appState.startedAt > POLLING_TIMEOUT_MS) {
          window.clearInterval(interval);
          setAppState({
            kind: "error",
            message: "处理超时，请稍后重试。",
          });
          return;
        }

        const response = await getJobStatus(appState.jobId);
        switch (response.status) {
          case "received":
          case "classifying":
          case "compressing":
            setAppState((current) =>
              current.kind === "polling"
                ? {
                    ...current,
                    status: response.status,
                  }
                : current,
            );
            return;
          case "awaiting_review":
            window.clearInterval(interval);
            setEditableClassifications(response.classifications ?? []);
            setThumbnailErrors({});
            setAppState({
              kind: "awaiting_review",
              jobId: response.job_id,
              classifications: response.classifications ?? [],
              thumbnails: response.thumbnails ?? [],
            });
            return;
          case "complete":
            window.clearInterval(interval);
            setAppState({
              kind: "complete",
              jobId: response.job_id,
              downloadUrl: response.download_url ?? "",
              finalSizeMb: response.final_size_mb ?? 0,
            });
            return;
          case "failed":
            window.clearInterval(interval);
            setAppState({
              kind: "error",
              message: response.error ?? "处理失败，请重试。",
            });
            return;
          default: {
            const exhaustiveCheck: never = response.status;
            throw new Error(`Unhandled job status: ${exhaustiveCheck}`);
          }
        }
      } catch (error) {
        window.clearInterval(interval);
        setAppState({
          kind: "error",
          message: error instanceof Error ? error.message : "网络错误，请稍后重试。",
        });
      }
    }, POLLING_INTERVAL_MS);

    return () => {
      window.clearInterval(interval);
    };
  }, [appState]);

  function resetFlow(): void {
    setAppState({ kind: "idle" });
    setEditableClassifications(null);
    setThumbnailErrors({});
    setSelectedFile(null);
    setDragActive(false);
  }

  function focusUploadArea(): void {
    uploaderRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function handlePickFile(file: File | null): void {
    if (!file) {
      return;
    }

    const validationError = validatePdfFile(file);
    if (validationError) {
      toast.error(validationError);
      return;
    }

    setSelectedFile(file);
    if (appState.kind === "error") {
      setAppState({ kind: "idle" });
    }
  }

  function handleFileInputChange(event: ChangeEvent<HTMLInputElement>): void {
    const [file] = Array.from(event.target.files ?? []);
    handlePickFile(file ?? null);
  }

  function handleDragOver(event: DragEvent<HTMLDivElement>): void {
    event.preventDefault();
    setDragActive(true);
  }

  function handleDragLeave(event: DragEvent<HTMLDivElement>): void {
    event.preventDefault();
    if (event.currentTarget.contains(event.relatedTarget as Node | null)) {
      return;
    }
    setDragActive(false);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>): void {
    event.preventDefault();
    setDragActive(false);
    const [file] = Array.from(event.dataTransfer.files);
    handlePickFile(file ?? null);
  }

  async function handleUpload(): Promise<void> {
    if (!selectedFile) {
      toast.error("请先选择一个 PDF 文件。");
      return;
    }
    if (targetSizeMb === null) {
      toast.error("请输入有效的目标大小。");
      return;
    }

    setAppState({ kind: "uploading", progress: 18 });

    try {
      const result = await uploadPdf(selectedFile, targetSizeMb);
      setAppState({
        kind: "polling",
        jobId: result.job_id,
        status: "received",
        startedAt: Date.now(),
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "上传失败，请稍后重试。";
      setAppState({ kind: "error", message });
    }
  }

  function toggleClassification(pageNum: number): void {
    setEditableClassifications((current) => {
      if (!current) {
        return current;
      }
      return current.map((item) =>
        item.page_num === pageNum
          ? {
              ...item,
              page_type: item.page_type === "hero" ? "process" : "hero",
            }
          : item,
      );
    });
  }

  async function handleConfirmCompression(): Promise<void> {
    if (appState.kind !== "awaiting_review" || !editableClassifications) {
      return;
    }

    const payload: ConfirmPageClassification[] = editableClassifications.map((item) => ({
      page_num: item.page_num,
      page_type: item.page_type,
    }));

    try {
      const result = await confirmJob(appState.jobId, payload);
      setEditableClassifications(null);
      setAppState({
        kind: "polling",
        jobId: result.job_id,
        status: "compressing",
        startedAt: Date.now(),
      });
    } catch (error) {
      setAppState({
        kind: "error",
        message: error instanceof Error ? error.message : "确认压缩失败，请稍后重试。",
      });
    }
  }

  function renderReviewWorkspace() {
    if (appState.kind !== "awaiting_review" || !editableClassifications) {
      return null;
    }

    const heroCount = editableClassifications.filter((item) => item.page_type === "hero").length;
    const processCount = editableClassifications.length - heroCount;

    return (
      <section
        ref={uploaderRef}
        className="mt-24 border-t border-border/80 pt-10 pb-40 lg:mt-32"
      >
        <div className="space-y-10">
          <div className="space-y-4">
            <p className="font-serif text-4xl leading-tight">审阅分类结果</p>
            <p className="max-w-3xl text-sm leading-loose text-muted-foreground">
              AI 已初步识别每一页的重要性。点击任意页面可切换 Hero / Process，以调整最终质量分配。
            </p>
          </div>

          <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-3">
            {editableClassifications.map((item, index) => {
              const original = appState.classifications.find(
                (classification) => classification.page_num === item.page_num,
              );
              const isModified = original?.page_type !== item.page_type;
              const imageFailed = thumbnailErrors[item.page_num] === true;
              const thumbnailUrl = appState.thumbnails[index];

              return (
                <article
                  key={item.page_num}
                  role="button"
                  tabIndex={0}
                  onClick={() => toggleClassification(item.page_num)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      toggleClassification(item.page_num);
                    }
                  }}
                  className={`cursor-pointer space-y-4 border p-4 transition-colors ${
                    item.page_type === "hero"
                      ? "border-[var(--accent-ink)]"
                      : "border-border hover:border-[var(--accent-ink)]/60"
                  }`}
                >
                  <div className="aspect-[3/4] overflow-hidden border border-border bg-muted/30">
                    {imageFailed || !thumbnailUrl ? (
                      <div className="flex h-full items-center justify-center px-6 text-center text-sm leading-loose text-muted-foreground">
                        缩略图加载失败
                      </div>
                    ) : (
                      // We intentionally use a plain img here because thumbnails come from
                      // the local FastAPI backend and do not benefit from next/image.
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={`${apiBaseUrl}${thumbnailUrl}`}
                        alt={`第 ${item.page_num} 页缩略图`}
                        loading="lazy"
                        onError={() =>
                          setThumbnailErrors((current) => ({
                            ...current,
                            [item.page_num]: true,
                          }))
                        }
                        className="h-full w-full object-cover"
                      />
                    )}
                  </div>

                  <div className="space-y-3">
                    <div className="flex items-center justify-between gap-4">
                      <div className="flex items-center gap-3">
                        <p className="text-xs tracking-[0.22em] text-muted-foreground uppercase">
                          {String(item.page_num).padStart(2, "0")}
                        </p>
                        {isModified ? (
                          <span className="text-xs tracking-[0.18em] text-[var(--accent-ink)] uppercase">
                            已修改
                          </span>
                        ) : null}
                      </div>
                      {isModified ? <Check className="size-4 text-[var(--accent-ink)]" /> : null}
                    </div>

                    <div className="flex items-center justify-between gap-4">
                      <p className="text-xs tracking-[0.18em] text-muted-foreground uppercase">
                        当前分类
                      </p>
                      <p className="text-sm tracking-[0.14em] text-foreground uppercase">
                        {item.page_type}
                      </p>
                    </div>

                    <p className="text-sm leading-loose text-muted-foreground">
                      AI 置信度 {Math.round(item.confidence * 100)}%
                    </p>
                  </div>
                </article>
              );
            })}
          </div>
        </div>

        <div className="fixed right-0 bottom-0 left-0 z-20 border-t border-border bg-background/96 backdrop-blur-sm">
          <div className="mx-auto flex w-full max-w-6xl flex-col gap-4 px-6 py-4 lg:flex-row lg:items-center lg:justify-between lg:px-10">
            <p className="text-xs tracking-[0.2em] text-muted-foreground uppercase">
              {heroCount} hero · {processCount} process · {editableClassifications.length} 页共计
            </p>
            <div className="flex items-center justify-end gap-6">
              <Button
                type="button"
                variant="ghost"
                className="h-auto rounded-none border-b border-border px-0 py-1 text-sm tracking-[0.12em] uppercase hover:bg-transparent hover:text-[var(--accent-ink)]"
                onClick={resetFlow}
              >
                重置
              </Button>
              <Button
                type="button"
                className="h-12 rounded-sm border border-[var(--accent-ink)] bg-[var(--accent-ink)] px-6 text-sm tracking-[0.14em] text-white uppercase hover:bg-[var(--accent-ink-soft)]"
                onClick={handleConfirmCompression}
              >
                确认并压缩
              </Button>
            </div>
          </div>
        </div>
      </section>
    );
  }

  function renderStatusPanel() {
    switch (appState.kind) {
      case "idle":
        return null;
      case "uploading":
        return (
          <div className="space-y-4 border-t border-border/80 pt-8">
            <p className="font-serif text-3xl">正在上传文件</p>
            <p className="text-sm leading-loose text-muted-foreground">
              请稍候，文件会先送往后端创建 job。
            </p>
            <div className="space-y-3">
              <div className="h-px w-full bg-border">
                <div
                  className="h-px bg-[var(--accent-ink)] transition-[width] duration-200"
                  style={{ width: `${appState.progress}%` }}
                />
              </div>
              <p className="text-sm text-muted-foreground">{appState.progress}%</p>
            </div>
          </div>
        );
      case "polling":
        return (
          <div className="space-y-4 border-t border-border/80 pt-8">
            <p className="font-serif text-3xl">正在处理作品集</p>
            <p className="text-sm leading-loose text-muted-foreground">
              {getStatusLabel(appState.status)}
            </p>
            <div className="h-px w-full overflow-hidden bg-border">
              <div className="h-px w-1/3 animate-pulse bg-[var(--accent-ink)]" />
            </div>
            <p className="text-xs tracking-[0.18em] text-muted-foreground uppercase">
              当前状态 · {appState.status}
            </p>
          </div>
        );
      case "awaiting_review":
        return null;
      case "complete":
        return (
          <div className="space-y-4 border-t border-border/80 pt-8">
            <p className="font-serif text-3xl">处理完成</p>
            <p className="text-sm leading-loose text-muted-foreground">
              最终 {appState.finalSizeMb.toFixed(2)} MB
            </p>
            <div className="flex flex-col items-start gap-4 pt-2">
              <a
                href={completeDownloadUrl}
                download="portfolio_compressed.pdf"
                className="inline-flex"
              >
                <Button
                  type="button"
                  className="h-12 rounded-sm border border-[var(--accent-ink)] bg-[var(--accent-ink)] px-6 text-sm tracking-[0.14em] text-white uppercase hover:bg-[var(--accent-ink-soft)]"
                >
                  下载压缩后的 PDF
                </Button>
              </a>
              <Button
                type="button"
                variant="ghost"
                className="h-auto rounded-none border-b border-border px-0 py-1 text-sm tracking-[0.12em] uppercase hover:bg-transparent hover:text-[var(--accent-ink)]"
                onClick={resetFlow}
              >
                压缩另一个作品集
              </Button>
            </div>
            <p className="text-xs tracking-[0.18em] text-muted-foreground uppercase">
              Job · {appState.jobId}
            </p>
          </div>
        );
      case "error":
        return (
          <div className="space-y-4 border-t border-border/80 pt-8">
            <p className="font-serif text-3xl">出现问题</p>
            <p className="text-sm leading-loose text-red-700">{appState.message}</p>
            <p className="text-sm leading-loose text-muted-foreground">
              你可以重试上传，或点击下方按钮返回主页。
            </p>
            {appState.message.toLowerCase().includes("unreachable") ? (
              <p className="text-xs tracking-[0.12em] text-muted-foreground">
                目标大小可能过小，建议试试更大的目标。
              </p>
            ) : null}
            <div className="flex flex-col items-start gap-4 pt-2">
              <Button
                type="button"
                className="h-12 rounded-sm border border-[var(--accent-ink)] bg-[var(--accent-ink)] px-6 text-sm tracking-[0.14em] text-white uppercase hover:bg-[var(--accent-ink-soft)]"
                onClick={resetFlow}
              >
                重新上传
              </Button>
              <Button
                type="button"
                variant="ghost"
                className="h-auto rounded-none border-b border-border px-0 py-1 text-sm tracking-[0.12em] uppercase hover:bg-transparent hover:text-[var(--accent-ink)]"
                onClick={resetFlow}
              >
                返回主页
              </Button>
            </div>
          </div>
        );
    }
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      <Toaster richColors position="top-center" />
      <header className="border-b border-border/70">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-6 lg:px-10">
          <p className="font-serif text-2xl leading-none text-foreground sm:text-3xl">
            Portfolio Compressor
          </p>
          <a
            href="#"
            className="text-sm tracking-[0.16em] text-muted-foreground uppercase transition-colors hover:text-[var(--accent-ink)]"
          >
            GitHub
          </a>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-6xl flex-col px-6 py-24 lg:px-10 lg:py-32">
        <section className="grid gap-16 lg:grid-cols-[minmax(0,1.4fr)_minmax(280px,0.8fr)] lg:items-end">
          <div className="space-y-8">
            <p className="text-sm tracking-[0.18em] text-muted-foreground uppercase">
              为艺术与设计作品集而做
            </p>
            <h1 className="max-w-4xl text-6xl leading-[0.95] font-semibold text-balance sm:text-7xl lg:text-[5rem]">
              作品集智能压缩
            </h1>
            <p className="max-w-2xl text-lg leading-loose text-muted-foreground sm:text-xl">
              按页面重要性分配质量。你的关键作品保持锐利，你的文件符合大小限制。
            </p>
            <div className="pt-2">
              <Button
                type="button"
                onClick={focusUploadArea}
                className="h-12 rounded-sm border border-[var(--accent-ink)] bg-[var(--accent-ink)] px-6 text-sm tracking-[0.14em] text-white uppercase hover:bg-[var(--accent-ink-soft)]"
              >
                上传作品集
                <ArrowRight className="size-4" />
              </Button>
            </div>
          </div>

          <div className="border-t border-border pt-8 lg:pl-10">
            <p className="font-serif text-3xl leading-tight text-foreground">
              面向申请季与求职季的 PDF 交付场景。
            </p>
            <p className="mt-4 text-base leading-loose text-muted-foreground">
              不再平均牺牲所有页面，而是在目标体积内保留真正重要的视觉质量。
            </p>
          </div>
        </section>

        {appState.kind === "awaiting_review" ? (
          renderReviewWorkspace()
        ) : (
          <section
            ref={uploaderRef}
            className="mt-24 border-t border-border/80 pt-10 lg:mt-32"
          >
            <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_320px]">
              <div className="space-y-8">
                <div
                  role="button"
                  tabIndex={0}
                  onClick={() => fileInputRef.current?.click()}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      fileInputRef.current?.click();
                    }
                  }}
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop}
                  className={`cursor-pointer border border-dashed px-8 py-16 text-center transition-colors ${
                    dragActive ? "border-[var(--accent-ink)]" : "border-border"
                  }`}
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".pdf,application/pdf"
                    className="hidden"
                    onChange={handleFileInputChange}
                  />
                  <div className="mx-auto flex max-w-xl flex-col items-center gap-5">
                    <FileUp className="size-6 text-muted-foreground" />
                    <p className="font-serif text-3xl leading-tight sm:text-4xl">
                      拖拽 PDF 到此，或点击选择
                    </p>
                    <p className="max-w-lg text-sm leading-loose text-muted-foreground">
                      仅支持 PDF，且文件需小于 100MB。上传后系统会自动开始分类并轮询状态。
                    </p>
                  </div>
                </div>

                <div className="flex flex-wrap items-baseline gap-x-4 gap-y-2 text-sm text-muted-foreground">
                  <span className="tracking-[0.16em] uppercase">已选文件</span>
                  <span className="text-foreground">
                    {selectedFile ? selectedFile.name : "尚未选择文件"}
                  </span>
                </div>

                {renderStatusPanel()}
              </div>

              <aside className="space-y-8 border-t border-border pt-8 lg:pt-0">
                <div className="space-y-4">
                  <p className="text-xs tracking-[0.18em] text-muted-foreground uppercase">
                    目标大小
                  </p>
                  <div className="flex flex-wrap gap-3">
                    {PRESET_TARGETS.map((preset) => {
                      const active = selectedPreset === preset;
                      return (
                        <button
                          key={preset}
                          type="button"
                          onClick={() => setSelectedPreset(preset)}
                          className={`border-b px-0 pb-1 text-sm tracking-[0.14em] uppercase transition-colors ${
                            active
                              ? "border-[var(--accent-ink)] text-[var(--accent-ink)]"
                              : "border-transparent text-muted-foreground hover:border-border hover:text-foreground"
                          }`}
                        >
                          {preset} MB
                        </button>
                      );
                    })}
                    <button
                      type="button"
                      onClick={() => setSelectedPreset("custom")}
                      className={`border-b px-0 pb-1 text-sm tracking-[0.14em] uppercase transition-colors ${
                        selectedPreset === "custom"
                          ? "border-[var(--accent-ink)] text-[var(--accent-ink)]"
                          : "border-transparent text-muted-foreground hover:border-border hover:text-foreground"
                      }`}
                    >
                      自定义
                    </button>
                  </div>
                </div>

                <div className="space-y-3">
                  <label
                    htmlFor="custom-target"
                    className="text-xs tracking-[0.18em] text-muted-foreground uppercase"
                  >
                    自定义大小
                  </label>
                  <div className="flex items-center gap-3 border-b border-border pb-2">
                    <input
                      id="custom-target"
                      type="number"
                      min="1"
                      step="0.5"
                      inputMode="decimal"
                      value={customTarget}
                      onChange={(event) => {
                        setSelectedPreset("custom");
                        setCustomTarget(event.target.value);
                      }}
                      className="w-full bg-transparent text-base text-foreground outline-none placeholder:text-muted-foreground"
                      placeholder="例如 12.5"
                    />
                    <span className="text-sm text-muted-foreground">MB</span>
                  </div>
                </div>

                <Button
                  type="button"
                  onClick={handleUpload}
                  disabled={
                    !selectedFile || targetSizeMb === null || appState.kind === "uploading"
                  }
                  className="h-12 rounded-sm border border-[var(--accent-ink)] bg-[var(--accent-ink)] px-6 text-sm tracking-[0.14em] text-white uppercase hover:bg-[var(--accent-ink-soft)] disabled:border-border disabled:bg-transparent disabled:text-muted-foreground"
                >
                  开始上传
                </Button>
              </aside>
            </div>
          </section>
        )}

        <section className="mt-24 border-t border-border/80 pt-10 lg:mt-32">
          <div className="grid gap-10 md:grid-cols-3">
            {steps.map((step) => (
              <article key={step.number} className="space-y-4">
                <p className="text-xs tracking-[0.22em] text-muted-foreground uppercase">
                  {step.number}
                </p>
                <h2 className="font-serif text-3xl leading-tight text-foreground">
                  {step.title}
                </h2>
                <p className="max-w-sm text-base leading-loose text-muted-foreground">
                  {step.description}
                </p>
              </article>
            ))}
          </div>
        </section>
      </main>

      <footer className="border-t border-border/70">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-6 text-sm text-muted-foreground lg:px-10">
          <p>Portfolio Compressor</p>
          <p>2026</p>
        </div>
      </footer>
    </div>
  );
}
