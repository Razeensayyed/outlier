import os
import requests
import replicate
from io import BytesIO
from PIL import Image


VIBE_PROMPTS = {
    "luxury": (
        "luxury lifestyle product photography background, marble surface, "
        "elegant soft lighting, gold and cream tones, high-end editorial, "
        "soft bokeh, no objects, no products, no text"
    ),
    "minimal": (
        "minimalist clean studio background, soft white gradient, "
        "subtle shadow beneath, professional product photography, "
        "no objects, no products, no text"
    ),
    "bold": (
        "vibrant bold advertisement background, rich saturated colors, "
        "dynamic brushstroke texture, energetic and modern, "
        "no objects, no products, no text"
    ),
    "playful": (
        "fun pastel background for product photography, soft confetti texture, "
        "cheerful warm tones, light airy aesthetic, "
        "no objects, no products, no text"
    ),
}


def generate_scene(metadata: dict, output_path: str) -> None:
    vibe = metadata.get("vibe", "minimal")
    product_name = metadata.get("product_name", "product")

    base = VIBE_PROMPTS.get(vibe, VIBE_PROMPTS["minimal"])
    prompt = f"Advertisement background for {product_name}, {base}, 1080x1080, ultra HD"

    output = replicate.run(
        "black-forest-labs/flux-schnell",
        input={
            "prompt": prompt,
            "width": 1080,
            "height": 1080,
            "num_outputs": 1,
            "output_format": "png",
            "go_fast": True,
        },
    )

    img_url = str(output[0])
    response = requests.get(img_url, timeout=60)
    response.raise_for_status()

    img = Image.open(BytesIO(response.content)).convert("RGB")
    img = img.resize((1080, 1080), Image.LANCZOS)
    img.save(output_path, "PNG")
