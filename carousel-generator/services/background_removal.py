import os
import requests


def remove_background(input_path: str, output_path: str) -> None:
    api_key = os.environ.get("REMOVEBG_API_KEY", "")
    if not api_key:
        raise RuntimeError("REMOVEBG_API_KEY is not set.")

    with open(input_path, "rb") as f:
        response = requests.post(
            "https://api.remove.bg/v1.0/removebg",
            files={"image_file": f},
            data={"size": "auto"},
            headers={"X-Api-Key": api_key},
            timeout=60,
        )

    if response.status_code != 200:
        raise RuntimeError(
            f"Remove.bg error {response.status_code}: {response.text}"
        )

    with open(output_path, "wb") as f:
        f.write(response.content)
