# Telegram Image Understanding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Telegram Bot 接收照片，把图片交给视觉 API 做客观识别，再由现有 Persona 语言模型结合记忆和上下文生成自然回复。

**Architecture:** 将链路拆成“Telegram 媒体接入 → 视觉结构化分析 → Persona 回复”三层。视觉层只返回有证据的 JSON，不模仿人物；语言层只接收压缩后的视觉观察，不接收图片二进制。图片只在内存中短暂存在，不写入 Redis 或聊天历史。

**Tech Stack:** Python 3.11+、FastAPI、httpx、Telegram Bot API、OpenAI-compatible multimodal Chat Completions、unittest。

---

## 文件结构

- Create: `bot/vision.py` — Telegram 图片下载、大小校验、视觉 API 调用和 JSON 解析。
- Create: `bot/vision_prompts.py` — 视觉抽取提示词和 Persona 消费视觉结果的规则。
- Modify: `bot/app.py` — 解析照片事件、扩展消息缓冲、调用视觉层和语言层。
- Create: `tests/test_telegram_images.py` — Telegram 照片解析、下载与缓冲测试。
- Create: `tests/test_vision_pipeline.py` — 视觉 JSON、失败降级和语言模型交接测试。
- Modify: `.env.example` — 独立的视觉模型配置。
- Modify: `docs/TELEGRAM_RAILWAY.md`、`docs/RENDER.md` — 部署和手工验证说明。

## 数据流

```text
Telegram update
  ├─ text
  ├─ caption
  └─ photo[-1].file_id
          ↓ 同一 chat 3 秒缓冲，合并“图片 + 随后补充的文字”
Telegram getFile → 下载 JPEG bytes → 大小/MIME 校验
          ↓
Vision API → 严格 JSON：画面事实、OCR、候选类别、置信度、不确定项
          ↓
Persona LLM：Persona + 相关记忆 + 最近历史 + 视觉 JSON + 用户文字
          ↓
Telegram 短消息回复
```

### Task 1: 定义视觉数据结构与提示词

**Files:**
- Create: `bot/vision_prompts.py`
- Create: `bot/vision.py`
- Test: `tests/test_vision_pipeline.py`

- [ ] **Step 1: 写失败测试，固定视觉输出契约**

```python
import unittest

from bot.vision import ImageObservation, parse_vision_response


class VisionResponseTests(unittest.TestCase):
    def test_parses_grounded_image_observation(self):
        raw = '''{
          "summary": "桌上有一杯带冰块的浅棕色饮品",
          "visible_text": ["LATTE"],
          "objects": ["透明塑料杯", "吸管", "冰块"],
          "likely_items": [{"name": "冰拿铁", "confidence": 0.78}],
          "uncertainties": ["无法确认咖啡品牌"]
        }'''

        result = parse_vision_response(raw)

        self.assertIsInstance(result, ImageObservation)
        self.assertEqual(result.likely_items[0]["name"], "冰拿铁")
        self.assertEqual(result.visible_text, ["LATTE"])

    def test_invalid_json_becomes_uncertain_observation(self):
        result = parse_vision_response("not json")

        self.assertEqual(result.summary, "图片识别结果不可用")
        self.assertEqual(result.likely_items, [])
        self.assertTrue(result.uncertainties)
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m unittest tests.test_vision_pipeline.VisionResponseTests -v`

Expected: FAIL，提示 `bot.vision` 不存在。

- [ ] **Step 3: 创建视觉抽取提示词**

