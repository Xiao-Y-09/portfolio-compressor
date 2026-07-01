# AI Portfolio Compressor · MVP Development Spec

> 这是一份给 Codex(或任何 AI coding agent)读的 spec 文档。
> 目的:让 Codex 严格按照本文档实现,避免自由发挥导致偏离设计。
> Owner: Xiao Yang · 起草日期: 2026-07

---

## 0. 项目背景 (Context)

面向艺术生/设计师的 PDF 作品集智能压缩工具。

**核心差异化**:现有工具(Pi7、Imresizer、ToolShelf)都是"一刀切"降低全局质量,导致关键页面(effect 图、渲染图)和次要页面(草图、文字调研)被同等程度压缩。本工具通过**按页面重要性智能分配质量权重**,让关键页面保持高质量,次要页面容忍更多压缩,总大小达到目标值。

**目标用户**:递交留学申请或求职时受限于 10MB/15MB/20MB 大小限制的艺术生/设计生。

---

## 1. MVP 范围 (Scope)

### 1.1 MVP 明确要做的

- [x] CLI 工具:输入 PDF + 目标大小 → 输出压缩 PDF
- [x] 基于 OpenCV 的启发式页面分类(hero vs process)
- [x] 二分搜索质量乘数,收敛到目标大小
- [x] FastAPI 服务层,包装 CLI 逻辑
- [x] 两阶段交互:分类完成 → 用户 review → 确认后压缩
- [x] 简单 Next.js 前端(上传、review、下载)
- [x] IP-based 限流
- [x] 匿名日志收集(用于后续训练更好的分类器)

### 1.2 MVP 明确不做的 (Non-Goals)

- [ ] **不做用户账户系统**(不用 Supabase Auth、不用 login)
- [ ] **不做支付**(不接 Stripe)
- [ ] **不做云数据库**(job 状态用 in-memory dict,进程重启丢失可接受)
- [ ] **不接 Gemma 视觉模型**(MVP 只用 OpenCV 启发式,Phase 2 才引入)
- [ ] **不做管理后台、数据分析 dashboard**
- [ ] **不做作品集历史记录、多版本管理**
- [ ] **不做 SSE / WebSocket**(前端用 HTTP 轮询即可)
- [ ] **不做多语言 i18n**(先只有中文 UI)
- [ ] **不做花哨动画、复杂设计**(前端用 shadcn/ui 默认组件)

**⚠️ 如果 Codex 想给我加以上任何一项功能,拒绝并提示"这是 non-goal"。**

---

## 2. 技术栈约束

### 2.1 后端(必用)

- **Python**: 3.11+
- **Web framework**: FastAPI + Uvicorn
- **PDF 处理**: PyMuPDF (`import fitz`)
- **图像处理**: OpenCV (`cv2`) + Pillow (`PIL`)
- **限流**: slowapi
- **数据模型**: Pydantic v2
- **测试**: pytest
- **依赖管理**: `pyproject.toml` + `uv` (推荐) 或 `pip` + `requirements.txt`

### 2.2 前端(Phase 2 才写)

- **Framework**: Next.js 14+ App Router
- **UI**: Tailwind CSS + shadcn/ui
- **HTTP**: 原生 fetch(不用 axios、swr)
- **状态**: React useState(不用 Redux、Zustand)
- **文件**: TypeScript 严格模式

### 2.3 禁用的东西

- ❌ 不用 Django、Flask
- ❌ 不用 Celery、Redis、RabbitMQ(MVP 阶段用不上)
- ❌ 不用 SQLAlchemy、任何 ORM(job 状态在内存里,不需要 DB)
- ❌ 不用 pypdf、pdfplumber(用 PyMuPDF 一个库就够)
- ❌ 前端不用 UI 库以外的第三方(比如不装 framer-motion、react-dropzone)

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
│       ├── pdf_io.py              # PDF 拆页、组装
│       ├── classifier.py          # 页面分类(OpenCV 启发式)
│       ├── compress.py            # 单页压缩 + 二分搜索
│       ├── schemas.py             # Pydantic 数据模型
│       └── config.py              # 常量、阈值
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

