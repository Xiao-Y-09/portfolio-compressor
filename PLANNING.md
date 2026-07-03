# AI Portfolio Compressor · MVP Development Spec

> 这是一份给 Codex（或任何 AI coding agent）读的 spec 文档。
> 目的：让 Codex 严格按照本文档实现,避免自由发挥导致偏离设计。
> Owner: Xiao Yang · 起草日期: 2026-07

---

## 0. 项目背景 (Context)

面向艺术生/设计师的 PDF 作品集智能压缩工具。

**核心差异化**：现有工具（Pi7、Imresizer、ToolShelf）都是"一刀切"降低全局质量,导致关键页面（effect 图、渲染图）和次要页面（草图、文字调研）被同等程度压缩。本工具通过**按页面重要性智能分配质量权重**,让关键页面保持高质量,次要页面容忍更多压缩,总大小达到目标值。

**目标用户**：递交留学申请或求职时受限于 10MB/15MB/20MB 大小限制的艺术生/设计生。

---

## 1. MVP 范围 (Scope)

### 1.1 MVP 明确要做的

- [x] CLI 工具：输入 PDF + 目标大小 → 输出压缩 PDF
- [x] 基于 OpenCV 的启发式图片级分类（hero vs process）
- [x] 图片级预算分配 + 二分搜索质量,收敛到目标大小
- [x] FastAPI 服务层,包装 CLI 逻辑
- [x] 两阶段交互：分类完成 → 用户 review（图片级）→ 确认后压缩
- [x] 简单 Next.js 前端（上传、review、下载）
- [x] IP-based 限流
- [x] 匿名日志收集（用于后续训练更好的分类器）

### 1.2 MVP 明确不做的 (Non-Goals)

- [ ] **不做用户账户系统**（不用 Supabase Auth、不用 login）
- [ ] **不做支付**（不接 Stripe）
- [ ] **不做云数据库**（job 状态用 in-memory dict,进程重启丢失可接受）
- [ ] **不接 Gemma 视觉模型**（MVP 只用 OpenCV 启发式,Phase 2 才引入）
- [ ] **不做管理后台、数据分析 dashboard**
- [ ] **不做作品集历史记录、多版本管理**
- [ ] **不做 SSE / WebSocket**（前端用 HTTP 轮询即可）
- [ ] **不做多语言 i18n**（先只有中文 UI）
- [ ] **不做花哨动画、复杂设计**（前端用 shadcn/ui 默认组件）

**⚠️ 如果 Codex 想给我加以上任何一项功能,拒绝并提示"这是 non-goal"。**

---

## 2. 技术栈约束

### 2.1 后端（必用）

- **Python**: 3.11+
- **Web framework**: FastAPI + Uvicorn
- **PDF 处理**: PyMuPDF (`import fitz`)
- **图像处理**: OpenCV (`cv2`) + Pillow (`PIL`)
- **限流**: slowapi
- **数据模型**: Pydantic v2
- **测试**: pytest
- **依赖管理**: `pyproject.toml` + `uv` (推荐) 或 `pip` + `requirements.txt`

### 2.2 前端（Phase 2 才写）

- **Framework**: Next.js 14+ App Router
- **UI**: Tailwind CSS + shadcn/ui
- **HTTP**: 原生 fetch（不用 axios、swr）
- **状态**: React useState（不用 Redux、Zustand）
- **文件**: TypeScript 严格模式

### 2.3 禁用的东西

- ❌ 不用 Django、Flask
- ❌ 不用 Celery、Redis、RabbitMQ（MVP 阶段用不上）
- ❌ 不用 SQLAlchemy、任何 ORM（job 状态在内存里,不需要 DB）
- ❌ 不用 pypdf、pdfplumber（用 PyMuPDF 一个库就够）
- ❌ 前端不用 UI 库以外的第三方（比如不装 framer-motion、react-dropzone）

---

## 3. 目录结构

```
portfolio-compressor/
├── PLANNING.md                    # 本文件
├── PROGRESS.md                    # Codex 每完成一步在这里打勾
├── README.md                      # 用户 facing 文档
├── pyproject.toml
├── .python-version                # 3.11
├── .gitignore
│
├── src/
│   └── compressor/
│       ├── __init__.py
│       ├── cli.py                 # CLI 入口
│       ├── pipeline.py            # 主流程编排
│       ├── pdf_io.py              # PDF 图片扫描、提取、写回
│       ├── classifier.py          # 图片级分类（OpenCV 启发式）
│       ├── compress.py            # 预算分配 + 单图 PPI 降级 + JPEG quality 二分搜索
│       ├── schemas.py             # Pydantic 数据模型
│       ├── config.py              # 常量、阈值、权重
│       └── exceptions.py          # 自定义异常
│
├── server/
│   ├── main.py                    # FastAPI app
│   ├── routes.py                  # API endpoints
│   ├── jobs.py                    # in-memory job manager
│   ├── ratelimit.py               # slowapi 配置
│   └── logging_config.py          # 匿名日志格式
│
├── web/                           # Next.js (Phase 2)
│   └── (标准 Next.js App Router 结构)
│
├── tests/
│   ├── test_classifier.py
│   ├── test_compress.py
│   ├── test_pipeline.py
│   └── fixtures/                  # 测试用 PDF
│
├── data/                          # gitignored
│   ├── uploads/                   # 临时上传
│   ├── outputs/                   # 临时输出
│   └── logs/                      # 匿名日志 JSONL
│
└── scripts/
    ├── cleanup.py                 # 清理 1h 前的临时文件
    └── run_dev.sh                 # 本地开发启动脚本
```