```python
# bot/vision_prompts.py
VISION_EXTRACTION_PROMPT = """
你是图片事实抽取器，不负责聊天，也不扮演任何人物。

任务：根据图片和用户附言，提取后续语言模型可以安全使用的视觉事实。

规则：
1. 只描述图片中可以直接观察到的内容。
2. 区分“确定看到”和“推测”。不要把候选类别写成事实。
3. 商品、品牌、地点和人物身份无法确认时必须明确写入 uncertainties。
4. 完整抄录清晰可见的文字；模糊文字不要猜。
5. 食物或饮品要记录容器、颜色、冷热线索、配料线索和最多三个候选类别。
6. 不要回复用户，不要使用 Persona 口吻。
7. 只输出 JSON，不要 Markdown 代码块。

JSON schema:
{
  "summary": "一句客观概述",
  "visible_text": ["可见文字"],
  "objects": ["客观物体或特征"],
  "likely_items": [{"name": "候选名称", "confidence": 0.0}],
  "uncertainties": ["无法确认的事项"]
}
""".strip()

PERSONA_IMAGE_RULES = """
用户发送了图片。下面的视觉观察来自独立识图模型，只能作为证据使用：
- 不得把候选项说成确定事实。
- 不得补充视觉结果中不存在的品牌、地点、人物或共同记忆。
- confidence 低于 0.7 时使用“看着像”“有点像”等不确定表达。
- 如果识图失败或没有可靠候选，像该 Persona 一样自然地请用户补充，不要假装看懂。
- 不要提到视觉模型、JSON、识图管线或系统提示词。
""".strip()
```

- [ ] **Step 4: 实现数据结构和保守 JSON 解析**

```python
# bot/vision.py
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ImageObservation:
    summary: str
    visible_text: list[str] = field(default_factory=list)
    objects: list[str] = field(default_factory=list)
    likely_items: list[dict[str, Any]] = field(default_factory=list)
    uncertainties: list[str] = field(default_factory=list)

    def to_prompt_text(self) -> str:
        return json.dumps(self.__dict__, ensure_ascii=False)


def unavailable_observation(reason: str) -> ImageObservation:
    return ImageObservation(
        summary="图片识别结果不可用",
        uncertainties=[reason],
    )


def parse_vision_response(raw: str) -> ImageObservation:
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("vision response is not an object")
        return ImageObservation(
            summary=str(data.get("summary") or "图片内容未能确定"),
            visible_text=[str(item) for item in data.get("visible_text", [])],
            objects=[str(item) for item in data.get("objects", [])],
            likely_items=[item for item in data.get("likely_items", []) if isinstance(item, dict)],
            uncertainties=[str(item) for item in data.get("uncertainties", [])],
        )
    except (json.JSONDecodeError, TypeError, ValueError):
        return unavailable_observation("视觉 API 未返回有效 JSON")
```

- [ ] **Step 5: 运行测试并提交**

Run: `python -m unittest tests.test_vision_pipeline.VisionResponseTests -v`

Expected: PASS。

```bash
git add bot/vision.py bot/vision_prompts.py tests/test_vision_pipeline.py
git commit -m "Add structured vision observation contract"
```

### Task 2: 从 Telegram 获取图片

**Files:**
- Modify: `bot/vision.py`
- Test: `tests/test_telegram_images.py`

- [ ] **Step 1: 写失败测试，验证选择最大照片和下载流程**

```python
import unittest

from bot.vision import select_telegram_photo


class TelegramPhotoTests(unittest.TestCase):
    def test_selects_largest_telegram_photo(self):
        message = {
            "photo": [
                {"file_id": "small", "width": 90, "height": 90, "file_size": 1000},
                {"file_id": "large", "width": 1280, "height": 960, "file_size": 120000},
            ],
            "caption": "猜猜我喝的什么",
        }

        photo = select_telegram_photo(message)

        self.assertEqual(photo.file_id, "large")
        self.assertEqual(photo.caption, "猜猜我喝的什么")

    def test_message_without_photo_returns_none(self):
        self.assertIsNone(select_telegram_photo({"text": "你好"}))
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m unittest tests.test_telegram_images.TelegramPhotoTests -v`

Expected: FAIL，提示 `select_telegram_photo` 不存在。

- [ ] **Step 3: 实现照片引用、大小限制和下载**