### 4.1 PageClassification

```python
from enum import Enum
from pydantic import BaseModel

class PageType(str, Enum):
    HERO = "hero"           # 效果图、渲染图、关键作品展示
    PROCESS = "process"     # 草图、调研、文字说明

class PageFeatures(BaseModel):
    """OpenCV 提取的特征,用于分类"""
    color_entropy: float        # 直方图熵,颜色丰富度
    edge_density: float         # Canny 边缘密度
    image_area_ratio: float     # 图像区域占比(vs 白底+文字)
    text_area_ratio: float      # 文字区域占比

class PageClassification(BaseModel):
    page_num: int               # 1-indexed
    page_type: PageType
    confidence: float           # 0.0 ~ 1.0
    features: PageFeatures
    user_override: bool = False # 用户是否手动改过分类
```

### 4.2 CompressionConfig

```python
class CompressionConfig(BaseModel):
    target_size_mb: float           # 目标大小,如 15.0
    tolerance_mb: float = 0.5       # 允许误差,达到 [target-tolerance, target] 视为成功
    max_iterations: int = 8         # 二分搜索最大轮次
    
    # 基础质量(quality multiplier=1.0 时用)
    hero_base_quality: int = 90
    process_base_quality: int = 55
    
    # 质量下限(multiplier 最小时也不能低于这个)
    hero_min_quality: int = 60
    process_min_quality: int = 25
    
    # DPI 相关
    render_dpi: int = 200           # 页面渲染 DPI(影响输出清晰度)
```

### 4.3 JobState (in-memory, FastAPI 层用)

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
    thumbnails: list[str] = []      # 每页缩略图的本地路径
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
```

### 4.4 日志格式 (JSONL)

**位置**: `data/logs/YYYY-MM-DD.jsonl`

每处理完一个 job(不管成功失败)追加一行:

```json
{
  "timestamp": "2026-07-01T14:23:00Z",
  "job_id": "abc-123",
  "input_hash": "sha256:...",
  "input_size_bytes": 45231000,
  "input_page_count": 32,
  "target_size_mb": 15.0,
  "final_size_bytes": 14876000,
  "duration_seconds": 47.3,
  "classifications": [
    {"page": 1, "ai_type": "hero", "user_type": "hero", "confidence": 0.87},
    {"page": 2, "ai_type": "process", "user_type": "hero", "confidence": 0.52}
  ],
  "iterations_used": 5,
  "final_multiplier": 0.72,
  "status": "success",
  "error": null,
  "user_agent_hash": "sha256:..."
}
```

**隐私**:不记录 IP,不记录用户名,PDF hash 用于去重但不存原文件长期。

---

## 5. 核心算法

### 5.1 页面分类(启发式规则)

**输入**:PDF 单页渲染成的 numpy array (H, W, 3), uint8, RGB

**特征提取步骤**:

1. **color_entropy**: 
   - 转 HSV,取 H 通道 histogram(bins=32)
   - 归一化后计算 Shannon entropy: `-sum(p * log2(p))`
   - 范围大约 0-5

2. **edge_density**:
   - 灰度化 → Canny(threshold1=50, threshold2=150)
   - `edge_density = np.sum(edges > 0) / edges.size`
   - 范围 0-1

3. **image_area_ratio**:
   - 检测大面积连续非白区域(阈值化 + morphology closing)
   - 面积占比

4. **text_area_ratio**:
   - MSER 或 简单的水平投影检测文字行
   - MVP 阶段可以先跳过,设 0.0

**分类规则**(启发式,MVP 版本):

```python
def classify(features: PageFeatures) -> tuple[PageType, float]:
    # 高分区间 → 高置信度 hero
    hero_score = (
        features.color_entropy * 0.4 +
        features.edge_density * 30 +      # edge_density 值小,乘系数放大
        features.image_area_ratio * 0.5
    )
    
    # 阈值(先写死,后续用真实数据调)
    HERO_THRESHOLD = 2.5
    
    if hero_score > HERO_THRESHOLD:
        page_type = PageType.HERO
        confidence = min(1.0, (hero_score - HERO_THRESHOLD) / 2 + 0.5)
    else:
        page_type = PageType.PROCESS
        confidence = min(1.0, (HERO_THRESHOLD - hero_score) / 2 + 0.5)
    
    return page_type, confidence
