from __future__ import annotations

import asyncio
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
from threading import Lock

import httpx

from backend.modules.errors import OCRDependencyError, OCRError
from backend.schemas.block import TextGroup


API_MODEL = "gemma-4-26b-a4b-it"
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{API_MODEL}:generateContent"
DEFAULT_LOCAL_MODEL_DIR = Path(__file__).resolve().parents[2] / "ocr_ai_model"
DEFAULT_LOCAL_MODEL_PATH = DEFAULT_LOCAL_MODEL_DIR / "gemma-4-E4B-it-Q4_K_M.gguf"


@dataclass
class TranslationResult:
    corrected_japanese: str
    translated_text: str


class GeminiApiTranslator:
    def __init__(self) -> None:
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.timeout_seconds = 120.0

    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def translate_groups(self, groups: list[TextGroup], target_lang: str = "en") -> list[TextGroup]:
        if not self.api_key:
            raise OCRDependencyError("Set GEMINI_API_KEY to enable API translation.")

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
        language_name = _language_name(target_lang)
        payload = {
            "systemInstruction": {
                "parts": [
                    {
                        "text": _translation_instruction(language_name)
                    }
                ]
            },
            "contents": [{"parts": [{"text": text}]}],
        }
        try:
            response = await client.post(
                API_URL,
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

        visible_parts: list[str] = []
        fallback_parts: list[str] = []
        for part in parts:
            if not isinstance(part, dict):
                continue
            part_text = str(part.get("text", "")).strip()
            if not part_text:
                continue
            fallback_parts.append(part_text)
            if not part.get("thought"):
                visible_parts.append(part_text)

        content = "\n".join(visible_parts or fallback_parts).strip()
        if not content:
            raise OCRError("Translation API returned no text content.")
        return _parse_translation_content(text, content)


class LocalGemmaTranslator:
    _model_lock = Lock()
    _cached_model = None
    _cached_signature: tuple = ()

    def __init__(self) -> None:
        self.model_path = Path(os.getenv("LOCAL_TRANSLATOR_MODEL_PATH", DEFAULT_LOCAL_MODEL_PATH))
        self.n_ctx = _safe_int(os.getenv("LOCAL_TRANSLATOR_N_CTX", "4096"), 4096)
        self.n_threads = _safe_int(os.getenv("LOCAL_TRANSLATOR_N_THREADS", str(max(4, (os.cpu_count() or 8) - 2))), 6)
        self.n_threads_batch = _safe_int(os.getenv("LOCAL_TRANSLATOR_N_THREADS_BATCH", str(self.n_threads)), self.n_threads)
        self.n_batch = _safe_int(os.getenv("LOCAL_TRANSLATOR_N_BATCH", "1024"), 1024)
        self.n_ubatch = _safe_int(os.getenv("LOCAL_TRANSLATOR_N_UBATCH", "512"), 512)
        self.gpu_layers = _safe_int(os.getenv("LOCAL_TRANSLATOR_GPU_LAYERS", "-1"), -1)
        self.flash_attn = _safe_bool(os.getenv("LOCAL_TRANSLATOR_FLASH_ATTN", "true"), True)
        self.temperature = _safe_float(os.getenv("LOCAL_TRANSLATOR_TEMPERATURE", "0.0"), 0.0)
        self.top_p = _safe_float(os.getenv("LOCAL_TRANSLATOR_TOP_P", "0.9"), 0.9)
        self.top_k = _safe_int(os.getenv("LOCAL_TRANSLATOR_TOP_K", "40"), 40)
        self.repeat_penalty = _safe_float(os.getenv("LOCAL_TRANSLATOR_REPEAT_PENALTY", "1.05"), 1.05)
        self.max_tokens = _safe_int(os.getenv("LOCAL_TRANSLATOR_MAX_TOKENS", "256"), 256)

    def is_configured(self) -> bool:
        return self.model_path.exists()

    async def translate_groups(self, groups: list[TextGroup], target_lang: str = "en") -> list[TextGroup]:
        if not self.is_configured():
            raise OCRDependencyError(
                f"Local translator model not found at `{self.model_path}`."
            )

        translated_groups: list[TextGroup] = []
        for group in groups:
            result = await asyncio.to_thread(self._translate_single_group, group.source_text, target_lang)
            translated_groups.append(
                group.model_copy(
                    update={
                        "corrected_text": result.corrected_japanese,
                        "translated_text": result.translated_text,
                    }
                )
            )
        return translated_groups

    def _translate_single_group(self, text: str, target_lang: str) -> TranslationResult:
        if not text.strip():
            return TranslationResult(corrected_japanese="", translated_text="")

        model = self._get_model()
        language_name = _language_name(target_lang)
        try:
            response = model.create_chat_completion(
                messages=[
                    {"role": "system", "content": _translation_instruction(language_name)},
                    {"role": "user", "content": f"Target language: {language_name}\n\n{text}"},
                ],
                temperature=self.temperature,
                top_p=self.top_p,
                top_k=self.top_k,
                repeat_penalty=self.repeat_penalty,
                max_tokens=self.max_tokens,
            )
        except Exception as exc:  # pragma: no cover
            raise OCRError(f"Local translation failed: {exc}") from exc

        content = _extract_chat_text(response)
        return _parse_translation_content(text, content)

    def _get_model(self):
        signature = (
            str(self.model_path),
            self.n_ctx,
            self.n_threads,
            self.n_threads_batch,
            self.n_batch,
            self.n_ubatch,
            self.gpu_layers,
            self.flash_attn,
        )
        with self._model_lock:
            if self.__class__._cached_model is not None and self.__class__._cached_signature == signature:
                return self.__class__._cached_model

            _ensure_cuda_runtime_on_path()
            try:
                from llama_cpp import Llama
            except Exception as exc:
                raise OCRDependencyError(
                    "llama-cpp-python could not be loaded for local translation."
                ) from exc

            kwargs = {
                "model_path": str(self.model_path),
                "n_ctx": self.n_ctx,
                "n_threads": self.n_threads,
                "n_threads_batch": self.n_threads_batch,
                "n_batch": self.n_batch,
                "n_ubatch": self.n_ubatch,
                "n_gpu_layers": self.gpu_layers,
                "flash_attn": self.flash_attn,
                "offload_kqv": True,
                "verbose": False,
            }
            try:
                model = Llama(**kwargs)
            except Exception as exc:
                cpu_kwargs = dict(kwargs)
                cpu_kwargs["n_gpu_layers"] = 0
                cpu_kwargs["flash_attn"] = False
                cpu_kwargs["offload_kqv"] = False
                try:
                    model = Llama(**cpu_kwargs)
                except Exception as cpu_exc:
                    raise OCRDependencyError(
                        f"Local translator could not start on GPU or CPU. GPU error: {exc} | CPU error: {cpu_exc}"
                    ) from cpu_exc

            self.__class__._cached_model = model
            self.__class__._cached_signature = signature
            return model


class GemmaTranslator:
    def __init__(self) -> None:
        self._local = LocalGemmaTranslator()
        self._api = GeminiApiTranslator()

    def is_configured(self, translator_engine: str = "local") -> bool:
        engine = self._resolve_engine(translator_engine)
        if engine == "local":
            return self._local.is_configured()
        if engine == "api":
            return self._api.is_configured()
        return self._local.is_configured() or self._api.is_configured()

    async def translate_groups(
        self,
        groups: list[TextGroup],
        target_lang: str = "en",
        translator_engine: str = "local",
    ) -> list[TextGroup]:
        engine = self._resolve_engine(translator_engine)
        if engine == "local":
            return await self._local.translate_groups(groups, target_lang)
        if engine == "api":
            return await self._api.translate_groups(groups, target_lang)

        if self._local.is_configured():
            return await self._local.translate_groups(groups, target_lang)
        if self._api.is_configured():
            return await self._api.translate_groups(groups, target_lang)
        raise OCRDependencyError("No translation engine is configured.")

    def _resolve_engine(self, translator_engine: str) -> str:
        normalized = str(translator_engine or "local").strip().lower()
        if normalized not in {"local", "api", "auto"}:
            raise OCRError("`translator_engine` must be `local`, `api`, or `auto`.")
        return normalized


def _extract_chat_text(result) -> str:
    if isinstance(result, dict):
        choices = result.get("choices") or []
        if choices:
            message = choices[0].get("message") or {}
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()
            text = choices[0].get("text")
            if isinstance(text, str) and text.strip():
                return text.strip()
    raise OCRError("Translator returned no text content.")


def _parse_translation_content(source_text: str, content: str) -> TranslationResult:
    jp = source_text.strip()
    translated = ""
    for line in content.splitlines():
        if line.startswith("JP:"):
            jp = line.removeprefix("JP:").strip()
        elif line.startswith("TR:"):
            translated = line.removeprefix("TR:").strip()
        elif line.startswith("EN:") and not translated:
            translated = line.removeprefix("EN:").strip()
    return TranslationResult(corrected_japanese=jp, translated_text=translated)


def _translation_instruction(language_name: str) -> str:
    return (
        "You are a Japanese manga OCR correction and translation engine. "
        "Minimally correct OCR mistakes in the provided Japanese text, then translate it. "
        "Be conservative. Do not invent story context. Preserve names, punctuation, ellipses, emphasis, and ambiguity when possible. "
        "If the OCR text already looks valid, keep the Japanese almost unchanged. "
        f"Return exactly two lines and nothing else: 'JP: <corrected japanese>' and 'TR: <{language_name} translation>'."
    )


def _language_name(target_lang: str) -> str:
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


def _candidate_cuda_bin_dirs() -> list[str]:
    candidates: list[str] = []
    try:
        import site

        site_roots = list(site.getsitepackages()) + [site.getusersitepackages()]
    except Exception:
        site_roots = []

    for site_root in site_roots:
        llama_lib = os.path.join(str(site_root or "").strip(), "llama_cpp", "lib")
        if os.path.isdir(llama_lib):
            candidates.append(llama_lib)

    toolkit_root = str(os.getenv("CUDAToolkit_ROOT", "")).strip()
    if toolkit_root:
        candidates.append(os.path.join(toolkit_root, "bin"))

    nvcc_path = shutil.which("nvcc")
    if nvcc_path:
        candidates.append(os.path.dirname(os.path.abspath(nvcc_path)))

    default_root = Path(r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA")
    if default_root.exists():
        for version_dir in sorted(default_root.glob("v*"), reverse=True):
            candidates.append(str(version_dir / "bin"))

    unique: list[str] = []
    seen = set()
    for item in candidates:
        normalized = os.path.normcase(os.path.abspath(item)) if item else ""
        if normalized and os.path.isdir(normalized) and normalized not in seen:
            seen.add(normalized)
            unique.append(normalized)
    return unique


def _ensure_cuda_runtime_on_path() -> None:
    current_path = os.environ.get("PATH", "")
    for cuda_bin in _candidate_cuda_bin_dirs():
        if cuda_bin not in current_path:
            os.environ["PATH"] = cuda_bin + os.pathsep + os.environ.get("PATH", "")
        if hasattr(os, "add_dll_directory"):
            try:
                os.add_dll_directory(cuda_bin)
            except Exception:
                pass


def _safe_int(raw_value: str, fallback: int) -> int:
    try:
        return int(str(raw_value).strip())
    except Exception:
        return fallback


def _safe_float(raw_value: str, fallback: float) -> float:
    try:
        return float(str(raw_value).strip())
    except Exception:
        return fallback


def _safe_bool(raw_value: str, fallback: bool) -> bool:
    normalized = str(raw_value or "").strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return fallback