```python
# append to bot/vision.py
import httpx


@dataclass(frozen=True)
class TelegramPhoto:
    file_id: str
    caption: str = ""
    declared_size: int = 0


def select_telegram_photo(message: dict[str, Any]) -> TelegramPhoto | None:
    photos = message.get("photo") or []
    if not photos:
        return None
    largest = max(
        photos,
        key=lambda item: (
            int(item.get("width", 0)) * int(item.get("height", 0)),
            int(item.get("file_size", 0)),
        ),
    )
    return TelegramPhoto(
        file_id=str(largest["file_id"]),
        caption=str(message.get("caption") or "").strip(),
        declared_size=int(largest.get("file_size", 0)),
    )


async def download_telegram_photo(
    photo: TelegramPhoto,
    telegram_api: str,
    bot_token: str,
    timeout: float,
    max_bytes: int,
) -> tuple[bytes, str]:
    if photo.declared_size and photo.declared_size > max_bytes:
        raise ValueError("Telegram photo exceeds VISION_MAX_IMAGE_BYTES")

    async with httpx.AsyncClient(timeout=timeout) as client:
        metadata_response = await client.get(
            f"{telegram_api}/getFile",
            params={"file_id": photo.file_id},
        )
        metadata_response.raise_for_status()
        file_path = metadata_response.json()["result"]["file_path"]
        image_response = await client.get(
            f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
        )
        image_response.raise_for_status()

    image_bytes = image_response.content
    if len(image_bytes) > max_bytes:
        raise ValueError("Downloaded image exceeds VISION_MAX_IMAGE_BYTES")
    mime_type = image_response.headers.get("content-type", "image/jpeg").split(";")[0]
    if mime_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise ValueError(f"Unsupported image MIME type: {mime_type}")
    return image_bytes, mime_type
```

- [ ] **Step 4: 用 `httpx.MockTransport` 测试 getFile、下载、超限和 MIME 拒绝**

测试必须断言：先请求 `/getFile?file_id=large`，再请求 `/file/bot…/photos/example.jpg`；超过 `max_bytes` 或返回 `text/html` 时抛出 `ValueError`。

- [ ] **Step 5: 运行测试并提交**

Run: `python -m unittest tests.test_telegram_images -v`

Expected: PASS。

```bash
git add bot/vision.py tests/test_telegram_images.py
git commit -m "Download Telegram photos for vision analysis"
```

### Task 3: 调用视觉 API

**Files:**
- Modify: `bot/vision.py`
- Modify: `bot/app.py:30-75`
- Test: `tests/test_vision_pipeline.py`

- [ ] **Step 1: 写失败测试，检查多模态请求形状**

测试通过 `httpx.MockTransport` 断言请求包含一个文本块和一个 `data:image/jpeg;base64,...` 图片块，并断言模型名来自 `VISION_MODEL`，不是 `LLM_MODEL`。

- [ ] **Step 2: 为 `Settings` 添加独立配置**

```python
vision_api_key: str = os.getenv("VISION_API_KEY", "")
vision_api_base: str = os.getenv("VISION_API_BASE", "").rstrip("/")
vision_model: str = os.getenv("VISION_MODEL", "")
vision_timeout: float = float(os.getenv("VISION_TIMEOUT", "45"))
vision_max_image_bytes: int = int(os.getenv("VISION_MAX_IMAGE_BYTES", str(8 * 1024 * 1024)))
```

- [ ] **Step 3: 实现视觉调用**

```python
# append to bot/vision.py
import base64

from bot.vision_prompts import VISION_EXTRACTION_PROMPT


async def call_vision_api(
    image_bytes: bytes,
    mime_type: str,
    caption: str,
    api_base: str,
    api_key: str,
    model: str,
    timeout: float,
) -> ImageObservation:
    encoded = base64.b64encode(image_bytes).decode("ascii")
    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": 700,
        "response_format": {"type": "json_object"},
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": f"{VISION_EXTRACTION_PROMPT}\n\n用户附言：{caption or '(无)'}"},
                {"type": "image_url", "image_url": {
                    "url": f"data:{mime_type};base64,{encoded}",
                    "detail": "high",
                }},
            ],
        }],
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{api_base}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )
        response.raise_for_status()
    return parse_vision_response(response.json()["choices"][0]["message"]["content"])
```

- [ ] **Step 4: 为不支持 `response_format` 的供应商添加一次兼容重试**

