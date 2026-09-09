"""Download the public JMangaBench_Syn benchmark. No account required."""
import argparse, hashlib, json, shutil, tarfile, urllib.request
from pathlib import Path, PurePosixPath
from collections import Counter

URL = "https://github.com/muscgab/JMangaBench_Syn/releases/download/data-v1/JMangaBench_Syn_5000.tar.gz"

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--archive", type=Path, help="Use an already downloaded release archive")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("Output directory must be empty")
    meta = json.loads(Path(__file__).with_name("DATA.json").read_text())
    output.mkdir(parents=True, exist_ok=True)
    archive = args.archive
    if archive is None:
        archive = output / "download.tar.gz"
        request = urllib.request.Request(URL, headers={"User-Agent": "JMangaBench_Syn downloader"})
        with urllib.request.urlopen(request, timeout=120) as src, archive.open("wb") as dst:
            shutil.copyfileobj(src, dst)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != meta["archive_sha256"]:
        raise ValueError("Archive checksum mismatch")
    with tarfile.open(archive) as tar:
        for member in tar:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or not member.isfile():
                raise ValueError("Unsafe archive member")
            if str(path) != "manifest.jsonl" and not (len(path.parts) == 2 and path.parts[0] in meta["subsets"] and path.suffix == ".png"):
                raise ValueError("Unexpected archive member")
            target = output.joinpath(*path.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with tar.extractfile(member) as src, target.open("xb") as dst:
                shutil.copyfileobj(src, dst)
    raw = (output / "manifest.jsonl").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == meta["manifest_sha256"]
    rows = [json.loads(line) for line in raw.splitlines()]
    assert len(rows) == len({r["id"] for r in rows}) == 5000
    assert Counter(r["subset"] for r in rows) == meta["subsets"]
    hashes = set()
    for row in rows:
        image = output / row["image"]
        assert image.resolve().is_relative_to(output)
        digest = hashlib.sha256(image.read_bytes()).hexdigest()
        assert digest == image.stem and digest not in hashes
        hashes.add(digest)
    (output / "download_receipt.json").write_text(json.dumps(meta, indent=2))
    if args.archive is None:
        archive.unlink()
    print("Verified 5,000 images and annotations:", output)

if __name__ == "__main__":
    main()