---

## 4. 数据模型 (Schemas)

### 4.1 ImageInfo (图片级核心单元)

```python
class ImageInfo(BaseModel):
    """PDF 内单张嵌入图片的元信息 + 分类结果"""
    xref: int                       # PDF 内部交叉引用编号
    page_num: int                   # 所在页码 (1-indexed)
    original_bytes: int             # 原始图片数据大小 (bytes)
    pixel_width: int                # 原始像素宽
    pixel_height: int               # 原始像素高
    format: str                     # 原始格式: "jpeg" / "png" / "jp2" / ...
    display_rect: tuple[float, float, float, float]  # 在页面上的显示区域 (x0, y0, x1, y1), pt
    display_ratio: float            # 显示面积 / 页面面积, 0.0~1.0
    effective_ppi: float            # 实际显示 PPI = pixel_width / display_width_inches
    classification: PageType = PageType.PROCESS
    confidence: float = 0.5
    user_override: bool = False
```

### 4.2 PageClassification (聚合层,用于展示和日志)

```python
class PageType(str, Enum):
    HERO = "hero"
    PROCESS = "process"

class PageClassification(BaseModel):
    page_num: int
    page_type: PageType             # 聚合自该页所有图片中最高优先级的分类
    images: list[ImageInfo]         # 该页包含的所有图片
    has_vector_content: bool        # 该页是否包含矢量绘图指令（线稿/hatch 等）
    has_text_content: bool          # 该页是否包含文字
    user_override: bool = False
```

### 4.3 CompressionConfig

```python
class CompressionConfig(BaseModel):
    target_size_mb: float               # 目标大小: 5.0 / 10.0 / 15.0 / 20.0
    tolerance_mb: float = 0.3           # 允许误差, 最终大小在 [target - tolerance, target] 视为成功

    # --- PPI 策略 (优先于 quality 调整) ---
    max_ppi: int = 250                  # 超过此值的图片先降 PPI
    hero_min_ppi: int = 180             # hero 图片 PPI 下限
    process_min_ppi: int = 120          # process 图片 PPI 下限

    # --- JPEG quality 策略 (PPI 降完后再调) ---
    hero_max_quality: int = 92          # hero 图片 quality 上限
    process_max_quality: int = 75       # process 图片 quality 上限
    hero_min_quality: int = 55          # hero 图片 quality 下限 (大图)
    process_min_quality: int = 30       # process 图片 quality 下限

    # --- quality floor 按显示面积分档 ---
    # display_ratio > 0.4  -> quality floor = hero/process_min_quality (上面的值)
    # display_ratio 0.15~0.4 -> quality floor = 上面的值 - 10
    # display_ratio < 0.15 -> quality floor = 25 (统一最低)
    small_image_quality_floor: int = 25

    # --- 权重 ---
    hero_label_weight: float = 1.0
    process_label_weight: float = 0.4
    large_size_weight: float = 1.0      # display_ratio > 0.4
    medium_size_weight: float = 0.6     # display_ratio 0.15~0.4
    small_size_weight: float = 0.3      # display_ratio < 0.15

    # --- 二分搜索 ---
    max_iterations_per_image: int = 8   # 单张图片的 quality 二分搜索最大轮次
    max_global_adjust_rounds: int = 3   # 全局校验微调最大轮次

    # --- 保存选项 ---
    garbage_level: int = 4              # PDF 垃圾回收级别
    deflate: bool = True                # 对所有流启用 zlib 压缩
```

### 4.4 JobState (in-memory, FastAPI 层用)

```python
from datetime import datetime

class JobStatus(str, Enum):
    RECEIVED = "received"
    CLASSIFYING = "classifying"
    AWAITING_REVIEW = "awaiting_review"
    COMPRESSING = "compressing"
    COMPLETE = "complete"
    FAILED = "failed"

class Job(BaseModel):
    id: str                         # UUID4
    status: JobStatus
    input_path: str                 # 本地临时文件路径
    output_path: str | None = None
    target_size_mb: float
    classifications: list[PageClassification] = []
    # 图片级缩略图: {xref: thumbnail_path}
    image_thumbnails: dict[int, str] = {}
    # 页面级缩略图用于整体预览
    page_thumbnails: list[str] = []
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
```

### 4.5 日志格式 (JSONL)

