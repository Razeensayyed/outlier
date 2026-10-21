import os
import shutil
import uuid
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse

load_dotenv()

from services.background_removal import remove_background
from services.scene_generator import generate_scene
from services.slide_composer import compose_slides
from services.zip_packager import create_zip

app = FastAPI(title="Carousel Ad Generator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

OUTPUTS_DIR = Path(__file__).parent / "outputs"
OUTPUTS_DIR.mkdir(exist_ok=True)


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = Path(__file__).parent / "static" / "index.html"
    return html_path.read_text()


@app.post("/generate")
async def generate_carousel(
    photos: List[UploadFile] = File(...),
    product_name: str = Form(...),
    brand_name: str = Form(...),
    tagline: Optional[str] = Form(""),
    vibe: str = Form("minimal"),
    primary_color: str = Form("#1a1a1a"),
    accent_color: str = Form("#c9a96e"),
):
    if not photos:
        raise HTTPException(status_code=400, detail="At least one photo is required.")

    job_id = str(uuid.uuid4())
    job_dir = OUTPUTS_DIR / job_id
    job_dir.mkdir(parents=True)

    metadata = {
        "product_name": product_name,
        "brand_name": brand_name,
        "tagline": tagline or "",
        "vibe": vibe,
        "primary_color": primary_color,
        "accent_color": accent_color,
    }

    try:
        for i, photo in enumerate(photos):
            product_dir = job_dir / f"product_{i + 1:02d}"
            product_dir.mkdir()

            raw_path = product_dir / f"raw{Path(photo.filename).suffix or '.jpg'}"
            contents = await photo.read()
            raw_path.write_bytes(contents)

            transparent_path = product_dir / "transparent.png"
            remove_background(str(raw_path), str(transparent_path))

            bg_path = product_dir / "background.png"
            generate_scene(metadata, str(bg_path))

            compose_slides(
                product_png=str(transparent_path),
                background_png=str(bg_path),
                output_dir=str(product_dir),
                metadata=metadata,
            )

        zip_path = OUTPUTS_DIR / f"{job_id}.zip"
        create_zip(str(job_dir), str(zip_path))
        shutil.rmtree(job_dir)

        return {"job_id": job_id, "download_url": f"/download/{job_id}"}

    except Exception as e:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/download/{job_id}")
async def download(job_id: str):
    zip_path = OUTPUTS_DIR / f"{job_id}.zip"
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="Job not found or expired.")
    return FileResponse(
        str(zip_path),
        media_type="application/zip",
        filename=f"carousel_{job_id[:8]}.zip",
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
