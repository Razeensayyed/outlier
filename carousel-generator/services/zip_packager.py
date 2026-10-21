import os
import zipfile
from pathlib import Path


def create_zip(source_dir: str, output_zip: str) -> None:
    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(source_dir):
            for file in sorted(files):
                # skip raw uploads, keep only generated slides
                if file.startswith("raw") or file == "background.png" or file == "transparent.png":
                    continue
                filepath = os.path.join(root, file)
                arcname = os.path.relpath(filepath, source_dir)
                zf.write(filepath, arcname)
