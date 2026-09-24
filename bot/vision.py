from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ImageObservation:
    summary: str
    visible_text: list[str] = field(default_factory=list)
    objects: list[str] = field(default_factory=list)
    likely_items: list[dict[str, Any]] = field(default_factory=list)
    uncertainties: list[str] = field(default_factory=list)

    def to_prompt_text(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


@dataclass(frozen=True)
class TelegramPhoto:
    file_id: str
    caption: str = ""
    declared_size: int = 0


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
            likely_items=[
                item for item in data.get("likely_items", []) if isinstance(item, dict)
            ],
            uncertainties=[str(item) for item in data.get("uncertainties", [])],
        )
    except (json.JSONDecodeError, TypeError, ValueError):
        return unavailable_observation("视觉 API 未返回有效 JSON")


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
    client: Any,
    max_bytes: int,
) -> tuple[bytes, str]:
    if photo.declared_size and photo.declared_size > max_bytes:
        raise ValueError("Telegram photo exceeds VISION_MAX_IMAGE_BYTES")

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