**位置**: `data/logs/YYYY-MM-DD.jsonl`

每处理完一个 job（不管成功失败）追加一行：

```json
{
  "timestamp": "2026-07-01T14:23:00Z",
  "job_id": "abc-123",
  "input_hash": "sha256:...",
  "input_size_bytes": 45231000,
  "input_page_count": 32,
  "total_images": 87,
  "non_image_overhead_bytes": 2340000,
  "target_size_mb": 15.0,
  "final_size_bytes": 14876000,
  "duration_seconds": 47.3,
  "image_classifications": [
    {"xref": 12, "page": 1, "ai_type": "hero", "user_type": "hero", "confidence": 0.87, "display_ratio": 0.52, "original_kb": 3200, "final_kb": 890},
    {"xref": 15, "page": 1, "ai_type": "process", "user_type": "process", "confidence": 0.73, "display_ratio": 0.08, "original_kb": 450, "final_kb": 120}
  ],
  "ppi_reductions": 23,
  "images_skipped": 5,
  "status": "success",
  "error": null,
  "user_agent_hash": "sha256:..."
}
```

**隐私**：不记录 IP,不记录用户名,PDF hash 用于去重但不存原文件长期。

---

## 5. 核心算法

### 5.0 设计原则

1. **不整页栅格化**：在原始 PDF 结构上操作,只替换嵌入图片对象,文字和矢量完全不动。
2. **图片级精度**：分类、预算分配、压缩都以单张嵌入图片为单位,不以页面为单位。
3. **先降 PPI,后降 quality**：PPI 过高时优先降分辨率（视觉退化温和）,PPI 到下限后再调 JPEG quality（伪影更刺眼）。
4. **在限制内最大化质量**：目标不是"尽可能小",而是"刚好塞进限制,把剩余空间全部还给画质"。

### 5.1 第一步：扫描 — 提取图片清单 + 测量开销

**输入**：PDF 文件路径
**输出**：`list[ImageInfo]` + `non_image_overhead_bytes: int`

```python
def scan_pdf(doc: fitz.Document) -> tuple[list[ImageInfo], int]:
    """
    遍历每一页,提取所有嵌入图片的元信息。
    同时计算非图片部分的固定开销（文字+矢量+字体+元数据）。
    """
    all_images: list[ImageInfo] = []
    seen_xrefs: set[int] = set()    # 去重: 同一图片被多页引用时只记一次
    total_image_bytes = 0

    for page_num, page in enumerate(doc, start=1):
        page_rect = page.rect
        page_area = abs(page_rect)  # 页面面积 (pt^2)

        for img_tuple in page.get_images(full=True):
            xref = img_tuple[0]
            if xref in seen_xrefs:
                continue
            seen_xrefs.add(xref)

            img_data = doc.extract_image(xref)
            raw_bytes = img_data["image"]
            width = img_data["width"]
            height = img_data["height"]
            ext = img_data["ext"]

            # 获取图片在页面上的显示区域
            img_rects = page.get_image_rects(xref)
            if not img_rects:
                continue
            display_rect = img_rects[0]  # 取第一个显示实例
            display_area = abs(display_rect)
            display_ratio = display_area / page_area if page_area > 0 else 0

            # 计算有效 PPI
            display_width_pt = display_rect.width
            display_width_inches = display_width_pt / 72.0
            effective_ppi = width / display_width_inches if display_width_inches > 0 else 0

            info = ImageInfo(
                xref=xref,
                page_num=page_num,
                original_bytes=len(raw_bytes),
                pixel_width=width,
                pixel_height=height,
                format=ext,
                display_rect=(display_rect.x0, display_rect.y0, display_rect.x1, display_rect.y1),
                display_ratio=display_ratio,
                effective_ppi=effective_ppi,
            )
            all_images.append(info)
            total_image_bytes += len(raw_bytes)

    file_total_bytes = os.path.getsize(doc.name)
    non_image_overhead = file_total_bytes - total_image_bytes

    return all_images, max(non_image_overhead, 0)
```

**注意**：
- 同一张图片可能被多页引用（共享 xref）,用 `seen_xrefs` 去重,只压缩一次。
- `non_image_overhead` 是估算值,实际保存后因为 deflate/garbage 会变,后面有全局校验兜底。

### 5.2 第二步：分类 — 图片级 hero/process

**输入**：每张图片的原始像素数据 + ImageInfo
**输出**：每张 ImageInfo 的 classification 和 confidence 被填充

分类信号（按权重组合）：

1. **显示面积** (`display_ratio`)：
   - `> 0.4` → 强 hero 信号 (+0.3)
   - `0.15 ~ 0.4` → 弱 hero 信号 (+0.1)
   - `< 0.15` → process 信号 (-0.1)

2. **颜色熵** (`color_entropy`)：
   - 转 HSV,取 H 通道 histogram（bins=32）,计算 Shannon entropy
   - 高熵（彩色丰富）→ hero 信号
   - 低熵（单色/灰度）→ process 信号

