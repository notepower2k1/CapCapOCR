import base64
import binascii

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from backend.modules.errors import OCRDependencyError, OCRError
from backend.modules.phase2 import build_text_groups
from backend.modules.paddle_ocr import OCREngine
from backend.modules.translator import GemmaTranslator
from backend.schemas.block import OCRBase64Request, OCRResponse, Phase2Request, Phase2Response


router = APIRouter(prefix="/api", tags=["ocr"])
ocr_service = OCREngine()
translator = GemmaTranslator()


@router.post("/ocr", response_model=OCRResponse)
async def run_ocr(
    image: UploadFile = File(...),
    source_lang: str = Form(default="ja"),
    ocr_engine_name: str = Form(default="gguf", alias="ocr_engine"),
    detection_engine: str = Form(default="text"),
) -> OCRResponse:
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must be an image.",
        )

    try:
        image_bytes = await image.read()
        return ocr_service.process_image(
            image_bytes=image_bytes,
            source_lang=source_lang,
            ocr_engine=ocr_engine_name,
            detection_engine=detection_engine,
        )
    except OCRDependencyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except OCRError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


@router.post("/ocr/base64", response_model=OCRResponse)
async def run_ocr_base64(request: OCRBase64Request) -> OCRResponse:
    try:
        image_bytes = _decode_base64_image(request.image_base64)
        return ocr_service.process_image(
            image_bytes=image_bytes,
            source_lang=request.source_lang,
            ocr_engine=request.ocr_engine,
            detection_engine=request.detection_engine,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except OCRDependencyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except OCRError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


@router.post("/phase2", response_model=Phase2Response)
async def run_phase2(request: Phase2Request) -> Phase2Response:
    try:
        grouped = build_text_groups(request.blocks).groups
        translation_enabled = (
            request.translate
            and translator.is_configured(request.translator_engine)
            and request.source_lang == "ja"
        )
        if translation_enabled:
            grouped = await translator.translate_groups(
                grouped,
                request.target_lang,
                request.translator_engine,
            )
        return Phase2Response(
            image=request.image,
            blocks=request.blocks,
            groups=grouped,
            translation_enabled=translation_enabled,
        )
    except OCRDependencyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except OCRError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


def _decode_base64_image(image_base64: str) -> bytes:
    if not image_base64 or not image_base64.strip():
        raise ValueError("`image_base64` must not be empty.")

    payload = image_base64.strip()
    if payload.startswith("data:"):
        marker = ";base64,"
        if marker not in payload:
            raise ValueError("Base64 data URL must include `;base64,`.")
        payload = payload.split(marker, 1)[1]

    try:
        return base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("`image_base64` is not valid base64 image data.") from exc