仅当第一次返回 HTTP 400 且响应正文明确提到 `response_format` 时，删除该字段重试一次；其他 400 不重试，避免重复计费和掩盖真实配置错误。

- [ ] **Step 5: 运行测试并提交**

Run: `python -m unittest tests.test_vision_pipeline -v`

Expected: PASS。

```bash
git add bot/vision.py bot/app.py tests/test_vision_pipeline.py
git commit -m "Call multimodal API for image observations"
```

### Task 4: 把照片和相邻文字合并为一个用户轮次

**Files:**
- Modify: `bot/app.py:84-90,702-746,1029-1054`
- Test: `tests/test_message_buffering.py`
- Test: `tests/test_telegram_images.py`

- [ ] **Step 1: 扩展缓冲状态**

```python
@dataclass
class PendingMessageBuffer:
    messages: list[str]
    photos: list[TelegramPhoto]
    version: int = 0
    task: asyncio.Task | None = None
```

- [ ] **Step 2: 写失败测试覆盖三个真实发送顺序**

测试以下输入最终只调用一次 `handle_user_turn`：

1. 图片带 caption；
2. 图片无 caption，1 秒后发送“猜猜是什么”；
3. 先发“给你看”，1 秒后发图片。

每个断言都应确认合并后的文本和 `TelegramPhoto` 被同时传递。

- [ ] **Step 3: 将 webhook 解析从纯文本改为文本或照片**

```python
text = (message.get("text") or message.get("caption") or "").strip()
photo = select_telegram_photo(message)
if chat_id is None or (not text and photo is None):
    return {"ok": True}

await record_user_chat_activity(chat_id)
await handle_buffered_user_message(chat_id, text=text, photo=photo)
```

- [ ] **Step 4: flush 时调用统一入口**

```python
combined_text = "\n".join(part for part in latest.messages if part)
photos = list(latest.photos)
_pending_message_buffers.pop(key, None)
await handle_user_turn(chat_id, combined_text, photos)
```

一期只处理每轮第一张照片；如果同一轮收到多张，语言模型要自然说明“我先看第一张”。这个限制防止一次请求意外放大费用，后续可通过配置扩展。

- [ ] **Step 5: 运行缓冲测试并提交**

Run: `python -m unittest tests.test_message_buffering tests.test_telegram_images -v`

Expected: PASS。

```bash
git add bot/app.py tests/test_message_buffering.py tests/test_telegram_images.py
git commit -m "Buffer Telegram photos with adjacent text"
```

### Task 5: 让 Persona 语言模型消费视觉结果

**Files:**
- Modify: `bot/app.py:207-227,749-782,1057-1081`
- Modify: `bot/vision_prompts.py`
- Test: `tests/test_vision_pipeline.py`

- [ ] **Step 1: 写失败测试验证两阶段边界**

测试应断言：

- 视觉 API 接收图片，但不接收完整 Persona 和聊天历史；
- 语言 LLM 接收 `ImageObservation`、用户文字、Persona、相关记忆和历史；
- 语言 LLM 不接收 base64 图片；
- Redis 历史中只保存压缩后的视觉文字，不保存图片字节或 data URL。

- [ ] **Step 2: 扩展系统提示词**

```python
def build_system_prompt(
    persona_prompt: str,
    memory_snippets: list[str] | None = None,
    image_observation: ImageObservation | None = None,
) -> str:
    image_block = "(no image in this turn)"
    if image_observation is not None:
        image_block = f"{PERSONA_IMAGE_RULES}\n{image_observation.to_prompt_text()}"
    # 将 image_block 放在 Persona 和 raw memory 之后，并保持“不虚构”的硬规则。
```

- [ ] **Step 3: 创建统一的图片轮次处理函数**