```

**⚠️ 这些阈值(HERO_THRESHOLD=2.5、系数 0.4/30/0.5)都是初始猜测,必须放在 `config.py` 里方便调整。后续用真实作品集数据集校准。**

### 5.2 二分搜索压缩

**输入**:分类完成的页面列表 + 目标大小

**算法**:

```python
def binary_search_compress(
    pages: list[PageData],           # 每页的图像 + 分类
    config: CompressionConfig
) -> tuple[bytes, dict]:              # 返回 (compressed_pdf_bytes, stats)
    
    lo, hi = 0.0, 1.0
    best_result = None
    
    for iteration in range(config.max_iterations):
        multiplier = (lo + hi) / 2
        
        # 每页按类型计算实际 quality
        compressed_pages = []
        for page in pages:
            if page.classification.page_type == PageType.HERO:
                base = config.hero_base_quality
                floor = config.hero_min_quality
            else:
                base = config.process_base_quality
                floor = config.process_min_quality
            
            quality = max(floor, int(base * multiplier))
            compressed_pages.append(compress_page(page.image, quality))
        
        # 组装 PDF,测量大小
        pdf_bytes = assemble_pdf(compressed_pages)
        size_mb = len(pdf_bytes) / (1024 * 1024)
        
        # 收敛判断
        target = config.target_size_mb
        tolerance = config.tolerance_mb
        
        if size_mb > target:
            # 太大,降低 multiplier
            hi = multiplier
        elif size_mb < target - tolerance:
            # 太小(可以更高质量),提高 multiplier
            lo = multiplier
            best_result = (pdf_bytes, {"iterations": iteration + 1, "multiplier": multiplier, "size_mb": size_mb})
        else:
            # 命中目标区间
            return pdf_bytes, {"iterations": iteration + 1, "multiplier": multiplier, "size_mb": size_mb}
    
    # 收敛失败,返回最后一次刚好小于目标的
    if best_result:
        return best_result
    raise CompressionError("Failed to converge below target size")
```

**注意**:
- 每一轮迭代都要重新压缩所有页面,不能缓存前一轮结果(quality 变了图像就变了)
- 但页面渲染(PDF → image)只做一次,缓存在内存
- 通常 5-8 轮收敛

---

## 6. API 契约

### 6.1 POST `/jobs`

**用途**:上传 PDF,创建 job

**Request**:
- `multipart/form-data`
- Field `file`: PDF 文件
- Field `target_size_mb`: float (10.0 / 15.0 / 20.0)

**Response 200**:
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "received"
}
```

**Response 400**: 文件不是 PDF、超过 100MB、target_size 不合法
**Response 429**: 超过 IP 限流

### 6.2 GET `/jobs/{id}`

**用途**:轮询 job 状态

**Response 200**(不同状态返回不同字段):

