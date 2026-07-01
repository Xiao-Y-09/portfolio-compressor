# ARCHITECTURE.md · Portfolio Compressor

> 这份文档回答一个问题:**新写的代码应该放在哪一层?**
> 
> 配合 PLANNING.md 使用。PLANNING.md 说"做什么",ARCHITECTURE.md 说"放哪里"。
> 
> Owner: Xiao Yang · 起草日期: 2026-07

---

## 1. 分层图

```
┌───────────────────────────────────────────────────────────────┐
│  Layer 4: web/  (Next.js 前端)                    Phase 2      │
│  浏览器中运行的 UI                                              │
│  文件: web/app/*, web/components/*                             │
│  依赖方向: HTTP 调 Layer 3, 不 import 任何 Python 代码           │
├───────────────────────────────────────────────────────────────┤
│  Layer 3: server/  (FastAPI HTTP 层)              Phase 1      │
│  HTTP endpoint · job 状态 · 限流 · 日志 · 缩略图                │
│  文件: server/main.py, server/jobs.py, server/routes.py, ...   │
│  允许 import:  Layer 2 (compressor.*), 标准库, fastapi/slowapi  │
│  禁止 import:  Layer 4                                          │
├───────────────────────────────────────────────────────────────┤
│  Layer 2: src/compressor/  (Python 库)            Phase 0 ✓    │
│  PDF 处理算法 · 分类 · 压缩 · pipeline · CLI                    │
│  文件: pdf_io.py, classifier.py, compress.py, pipeline.py,     │
│        cli.py, schemas.py, config.py, exceptions.py            │
│  允许 import:  标准库, PyMuPDF, OpenCV, PIL, numpy, pydantic    │
│  禁止 import:  Layer 3, Layer 4, FastAPI, 任何 HTTP 相关        │
├───────────────────────────────────────────────────────────────┤
│  Layer 1: 第三方 (PyMuPDF, OpenCV, PIL, FastAPI, ...)  已装好   │
│  由 pyproject.toml 管理                                         │
└───────────────────────────────────────────────────────────────┘
```

**唯一硬规则**:import 箭头**只能向下**,不能向上。

```
✅ 允许:  server/routes.py → from compressor.pipeline import compress_pdf
❌ 禁止:  src/compressor/pipeline.py → from server.jobs import JobManager
```

违反这条规则一次,项目就开始腐烂。任何时候看到 `src/compressor/` 里面 
`import fastapi` 或 `from server.*`,立刻回滚。

---

## 2. 每层的职责边界

### Layer 2: `src/compressor/` (Python 库)

**它做什么**:
- 把 PDF 拆成 numpy 数组
- 对数组做特征提取和分类
- 把数组压成 JPEG 字节
- 把 JPEG 字节组装回 PDF
- 编排上述步骤 (pipeline)
- 提供 CLI 入口

**它不做什么**:
- 不打日志(no `import logging`, no `print` 除了 CLI 层)
- 不管 HTTP、不管 request/response
- 不管用户身份、限流、账户
- 不管文件存哪里、什么时候删(只按参数读写指定路径)
- 不管并发调度、job 队列
- 不假设有网络

**它的合约**:
- 输入:文件路径 + 参数
- 输出:文件写入 + 返回 stats
- 失败:抛自定义异常 (`PDFParseError` / `ClassificationError` / `CompressionError` / `ValueError` / `OSError`)

这一层可以脱离所有上层单独跑,单独测试,单独发布(未来甚至可以 `pip install portfolio-compressor` 让别人用)。

### Layer 3: `server/` (FastAPI HTTP 层)

**它做什么**:
- 定义 HTTP endpoint,把 HTTP 请求翻译成 compressor.pipeline 调用
- 管理 job 状态(内存 dict),因为 pipeline 是一次性调用,没有"job"概念
- 提供两阶段异步交互(分类完暂停等待 review)
- 生成和返回缩略图
- 限流(slowapi)
- 打日志(anonymous JSONL)
- 清理过期临时文件

**它不做什么**:
- 不做 PDF 数值计算(全部委托给 Layer 2)
- 不管 UI 长什么样(不返回 HTML,只返回 JSON 和文件流)
- 不管数据库(MVP 无数据库,job 状态在内存里)
- 不管认证(MVP 无账户)

**它的合约**:
- 输入:HTTP request (multipart / JSON / URL param)
- 输出:HTTP response (JSON / 文件流)
- 内部错误:变成对应 HTTP 状态码 (400 / 404 / 409 / 429 / 500)

### Layer 4: `web/` (Next.js 前端)

**它做什么**:
- 用户界面:上传、进度、review、下载
- 状态管理:通过 HTTP 轮询 Layer 3 拿到 job 状态

