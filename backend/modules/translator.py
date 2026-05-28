from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

from backend.modules.errors import OCRDependencyError, OCRError
from backend.schemas.block import TextGroup


GEMMA_MODEL = "gemma-4-26b-a4b-it"
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMMA_MODEL}:generateContent"


@dataclass
class TranslationResult:
    corrected_japanese: str
    translated_text: str


class GemmaTranslator:
    def __init__(self) -> None:
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.timeout_seconds = 120.0

    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def translate_groups(self, groups: list[TextGroup], target_lang: str = "en") -> list[TextGroup]:
        if not self.api_key:
            raise OCRDependencyError("Set GEMINI_API_KEY to enable Phase 2 translation.")

        translated_groups: list[TextGroup] = []
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            for group in groups:
                result = await self._translate_single_group(client, group.source_text, target_lang)
                translated_groups.append(
                    group.model_copy(
                        update={
                            "corrected_text": result.corrected_japanese,
                            "translated_text": result.translated_text,
                        }
                    )
                )
        return translated_groups

    async def _translate_single_group(
        self,
        client: httpx.AsyncClient,
        text: str,
        target_lang: str,
    ) -> TranslationResult:
        language_name = self._language_name(target_lang)
        payload = {
            "systemInstruction": {
                "parts": [
                    {
                        "text": (
                            "You are a Japanese manga OCR correction and translation engine. "
                            "Your job is to minimally correct OCR mistakes in the provided Japanese text, "
                            f"then translate it to {language_name}. Be conservative. Do not invent story context, "
                            "do not reinterpret ambiguous words aggressively, and do not rewrite stylized manga phrasing "
                            "into different wording unless the OCR error is obvious. Preserve character names, title names, "
                            "quoted terms, punctuation, ellipses, emphasis, and repeated sounds as much as possible. "
                            "If a word is uncertain, keep it close to the original Japanese rather than guessing a different meaning. "
                            "For proper names and titles, prefer transliteration over semantic replacement unless the reading is explicit. "
                            "If the OCR text already looks valid, keep the Japanese almost unchanged. "
                            "Return exactly two lines and nothing else: "
                            f"'JP: <corrected japanese>' and 'TR: <{language_name} translation>'."
                        )
                    }
                ]
            },
            "contents": [{"parts": [{"text": text}]}],
        }

        try:
            response = await client.post(
                GEMINI_API_URL,
                params={"key": self.api_key},
                json=payload,
                headers={"Content-Type": "application/json"},
            )
        except httpx.TimeoutException as exc:
            raise OCRError(
                f"Translation request timed out after {int(self.timeout_seconds)} seconds."
            ) from exc
        except httpx.HTTPError as exc:
            raise OCRError(f"Translation request failed: {exc}") from exc

        if response.status_code >= 400:
            raise OCRError(f"Translation request failed: {response.text}")

        data = response.json()
        try:
            parts = data["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError, TypeError) as exc:
            raise OCRError("Translation API returned an unexpected response shape.") from exc

        content = self._extract_response_text(parts)
        jp = text
        translated = ""
        for line in content.splitlines():
            if line.startswith("JP:"):
                jp = line.removeprefix("JP:").strip()
            elif line.startswith("TR:"):
                translated = line.removeprefix("TR:").strip()
            elif line.startswith("EN:") and not translated:
                translated = line.removeprefix("EN:").strip()

        return TranslationResult(corrected_japanese=jp, translated_text=translated)

    def _extract_response_text(self, parts: list[dict]) -> str:
        visible_parts: list[str] = []
        fallback_parts: list[str] = []

        for part in parts:
            if not isinstance(part, dict):
                continue
            text = str(part.get("text", "")).strip()
            if not text:
                continue
            fallback_parts.append(text)
            if not part.get("thought"):
                visible_parts.append(text)

        combined = "\n".join(visible_parts or fallback_parts).strip()
        if not combined:
            raise OCRError("Translation API returned no text content.")
        return combined

    def _language_name(self, target_lang: str) -> str:
        normalized = target_lang.strip().lower()
        names = {
            "en": "English",
            "vi": "Vietnamese",
            "ja": "Japanese",
            "ko": "Korean",
            "zh": "Chinese",
            "zh-cn": "Simplified Chinese",
            "zh-tw": "Traditional Chinese",
            "es": "Spanish",
            "fr": "French",
            "de": "German",
            "it": "Italian",
            "pt": "Portuguese",
            "ru": "Russian",
            "th": "Thai",
            "id": "Indonesian",
        }
        return names.get(normalized, normalized or "English")