```json
// classifying 阶段
{ "job_id": "...", "status": "classifying" }

// awaiting_review 阶段
{
  "job_id": "...",
  "status": "awaiting_review",
  "classifications": [
    {"page_num": 1, "page_type": "hero", "confidence": 0.87},
    ...
  ],
  "thumbnails": ["/jobs/.../thumb/1", "/jobs/.../thumb/2", ...]
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

**用途**:用户 review 完分类,提交修改并开始压缩

**Request**:
```json
{
  "classifications": [
    {"page_num": 1, "page_type": "hero"},
    {"page_num": 2, "page_type": "hero"},   // 用户改了这一页
    ...
  ]
}
```

**Response 200**:
```json
{ "job_id": "...", "status": "compressing" }
```

**Response 409**: job 不在 awaiting_review 状态

### 6.4 GET `/jobs/{id}/thumb/{page_num}`

**用途**:返回某一页的缩略图(JPEG,~200px 宽)

**Response 200**: `image/jpeg`

### 6.5 GET `/jobs/{id}/download`

**用途**:下载压缩结果

**Response 200**: `application/pdf`

---

## 7. 分阶段实施

### Phase 0: CLI 核心(优先实现,不做以下任何一步之前不要开始下一 phase)

**目标**:一个可以在命令行跑的 `compress` 工具。

- [ ] Task 0.1: 项目初始化(`pyproject.toml`, `.gitignore`, 目录结构)
- [ ] Task 0.2: 实现 `pdf_io.py`(PDF → 页面 image list; 页面 image list → PDF)
- [ ] Task 0.3: 实现 `classifier.py`(特征提取 + 启发式分类)
- [ ] Task 0.4: 实现 `compress.py`(单页 JPEG 压缩 + 二分搜索循环)
- [ ] Task 0.5: 实现 `pipeline.py`(编排整个流程)
- [ ] Task 0.6: 实现 `cli.py`(argparse,`python -m compressor input.pdf --target 15`)
- [ ] Task 0.7: 写 pytest 单元测试(至少覆盖 classifier 和 binary search)
- [ ] Task 0.8: 用真实作品集测试(找 3-5 个 PDF 放 `tests/fixtures/`),记录压缩效果

**验收标准**:能对一个 30 页的 PDF 作品集,压缩到指定大小(误差 < 0.5MB),耗时 < 60 秒。

### Phase 1: FastAPI 服务层

**目标**:HTTP 接口暴露 CLI 能力,支持两阶段交互。

- [ ] Task 1.1: `server/main.py` FastAPI app,CORS 配置
- [ ] Task 1.2: `server/jobs.py` in-memory JobManager(dict + threading.Lock)
- [ ] Task 1.3: 实现 5 个 endpoint(POST /jobs, GET /jobs/{id}, POST /jobs/{id}/confirm, GET thumbnail, GET download)
- [ ] Task 1.4: 后台任务用 FastAPI `BackgroundTasks` 或 `asyncio.create_task`,分类和压缩不阻塞请求
- [ ] Task 1.5: slowapi 限流(每 IP 每小时 5 次上传)
- [ ] Task 1.6: 匿名日志写入 JSONL
- [ ] Task 1.7: `scripts/cleanup.py` 清理 1h 前的临时文件
- [ ] Task 1.8: 集成测试(用 httpx 测完整 flow)

**验收标准**:用 curl / Postman 能跑通完整流程(上传 → 轮询 → 确认 → 下载)。

### Phase 2: Next.js 前端

**目标**:能给非技术用户用的 web 界面。

- [ ] Task 2.1: `create-next-app` 初始化,配置 Tailwind + shadcn/ui
- [ ] Task 2.2: Landing page(简单介绍 + 上传按钮)
- [ ] Task 2.3: 上传组件(拖拽 + 点击选择,支持 PDF only,大小校验)
- [ ] Task 2.4: 目标大小选择器(10/15/20MB + 自定义)
- [ ] Task 2.5: 进度轮询组件(useEffect + setInterval)
- [ ] Task 2.6: Review 页面(缩略图 grid + 每页 hero/process toggle)
- [ ] Task 2.7: 下载页面(显示最终大小 + 下载按钮)
- [ ] Task 2.8: 错误处理和 loading 状态

**验收标准**:朋友能在没有你指导的情况下完成上传 → 下载全流程。

### Phase 3: Cloudflare Tunnel 部署

- [ ] Task 3.1: 本地跑通 cloudflared tunnel,拿到公网 URL
- [ ] Task 3.2: Next.js 部署到 Vercel,环境变量配置 FastAPI URL
- [ ] Task 3.3: 端到端测试

---

## 8. 强制约束(Codex 必须遵守)

### 8.1 一定要做的

1. **每个 module 顶部写 docstring**,说明用途、输入、输出
2. **所有函数标注 type hints**(Python 3.11 style: `list[int]` 而不是 `List[int]`)
3. **用 Pydantic 而不是 dataclass**(需要序列化)
4. **异常要用自定义类**(`CompressionError`, `ClassificationError`, `PDFParseError`),不用裸 `Exception`
5. **常量放 `config.py`**,不要 hardcode 在业务代码里
6. **每完成一个 Task,在 `PROGRESS.md` 里打勾并简短记录做了什么**
7. **写代码前先看 `PLANNING.md`**,不确定的时候问,不要自由发挥

### 8.2 一定不要做的

1. **不要引入 non-goals 里的功能**(账户、支付、DB、Celery 等)
2. **不要装 requirements.txt 里没写的库**,需要新库先问
3. **不要写 500+ 行的单个文件**,超过就拆
4. **不要写没有测试的复杂逻辑**(classifier、compress 必须有测试)
5. **不要用 emoji 在 commit message 或代码注释里**
6. **不要生成大段 TODO 注释后就交差**,要么实现要么明确标记 out-of-scope
7. **不要改 `PLANNING.md`**,如果发现需要改设计,先和我讨论

### 8.3 代码风格

- Python: black + ruff 默认配置
- 命名: `snake_case` 函数变量,`PascalCase` 类,`SCREAMING_SNAKE_CASE` 常量
- 注释用中英混合都可以,但公共 API 的 docstring 用英文
- 不写多余注释(比如 `# increment counter` 在 `counter += 1` 前面)

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
- Commit message 格式: `[Phase X.Y] 简短描述` 例如 `[Phase 0.3] Implement heuristic classifier`

