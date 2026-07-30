"""Standalone FastAPI service for CaVDesign image preparation.

Run alongside the main backend:
    uvicorn image_api:app --reload --port 8001
"""

from __future__ import annotations

import io
import json
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from src.image_toolkit import (
    ImageToolkitError,
    inspect_image,
    optimize_under_limit,
    tile_bundle,
    upscale_image,
)

app = FastAPI(title="CaVDesign Image Toolkit", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "X-CaVDesign-Manifest"],
)

ALLOWED_MIME_TYPES = {"image/png", "image/jpeg", "image/webp"}
MAX_UPLOAD_SIZE = 250 * 1024 * 1024


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "image-toolkit"}


async def _read_upload(file: UploadFile) -> bytes:
    mime = file.content_type or ""
    if mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported image type: {mime}")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(data) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="Maximum upload size is 250 MB.")
    return data


def _response(data: bytes, filename: str, media_type: str, manifest: dict) -> StreamingResponse:
    response = StreamingResponse(io.BytesIO(data), media_type=media_type)
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.headers["X-CaVDesign-Manifest"] = json.dumps(manifest, separators=(",", ":"))
    return response


@app.post("/api/image/inspect")
async def image_inspect(file: UploadFile = File(...)) -> dict:
    data = await _read_upload(file)
    try:
        info = inspect_image(data)
    except ImageToolkitError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "width": info.width,
        "height": info.height,
        "mode": info.mode,
        "source_bytes": info.source_bytes,
    }


@app.post("/api/image/process")
async def image_process(
    file: UploadFile = File(...),
    operation: Literal["optimize", "upscale", "tiles"] = Form(...),
    target_mb: float = Form(49.0),
    preferred_format: Literal["auto", "jpeg", "webp", "png"] = Form("auto"),
    factor: int = Form(2),
    sharpen: bool = Form(True),
    columns: int = Form(2),
    rows: int = Form(2),
    overlap_px: int = Form(32),
    tile_format: Literal["png", "webp"] = Form("png"),
):
    data = await _read_upload(file)
    stem = (file.filename or "image").rsplit(".", 1)[0]
    try:
        if operation == "optimize":
            output, extension, manifest = optimize_under_limit(
                data,
                target_mb=target_mb,
                preferred_format=preferred_format,
            )
            mime = {"png": "image/png", "webp": "image/webp", "jpeg": "image/jpeg"}[extension]
            return _response(output, f"{stem}_canva.{extension}", mime, manifest)

        if operation == "upscale":
            output, manifest = upscale_image(data, factor=factor, sharpen=sharpen)
            return _response(output, f"{stem}_{factor}x.png", "image/png", manifest)

        output, manifest = tile_bundle(
            data,
            columns=columns,
            rows=rows,
            overlap_px=overlap_px,
            output_format=tile_format,
        )
        return _response(output, f"{stem}_canva_tiles.zip", "application/zip", manifest)
    except ImageToolkitError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Image processing failed: {exc}") from exc