3. **边缘密度** (`edge_density`)：
   - 灰度 → Canny(50, 150) → 边缘像素占比
   - 适中（0.05~0.15）→ 可能是渲染图
   - 过高（>0.2）→ 可能是线稿/草图 → process 信号
   - 过低（<0.02）→ 可能是纯色/简单图 → process 信号

4. **分辨率** (`effective_ppi`)：
   - 高 PPI（>250）→ 更可能是精心准备的 hero 图
   - 低 PPI（<100）→ 更可能是随手截图 → process 信号

```python
def classify_image(image_array: np.ndarray, info: ImageInfo) -> tuple[PageType, float]:
    """
    对单张图片进行 hero/process 分类。
    image_array: (H, W, 3) uint8 RGB
    """
    score = 0.0

    # 1. 显示面积信号
    if info.display_ratio > 0.4:
        score += 0.3
    elif info.display_ratio > 0.15:
        score += 0.1
    else:
        score -= 0.1

    # 2. 颜色熵
    hsv = cv2.cvtColor(image_array, cv2.COLOR_RGB2HSV)
    h_hist = cv2.calcHist([hsv], [0], None, [32], [0, 180])
    h_hist = h_hist.flatten() / h_hist.sum()
    h_hist = h_hist[h_hist > 0]
    color_entropy = -np.sum(h_hist * np.log2(h_hist))
    # 归一化到 0~1 (max entropy for 32 bins = 5.0)
    normalized_entropy = min(color_entropy / 5.0, 1.0)
    score += normalized_entropy * 0.3  # max +0.3

    # 3. 边缘密度
    gray = cv2.cvtColor(image_array, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    edge_density = np.sum(edges > 0) / edges.size
    if 0.05 <= edge_density <= 0.15:
        score += 0.2   # 适中 = 渲染图特征
    elif edge_density > 0.2:
        score -= 0.1   # 过密 = 线稿/草图
    else:
        score -= 0.05  # 过疏 = 简单图

    # 4. 分辨率信号
    if info.effective_ppi > 250:
        score += 0.1
    elif info.effective_ppi < 100:
        score -= 0.1

    # 决策
    THRESHOLD = 0.35  # 放在 config.py
    if score >= THRESHOLD:
        page_type = PageType.HERO
        confidence = min(1.0, 0.5 + (score - THRESHOLD) / 0.6)
    else:
        page_type = PageType.PROCESS
        confidence = min(1.0, 0.5 + (THRESHOLD - score) / 0.6)

    return page_type, round(confidence, 3)
```

**⚠️ 所有阈值和系数（THRESHOLD=0.35、+0.3/+0.1/-0.1 等）必须放在 `config.py`,不可 hardcode。后续用真实作品集数据校准。**

### 5.3 第三步：预算分配

**输入**：`list[ImageInfo]`（已分类）+ `non_image_overhead_bytes` + `CompressionConfig`
**输出**：每张图片的 `target_bytes` 和 `target_ppi`

```python
def allocate_budget(
    images: list[ImageInfo],
    overhead_bytes: int,
    config: CompressionConfig,
) -> list[dict]:
    """
    返回 [{xref, target_bytes, target_ppi, quality_floor, quality_ceiling, skip}, ...]
    """
    target_total = config.target_size_mb * 1024 * 1024
    safety_margin = 0.05 * target_total  # 5% 安全余量给 deflate 误差
    image_budget = target_total - overhead_bytes - safety_margin

    if image_budget <= 0:
        raise CompressionError(
            "Non-image content alone exceeds target size. "
            "Target too small for this PDF."
        )

    allocations = []

    # --- Pass 1: 计算权重, 标记 PPI 目标, 计算 quality floor ---
    for img in images:
        # 权重 = 分类标签因子 x 显示面积因子
        label_w = config.hero_label_weight if img.classification == PageType.HERO else config.process_label_weight

        if img.display_ratio > 0.4:
            size_w = config.large_size_weight
        elif img.display_ratio > 0.15:
            size_w = config.medium_size_weight
        else:
            size_w = config.small_size_weight

        weight = label_w * size_w

        # PPI 目标: 如果当前 PPI 超过 max_ppi, 先降
        if img.effective_ppi > config.max_ppi:
            if img.classification == PageType.HERO:
                target_ppi = max(config.hero_min_ppi, config.max_ppi)
            else:
                target_ppi = max(config.process_min_ppi, config.max_ppi)
        else:
            target_ppi = img.effective_ppi  # 不动

        # quality floor 按显示面积分档
        if img.classification == PageType.HERO:
            base_floor = config.hero_min_quality
            quality_ceiling = config.hero_max_quality
        else:
            base_floor = config.process_min_quality
            quality_ceiling = config.process_max_quality

        if img.display_ratio > 0.4:
            quality_floor = base_floor
        elif img.display_ratio > 0.15:
            quality_floor = base_floor - 10
        else:
            quality_floor = config.small_image_quality_floor

        allocations.append({
            "xref": img.xref,
            "weight": weight,
            "target_ppi": target_ppi,
            "current_ppi": img.effective_ppi,
            "quality_floor": quality_floor,
            "quality_ceiling": quality_ceiling,
            "original_bytes": img.original_bytes,
            "classification": img.classification,
            "skip": False,
            "target_bytes": 0,
        })

    # --- Pass 2: 按权重分配预算 ---
    total_weight = sum(a["weight"] for a in allocations)

    for a in allocations:
        a["target_bytes"] = int(image_budget * (a["weight"] / total_weight))

    # --- Pass 3: 处理 "不用压" 和重新分配 ---
    # 如果某张图的 target_bytes >= original_bytes, 跳过压缩, 释放多余预算
    redistributed = True
    while redistributed:
        redistributed = False
        surplus = 0

        for a in allocations:
            if not a["skip"] and a["target_bytes"] >= a["original_bytes"]:
                surplus += a["target_bytes"] - a["original_bytes"]
                a["target_bytes"] = a["original_bytes"]
                a["skip"] = True
                redistributed = True

        # 把多余预算按权重重新分配给未跳过的图片
        if surplus > 0:
            active = [a for a in allocations if not a["skip"]]
            active_weight = sum(a["weight"] for a in active)
            if active_weight > 0:
                for a in active:
                    a["target_bytes"] += int(surplus * (a["weight"] / active_weight))

    return allocations
```