```python
async def handle_user_turn(
    chat_id: int | str,
    text: str,
    photos: list[TelegramPhoto] | None = None,
) -> None:
    observation = None
    if photos:
        try:
            image_bytes, mime_type = await download_telegram_photo(
                photos[0],
                settings.telegram_api,
                settings.telegram_bot_token,
                settings.vision_timeout,
                settings.vision_max_image_bytes,
            )
            observation = await call_vision_api(
                image_bytes,
                mime_type,
                photos[0].caption,
                settings.vision_api_base,
                settings.vision_api_key,
                settings.vision_model,
                settings.vision_timeout,
            )
        except Exception as exc:
            logger.warning("Vision processing failed: %s", type(exc).__name__)
            observation = unavailable_observation("暂时无法读取这张图片")

    history = await load_history(chat_id)
    reply = await call_llm(text or "用户发送了一张图片", history, observation)
    stored_user_text = text or "[发送了一张图片]"
    if observation:
        stored_user_text += f"\n[图片观察摘要] {observation.summary}"
    history.extend([
        {"role": "user", "content": stored_user_text},
        {"role": "assistant", "content": reply},
    ])
    await save_history(chat_id, history)
    await send_telegram_message(chat_id, reply)
```

- [ ] **Step 4: 明确失败降级行为**

视觉失败时仍调用 Persona LLM，但只提供“图片暂时无法读取”的观察；系统规则要求它不猜内容，而是用人物口吻说类似“图没加载出来，你再发一下”。语言模型失败时继续使用现有“呃 / 卡住了”兜底。

- [ ] **Step 5: 运行测试并提交**

Run: `python -m unittest tests.test_vision_pipeline tests.test_memory_retrieval -v`

Expected: PASS。

```bash
git add bot/app.py bot/vision_prompts.py tests/test_vision_pipeline.py
git commit -m "Generate persona replies from grounded image observations"
```

### Task 6: 配置、日志安全与上线验证

**Files:**
- Modify: `.env.example`
- Modify: `bot/app.py:20-27,985-1016`
- Modify: `docs/TELEGRAM_RAILWAY.md`
- Modify: `docs/RENDER.md`

- [ ] **Step 1: 增加环境变量示例**

```dotenv
# Vision model. Keep separate so vision and persona models can use different providers.
VISION_API_BASE=https://your-vision-provider.example/v1
VISION_API_KEY=
VISION_MODEL=
VISION_TIMEOUT=45
VISION_MAX_IMAGE_BYTES=8388608
```

- [ ] **Step 2: 健康检查只暴露布尔状态，不暴露密钥**

```python
"vision": {
    "configured": bool(
        settings.vision_api_base
        and settings.vision_api_key
        and settings.vision_model
    ),
    "model": settings.vision_model,
    "max_image_bytes": settings.vision_max_image_bytes,
},
```

- [ ] **Step 3: 禁止 httpx 把 Telegram Token 写进日志**

```python
logging.getLogger("httpx").setLevel(logging.WARNING)
```

同时确保自定义日志不记录 Telegram 下载 URL、Authorization、base64、图片内容或完整视觉请求。

- [ ] **Step 4: 运行完整测试**

Run: `python -m unittest discover -s tests -v`

Expected: 所有测试通过，没有未等待协程和残留缓冲任务警告。

- [ ] **Step 5: 在 Render 测试五个场景**

1. 单独发一张咖啡照片；
2. 发照片并附言“猜猜我喝的什么”；
3. 发照片后一秒补发“看出来了吗”；
4. 发一张看不清的照片，确认 Bot 表达不确定而不是编造；
5. 临时配置错误的视觉模型名，确认 Bot 自然请求重发且 Render 日志不出现 Telegram Token。

- [ ] **Step 6: 提交部署文档**

```bash
git add .env.example bot/app.py docs/TELEGRAM_RAILWAY.md docs/RENDER.md
git commit -m "Document and secure Telegram vision deployment"
```

## 验收标准

- 纯图片、图片加 caption、图片后补文字都能形成一个自然回复。
- 视觉模型只抽取事实，Persona 模型负责最终措辞。
- 无法确认咖啡种类时必须表达不确定，不得编造品牌。
- 图片和 base64 不写入 Redis、日志或聊天历史。
- 视觉 API 失败不会让整个 Telegram Bot 返回“卡住了”。
- Telegram Bot Token 不再出现在 Render 请求日志中。