**它不做什么**:
- 不做 PDF 处理(浏览器里不装 OpenCV/PyMuPDF)
- 不假设自己知道 pipeline 内部实现,只按 API 契约调
- 不存持久数据

---

## 3. 决策表:新功能应该加在哪一层?

| 你想加的东西 | 加在哪一层 | 具体文件建议 |
|-------------|-----------|-------------|
| 新的图像特征(比如"检测手绘线条") | Layer 2 | `classifier.py` + `config.py` |
| 新的压缩算法(比如"用 WebP 代替 JPEG") | Layer 2 | `compress.py` |
| 新的 PDF 输出格式(比如"输出成图片 zip") | Layer 2 | `pdf_io.py` + `pipeline.py` |
| 新的 CLI 参数(比如 `--verbose`) | Layer 2 | `cli.py` |
| 新的 HTTP endpoint(比如 `/jobs/{id}/preview`) | Layer 3 | `routes.py` |
| 修改 job 状态字段(加个 progress_percent) | Layer 2(schema) | `schemas.py` — Job model |
| 支持多个用户并发(用 Redis 代替 dict) | Layer 3 | 新增 `server/queue.py`,替换 `jobs.py` 内部实现,**API 不变** |
| 加认证(登录) | Layer 3 + Layer 4 | `server/auth.py` + Next.js middleware |
| 换前端框架(Remix / SvelteKit) | 只改 Layer 4 | Layer 3 完全不动 |
| 改换云存储(S3 代替本地磁盘) | Layer 3 | `server/storage.py`,不影响 Layer 2 |
| 加日志字段(比如记录 IP 段) | Layer 3 | `server/logging_config.py` |
| 训练一个新分类器 | Layer 2 | 新增 `classifier_ml.py`,pipeline 里 switch |
| 换 UI 样式 | 只改 Layer 4 | web/app/*.tsx + Tailwind |

**这张表告诉你两件事**:
1. Layer 2 和 Layer 3 应该**独立演化**。Layer 2 换算法不影响 Layer 3;Layer 3 换存储不影响 Layer 2。
2. 大部分"感觉难"的功能,拆到对应层后就变简单。

---

## 4. 具体到你现在的项目

### 当前状态(2026-07 Phase 1 开始时)

**Layer 2**:完成 ✓
```
src/compressor/
├── __init__.py
├── __main__.py         # python -m compressor 入口
├── cli.py              # argparse CLI
├── pipeline.py         # 主编排
├── pdf_io.py           # render / assemble PDF
├── classifier.py       # OpenCV 启发式分类
├── compress.py         # JPEG + 二分搜索
├── schemas.py          # Pydantic 模型
├── config.py           # 阈值常量
└── exceptions.py       # 自定义异常
```

**Layer 3**:开始
```
server/
├── __init__.py         # 空 package marker
├── main.py             # FastAPI app,CORS,lifespan (即将写)
├── jobs.py             # JobManager (即将写)
├── routes.py           # HTTP endpoints (Task 1.3)
├── ratelimit.py        # slowapi (Task 1.5)
├── logging_config.py   # 匿名 JSONL (Task 1.6)
└── (thumbnails.py?)    # 缩略图生成,可能拆出来
```

**Layer 4**:未开始
```
web/                    # Phase 2 才创建
```

### Job 模型放在哪一层?—— 一个关键决策

**Job 属于 Layer 2 的 schemas.py,不属于 server/**。原因:

- Job 引用了 PageClassification(Layer 2 的模型)
- 如果 Job 在 server/schemas.py,那么 Layer 2 的 pipeline 想返回 Job 时会形成上→下 import,违反规则
- 反过来 Job 在 Layer 2,server/ 可以自由 import,不违反任何规则

**通用原则**:**共享 schema 应该放在依赖树的最底层**,这样谁都能引用它。

### 一个反例:JobManager 放在 Layer 2 是错的

假设你想把 `JobManager` 挪到 `src/compressor/jobs.py`,理由是"job 是核心概念"。**这是错的**,因为:

- JobManager 有 threading.Lock,是运行时状态,不是数值算法
- JobManager 的存在意味着"多个并发请求",这是 HTTP 层的概念
- Layer 2 应该是无状态的,同一个输入永远给同一个输出

**规则**:**有全局可变状态的东西一定在 Layer 3 或以上**。Layer 2 只能有函数和不可变数据。

---

## 5. 何时该新增一层?何时该拆一层?

### 加一层的信号

如果你发现某一层做的事情已经**跨越两种关注点**,考虑拆一层:

- 例:如果 Layer 3 里既有 HTTP endpoint,又有大量文件存储/清理逻辑,且这些逻辑将来可能换实现(S3、Cloud Storage),就该拆一个 Layer 3.5:`server/storage.py`,负责所有文件 IO。routes.py 只调 storage 的方法,不直接 open 文件。
- 例:如果分类逻辑从"OpenCV 启发式"演化成"OpenCV + Gemma vision + ML 模型"三种共存,考虑拆一个 `classifier/` 子包:`classifier/heuristic.py`、`classifier/vision.py`、`classifier/router.py`(决定用哪个)。

### 不加层的信号

**每加一层都是一份心智负担和一层跳转**。以下情况**不要**加层:

- "只是想让代码看起来更工整" → 用文件夹分组就够,不需要抽象层
- "以后可能需要" → YAGNI,以后需要时再加
- "别人的项目都有" → 别人的项目大小和需求不一样

### 何时拆文件

一个文件超过 **300 行**或者内部有两个明显不同的关注点时,拆。
- 例:`server/routes.py` 如果超过 300 行,按资源拆:`routes/jobs.py`、`routes/health.py`、`routes/admin.py`。这不是新增层,只是同层内拆文件。

---

## 6. 依赖检查清单(每次 commit 前问自己)

- [ ] `src/compressor/` 里的所有 `.py` 有没有 `import fastapi` 或 `from server.*`?**如果有,回滚。**
- [ ] `server/` 里的所有 `.py` 有没有 `import` 什么 web/ 或 Next.js 相关?**如果有,回滚。**
- [ ] 新增的 schema 是否放在正确的层?通用共享 → `src/compressor/schemas.py`;只有 HTTP 层用 → `server/dto.py`(需要时再建)。
- [ ] 新增的常量/配置是否在正确层的 config?算法相关 → `src/compressor/config.py`;HTTP 层相关(比如 CORS 允许域名) → `server/config.py`(需要时再建)。
- [ ] 全局可变状态(锁、缓存、连接池)是否只出现在 Layer 3 或以上?

用 `grep` 快速自查:
```powershell
# Layer 2 里不该有的东西
Select-String -Path "src/compressor/*.py" -Pattern "fastapi|from server|import server"

# 如果输出为空,依赖方向就是干净的
```

---

## 7. 和 PLANNING.md 的关系

| 问题 | 查哪份文档 |
|-----|-----------|
| 我应该做什么 task? | PLANNING.md |
| 这个功能要不要做? | PLANNING.md 的 non-goals 章节 |
| 这个 task 完成后交付什么? | PLANNING.md 的验收标准 |
| 我写的这段代码放在哪个文件? | ARCHITECTURE.md 的决策表 |
| 我能不能 import 这个东西? | ARCHITECTURE.md 的依赖方向 |
| 我在写的代码是不是加错层了? | ARCHITECTURE.md 的层职责边界 |

**给 Codex 用的时候**:

```
读 PLANNING.md Task X.Y 和 ARCHITECTURE.md 第 3、4 节。
先给我 plan,不写代码。
```

Codex 就会:
- 从 PLANNING 拿到"做什么"和验收标准
- 从 ARCHITECTURE 拿到"放哪里"和"能 import 什么"
- 不会把 FastAPI 塞进 Layer 2,也不会把算法塞进 endpoint

---

## 附录 A:常见错误反例

### 反例 1:pipeline 里加日志

```python
# src/compressor/pipeline.py
import logging  # ❌ Layer 2 不打日志

logger = logging.getLogger(__name__)

def compress_pdf(...):
    logger.info(f"Compressing {input_path}")  # ❌
    ...
```

**为什么错**:Layer 2 应该无 IO 副作用(除了指定的文件读写)。日志是 IO,而且日志的形式(JSON / text / 结构化)是上层的关注点。

**正确做法**:pipeline 返回 stats,Layer 3 拿到 stats 后打日志。

### 反例 2:server/ 里做数值计算

```python
# server/routes.py
def compute_entropy(hist):  # ❌ 数值算法不应该在 Layer 3
    ...
```

**为什么错**:算法应该在 Layer 2,方便测试、复用、换实现。Layer 3 只做编排。

### 反例 3:pipeline 假设有 job_id

```python
# src/compressor/pipeline.py
def compress_pdf(job_id: str, ...):  # ❌ Layer 2 没有 job 概念
    ...
```

**为什么错**:job_id 是 HTTP 层的概念(多个并发请求需要区分)。Layer 2 单次调用完成任务,不需要区分身份。

**正确做法**:pipeline 就用 input_path/output_path。Layer 3 里 JobManager 记录"哪个 job_id 对应哪个 input_path"。

---

_End of ARCHITECTURE.md_
