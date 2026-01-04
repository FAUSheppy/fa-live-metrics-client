import os
import requests
from tqdm import tqdm
from urllib.parse import urlparse

def download_file(url: str, dest_dir: str = ".") -> str:

    # Extract filename from URL
    filename = os.path.basename(urlparse(url).path)
    if not filename:
        raise ValueError("Could not determine filename from URL")

    dest_path = os.path.join(dest_dir, filename)

    with requests.get(url, stream=True) as response:
        response.raise_for_status()
        total_size = int(response.headers.get("Content-Length", 0))

        with open(dest_path, "wb") as f, tqdm(
            total=total_size,
            unit="B",
            unit_scale=True,
            unit_divisor=1024,
            desc=filename,
        ) as pbar:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    pbar.update(len(chunk))

    return dest_path