### 5.4 第四步：逐图压缩 + 写回

**输入**：原始 PDF Document + allocations
**输出**：修改后的 Document（in-place）

对每张需要压缩的图片：

```python
def compress_single_image(
    doc: fitz.Document,
    xref: int,
    target_bytes: int,
    target_ppi: float,
    current_ppi: float,
    quality_floor: int,
    quality_ceiling: int,
    max_iterations: int = 8,
) -> int:
    """
    压缩单张图片并写回 PDF。返回最终字节数。

    策略:
    1. 如果 current_ppi > target_ppi, 先降分辨率
    2. 二分搜索 JPEG quality 使字节数接近 target_bytes
    搜索方向: 在 target_bytes 内找最高 quality（最大化质量）
    """
    img_data = doc.extract_image(xref)
    pil_img = Image.open(io.BytesIO(img_data["image"]))

    # --- Step 1: 降分辨率 (如果需要) ---
    if current_ppi > target_ppi and target_ppi > 0:
        scale = target_ppi / current_ppi
        new_w = max(1, int(pil_img.width * scale))
        new_h = max(1, int(pil_img.height * scale))
        pil_img = pil_img.resize((new_w, new_h), Image.LANCZOS)

    # 确保 RGB 模式
    if pil_img.mode not in ("RGB", "L"):
        pil_img = pil_img.convert("RGB")

    # --- Step 2: 二分搜索 JPEG quality ---
    lo, hi = quality_floor, quality_ceiling
    best_buf = None
    best_size = float("inf")

    for _ in range(max_iterations):
        q = (lo + hi) // 2
        buf = io.BytesIO()
        pil_img.save(buf, format="JPEG", quality=q, optimize=True, subsampling="4:2:0")
        size = buf.tell()

        if size <= target_bytes:
            best_buf = buf.getvalue()
            best_size = size
            lo = q + 1     # 尝试更高质量
        else:
            hi = q - 1     # 需要更低质量

        if lo > hi:
            break

    # 如果二分搜索没找到 <= target 的, 用 quality_floor 的结果
    if best_buf is None:
        buf = io.BytesIO()
        pil_img.save(buf, format="JPEG", quality=quality_floor, optimize=True, subsampling="4:2:0")
        best_buf = buf.getvalue()
        best_size = len(best_buf)

    # --- Step 3: 写回 PDF ---
    doc.update_stream(xref, best_buf)
    # 更新 xref 的元信息, 标记为 JPEG
    doc.xref_set_key(xref, "Filter", "/DCTDecode")
    doc.xref_set_key(xref, "ColorSpace", "/DeviceRGB")
    if pil_img.mode == "L":
        doc.xref_set_key(xref, "ColorSpace", "/DeviceGray")

    return best_size
```

**注意**：
- 二分搜索方向是"在 target_bytes 内找最高 quality",不是找最小文件。这保证了在限制内最大化质量。
- `subsampling="4:2:0"` 对照片/渲染图是最佳性价比,色度子采样省字节且肉眼几乎无感。
- 同一 xref 被多页引用时只压缩一次（scan 阶段已去重）。

### 5.5 第五步：全局校验 + 质量回调

**目的**：因为 `non_image_overhead` 是估算值,`deflate` 后的实际大小可能偏差,需要校验。