---

## 10. 测试数据准备

在开始 Task 0.8 之前,我(user)会准备:

- `tests/fixtures/portfolio_small.pdf` (10页,~20MB)
- `tests/fixtures/portfolio_medium.pdf` (30页,~80MB)
- `tests/fixtures/portfolio_large.pdf` (60页,~200MB)
- `tests/fixtures/text_heavy.pdf` (10页,主要是文字)
- `tests/fixtures/image_heavy.pdf` (10页,全是渲染图)

如果这些没准备好,Codex 可以用 PyMuPDF 从图片生成一个合成 PDF 做基础测试,但真实作品集测试要等我准备。

---

## 11. 提示词模板(给 Codex 用)

我在 VSCode 里唤起 Codex 时,建议这样开头:

```
读 PLANNING.md 里 Phase [X] Task [Y] 的要求。
先给我一个 3-5 句话的实现计划,不要写代码。
我确认后你再写。
```

或者具体一点:

```
按 PLANNING.md Task 0.3 的要求实现 src/compressor/classifier.py。
约束:只用 OpenCV + numpy,不引入新依赖。
先展示函数 signature,我 review 后你再填函数体。
```

---

## 附录 A: MVP 之后的路线图(仅供参考,先不做)

- Phase 4: 引入 Gemma 4 视觉模型做低置信度页面的精分类
- Phase 5: 用收集的数据训练一个专用的分类模型(可能是 CLIP + 小 MLP)
- Phase 6: Supabase Auth + 用户账户 + 压缩历史
- Phase 7: Stripe 支付 + 订阅制/按次付费
- Phase 8: 迁移 worker 到 Modal.com serverless GPU
- Phase 9: 开放 API 给第三方使用

**这些不在当前 spec 范围内,Codex 忽略。**

---

_End of PLANNING.md_
