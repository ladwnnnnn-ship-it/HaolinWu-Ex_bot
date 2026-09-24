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