```python
def global_adjust(
    doc: fitz.Document,
    allocations: list[dict],
    config: CompressionConfig,
) -> bytes:
    """
    保存 PDF,检查最终大小,如果需要则微调。
    """
    for round_num in range(config.max_global_adjust_rounds):
        pdf_bytes = doc.tobytes(
            garbage=config.garbage_level,
            deflate=config.deflate,
        )
        size_mb = len(pdf_bytes) / (1024 * 1024)
        target = config.target_size_mb
        tolerance = config.tolerance_mb

        if target - tolerance <= size_mb <= target:
            # 命中目标区间
            return pdf_bytes

        if size_mb > target:
            # 超了: 从权重最低的图片开始,再压一轮
            active = sorted(
                [a for a in allocations if not a["skip"]],
                key=lambda a: a["weight"]
            )
            for a in active[:5]:  # 最多调 5 张
                new_target = int(a["target_bytes"] * 0.75)
                compress_single_image(
                    doc, a["xref"], new_target,
                    a["target_ppi"], a["current_ppi"],
                    a["quality_floor"], a["quality_ceiling"],
                )
                a["target_bytes"] = new_target
            continue

        if size_mb < target - tolerance:
            # 太小: 从权重最高的 hero 图开始,提高质量
            heroes = sorted(
                [a for a in allocations if not a["skip"]],
                key=lambda a: a["weight"],
                reverse=True
            )
            surplus_bytes = int((target - tolerance - size_mb) * 1024 * 1024)
            for a in heroes[:5]:
                bonus = surplus_bytes // 5
                new_target = a["target_bytes"] + bonus
                compress_single_image(
                    doc, a["xref"], new_target,
                    a["target_ppi"], a["current_ppi"],
                    a["quality_floor"], a["quality_ceiling"],
                )
                a["target_bytes"] = new_target
            continue

    # 兜底: 返回最后一次的结果
    return doc.tobytes(garbage=config.garbage_level, deflate=config.deflate)
```

### 5.6 总编排 (pipeline.py)

```python
def compress_portfolio(
    input_path: str,
    config: CompressionConfig,
    user_overrides: dict[int, PageType] | None = None,  # {xref: PageType}
) -> tuple[bytes, dict]:
    """
    主入口。

    Phase A (分类, 前端轮询 awaiting_review 前):
        1. scan_pdf -> 图片清单 + 非图片开销
        2. classify_images -> 每张图片标 hero/process
        3. 聚合为 PageClassification 列表
        4. 返回分类结果, 等用户 review

    Phase B (压缩, 用户 confirm 后):
        5. 应用 user_overrides (按 xref 覆盖分类)
        6. allocate_budget -> 每张图片的目标字节数 + 目标 PPI
        7. 逐图 compress_single_image
        8. global_adjust -> 校验 + 微调
        9. 返回最终 PDF bytes + stats
    """
```

### 5.7 与旧算法的关键差异总结

| 维度 | 旧算法 (v1) | 新算法 (v2) |
|------|------------|------------|
| 压缩对象 | 整页栅格化位图 | 每张嵌入图片单独压缩 |
| 文字/矢量 | 被拍成图片,不可逆损失 | 完全不动,保持原始清晰度 |
| 分类粒度 | 页面级 hero/process | 图片级 hero/process |
| 用户 review 粒度 | 页面级 toggle | 图片级 toggle |
| 体积控制维度 | 仅 JPEG quality | PPI（优先）+ JPEG quality + subsampling |
| 搜索方向 | "找到刚好低于目标的 quality" | "在目标字节数内找最高 quality" |
| PDF 结构 | 重建新 PDF | 原地修改,结构保留 |
| 保存优化 | 无 | garbage=4 + deflate + 字体子集化 |
| 全局校验 | 无 | 有,超了再压 / 小了回调质量 |

---

## 6. API 契约

### 6.1 POST `/jobs`

**用途**：上传 PDF,创建 job

**Request**：
- `multipart/form-data`
- Field `file`: PDF 文件
- Field `target_size_mb`: float (5.0 / 10.0 / 15.0 / 20.0)

**Response 200**：
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "received"
}
```

**Response 400**: 文件不是 PDF、超过 100MB、target_size 不合法
**Response 429**: 超过 IP 限流

### 6.2 GET `/jobs/{id}`

**用途**：轮询 job 状态

**Response 200**（不同状态返回不同字段）：

```json
// classifying 阶段
{ "job_id": "...", "status": "classifying" }

// awaiting_review 阶段 (图片级)
{
  "job_id": "...",
  "status": "awaiting_review",
  "pages": [
    {
      "page_num": 1,
      "page_type": "hero",
      "images": [
        {"xref": 12, "classification": "hero", "confidence": 0.87, "display_ratio": 0.52, "thumbnail_url": "/jobs/.../img_thumb/12"},
        {"xref": 15, "classification": "process", "confidence": 0.73, "display_ratio": 0.08, "thumbnail_url": "/jobs/.../img_thumb/15"}
      ]
    },
    {
      "page_num": 2,
      "page_type": "process",
      "images": [
        {"xref": 20, "classification": "process", "confidence": 0.91, "display_ratio": 0.35, "thumbnail_url": "/jobs/.../img_thumb/20"}
      ]
    }
  ],
  "page_thumbnails": ["/jobs/.../thumb/1", "/jobs/.../thumb/2"]
}

