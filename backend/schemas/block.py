from __future__ import annotations

from pydantic import BaseModel, Field


class TextBlock(BaseModel):
    id: int
    bbox: list[list[int]] = Field(default_factory=list)
    text: str = ""
    confidence: float = 0.0
    direction: str = "horizontal"


class ImageMeta(BaseModel):
    width: int
    height: int


class OCRResponse(BaseModel):
    image: ImageMeta
    blocks: list[TextBlock] = Field(default_factory=list)


class OCRBase64Request(BaseModel):
    image_base64: str
    source_lang: str = "ja"
    ocr_engine: str = "gguf"
    detection_engine: str = "text"


class TextGroup(BaseModel):
    id: int
    block_ids: list[int] = Field(default_factory=list)
    bbox: list[list[int]] = Field(default_factory=list)
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    reading_order: int = 0
    source_text: str = ""
    corrected_text: str = ""
    translated_text: str = ""


class Phase2Request(BaseModel):
    image: ImageMeta
    blocks: list[TextBlock] = Field(default_factory=list)
    source_lang: str = "ja"
    ocr_engine: str = "gguf"
    detection_engine: str = "text"
    translator_engine: str = "local"
    target_lang: str = "en"
    translate: bool = True


class Phase2Response(BaseModel):
    image: ImageMeta
    blocks: list[TextBlock] = Field(default_factory=list)
    groups: list[TextGroup] = Field(default_factory=list)
    translation_enabled: bool = False