// compressing 阶段
{ "job_id": "...", "status": "compressing" }

// complete
{
  "job_id": "...",
  "status": "complete",
  "download_url": "/jobs/.../download",
  "final_size_mb": 14.7
}

// failed
{ "job_id": "...", "status": "failed", "error": "..." }
```

**Response 404**: job_id 不存在或已过期

### 6.3 POST `/jobs/{id}/confirm`

**用途**：用户 review 完分类,提交修改并开始压缩

**Request**（图片级,只传被用户修改过的图片）：
```json
{
  "image_overrides": [
    {"xref": 15, "classification": "hero"},
    {"xref": 20, "classification": "hero"}
  ]
}
```

未传的图片保持 AI 分类结果。

**Response 200**：
```json
{ "job_id": "...", "status": "compressing" }
```

**Response 409**: job 不在 awaiting_review 状态

### 6.4 GET `/jobs/{id}/thumb/{page_num}`

**用途**：返回某一页的整页缩略图（JPEG,~200px 宽）

**Response 200**: `image/jpeg`

### 6.5 GET `/jobs/{id}/download`

**用途**：下载压缩结果

**Response 200**: `application/pdf`

### 6.6 GET `/jobs/{id}/img_thumb/{xref}`

**用途**：返回单张嵌入图片的缩略图（JPEG,~300px 宽边）

**Response 200**: `image/jpeg`

---

## 7. 分阶段实施

### Phase 0: CLI 核心（优先实现,不做以下任何一步之前不要开始下一 phase）

**目标**：一个可以在命令行跑的 `compress` 工具。

- [ ] Task 0.1: 项目初始化（`pyproject.toml`, `.gitignore`, 目录结构）
- [ ] Task 0.2: 实现 `pdf_io.py`（PDF 图片扫描：遍历页面提取所有嵌入图片的 ImageInfo + 计算非图片开销；图片提取/写回：extract_image、update_stream）
- [ ] Task 0.3: 实现 `classifier.py`（图片级特征提取：颜色熵、边缘密度、显示面积、PPI；图片级 hero/process 分类）
- [ ] Task 0.4: 实现 `compress.py`（预算分配算法：权重计算 + 按权重分配 + 跳过/重分配循环；单图压缩：PPI 降级 + JPEG quality 二分搜索；全局校验 + 质量回调）
- [ ] Task 0.5: 实现 `pipeline.py`（编排 Phase A 分类 + Phase B 压缩两阶段流程）
- [ ] Task 0.6: 实现 `cli.py`（argparse,`python -m compressor input.pdf --target 15`）
- [ ] Task 0.7: 写 pytest 单元测试（覆盖：图片级分类、预算分配逻辑、PPI 降级、单图压缩、全局校验）
- [ ] Task 0.8: 用真实作品集测试（找 3-5 个 PDF 放 `tests/fixtures/`）,记录压缩效果

**验收标准**：能对一个 30 页的 InDesign 导出 PDF 作品集,压缩到指定大小（误差 < 0.3MB）,文字保持矢量清晰,耗时 < 60 秒。

### Phase 1: FastAPI 服务层

**目标**：HTTP 接口暴露 CLI 能力,支持两阶段交互（图片级 review）。

- [ ] Task 1.1: `server/main.py` FastAPI app,CORS 配置
- [ ] Task 1.2: `server/jobs.py` in-memory JobManager（dict + threading.Lock）
- [ ] Task 1.3: 实现 6 个 endpoint（POST /jobs, GET /jobs/{id}, POST /jobs/{id}/confirm, GET page thumbnail, GET image thumbnail, GET download）
- [ ] Task 1.4: 后台任务用 FastAPI `BackgroundTasks` 或 `asyncio.create_task`,分类和压缩不阻塞请求
- [ ] Task 1.5: slowapi 限流（每 IP 每小时 5 次上传）
- [ ] Task 1.6: 匿名日志写入 JSONL
- [ ] Task 1.7: `scripts/cleanup.py` 清理 1h 前的临时文件
- [ ] Task 1.8: 集成测试（用 httpx 测完整 flow）

**验收标准**：用 curl / Postman 能跑通完整流程（上传 → 轮询 → 图片级 review → 确认 → 下载）。

### Phase 2: Next.js 前端

**目标**：能给非技术用户用的 web 界面。

- [ ] Task 2.1: `create-next-app` 初始化,配置 Tailwind + shadcn/ui
- [ ] Task 2.2: Landing page（简单介绍 + 上传按钮）
- [ ] Task 2.3: 上传组件（拖拽 + 点击选择,支持 PDF only,大小校验）
- [ ] Task 2.4: 目标大小选择器（5/10/15/20MB + 自定义）
- [ ] Task 2.5: 进度轮询组件（useEffect + setInterval）
- [ ] Task 2.6: Review 页面（按页展开,每页显示整页缩略图 + 该页所有图片的单独缩略图和 hero/process toggle）
- [ ] Task 2.7: 下载页面（显示最终大小 + 下载按钮）
- [ ] Task 2.8: 错误处理和 loading 状态

**验收标准**：朋友能在没有你指导的情况下完成上传 → 图片级 review → 下载全流程。

### Phase 3: Cloudflare Tunnel 部署

- [ ] Task 3.1: 本地跑通 cloudflared tunnel,拿到公网 URL
- [ ] Task 3.2: Next.js 部署到 Vercel,环境变量配置 FastAPI URL
- [ ] Task 3.3: 端到端测试

---

## 8. 强制约束（Codex 必须遵守）

### 8.1 一定要做的

1. **每个 module 顶部写 docstring**,说明用途、输入、输出
2. **所有函数标注 type hints**（Python 3.11 style: `list[int]` 而不是 `List[int]`）
3. **用 Pydantic 而不是 dataclass**（需要序列化）
4. **异常要用自定义类**（`CompressionError`, `ClassificationError`, `PDFParseError`）,不用裸 `Exception`
5. **常量放 `config.py`**,不要 hardcode 在业务代码里
6. **每完成一个 Task,在 `PROGRESS.md` 里打勾并简短记录做了什么**
7. **写代码前先看 `PLANNING.md`**,不确定的时候问,不要自由发挥

### 8.2 一定不要做的

1. **不要引入 non-goals 里的功能**（账户、支付、DB、Celery 等）
2. **不要装 requirements.txt 里没写的库**,需要新库先问
3. **不要写 500+ 行的单个文件**,超过就拆
4. **不要写没有测试的复杂逻辑**（classifier、compress 必须有测试）
5. **不要用 emoji 在 commit message 或代码注释里**
6. **不要生成大段 TODO 注释后就交差**,要么实现要么明确标记 out-of-scope
7. **不要改 `PLANNING.md`**,如果发现需要改设计,先和我讨论

### 8.3 代码风格

- Python: black + ruff 默认配置
- 命名: `snake_case` 函数变量,`PascalCase` 类,`SCREAMING_SNAKE_CASE` 常量
- 注释用中英混合都可以,但公共 API 的 docstring 用英文
- 不写多余注释（比如 `# increment counter` 在 `counter += 1` 前面）

---

## 9. 开发工作流

### 9.1 Codex 每次开工前

1. 读 `PLANNING.md` 相关章节
2. 读 `PROGRESS.md` 看已完成什么
3. 确认当前 Task 的输入输出契约
4. 写代码 + 测试
5. 更新 `PROGRESS.md`

### 9.2 遇到设计不清晰时

- **不要自作主张扩大范围**
- 在 `PROGRESS.md` 里的 "Questions" 章节记录问题,等我回答
- 阻塞任务先跳过,做下一个能推进的

### 9.3 提交粒度

- 每完成一个 Task 提交一次
- Commit message 格式: `[Phase X.Y] 简短描述` 例如 `[Phase 0.3] Implement image-level heuristic classifier`

---

## 10. 测试数据准备

在开始 Task 0.8 之前,我（user）会准备：

- `tests/fixtures/portfolio_small.pdf` (10页,~20MB)
- `tests/fixtures/portfolio_medium.pdf` (30页,~80MB)
- `tests/fixtures/portfolio_large.pdf` (60页,~200MB)
- `tests/fixtures/text_heavy.pdf` (10页,主要是文字)
- `tests/fixtures/image_heavy.pdf` (10页,全是渲染图)

如果这些没准备好,Codex 可以用 PyMuPDF 从图片生成一个合成 PDF 做基础测试,但真实作品集测试要等我准备。

---

## 11. 提示词模板（给 Codex 用）

我在 VSCode 里唤起 Codex 时,建议这样开头：

```
读 PLANNING.md 里 Phase [X] Task [Y] 的要求。
先给我一个 3-5 句话的实现计划,不要写代码。
我确认后你再写。
```

或者具体一点：

```
按 PLANNING.md Task 0.3 的要求实现 src/compressor/classifier.py。
约束：只用 OpenCV + numpy,不引入新依赖。
先展示函数 signature,我 review 后你再填函数体。
```

---

## 附录 A: MVP 之后的路线图（仅供参考,先不做）

- Phase 4: 引入 Gemma 4 视觉模型做低置信度图片的精分类
- Phase 5: 用收集的数据训练一个专用的分类模型（可能是 CLIP + 小 MLP）
- Phase 6: Supabase Auth + 用户账户 + 压缩历史
- Phase 7: Stripe 支付 + 订阅制/按次付费
- Phase 8: 迁移 worker 到 Modal.com serverless GPU
- Phase 9: 开放 API 给第三方使用

**这些不在当前 spec 范围内,Codex 忽略。**

---

_End of PLANNING.md_
