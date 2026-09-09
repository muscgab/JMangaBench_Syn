"""Download the frozen private benchmark directly from ModelScope on this machine."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tarfile

REPOSITORY = 'muscgab/JmangaBench-Syn-R33-5000-20260909'
MANIFEST_SHA256 = 'bd0dde4fc95891d6aa198afbb9f334403bcdfc7fbf6f960ca763a0ca429a343e'
ARCHIVES = {
    'base4000': '50453b794c41fba7e2ae8042f69f4f40f348900e40abcb0143c152c8c0cff96d',
    'enhanced1000': '4bf0d9c6d74b402bdb874fc4b64387a214b2194fc6130f320d69de77d71aae79',
}


def extract_part(archive: Path, output: Path, name: str) -> list[dict]:
    records = None
    with tarfile.open(archive, 'r:gz') as tar:
        for member in tar:
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts:
                raise ValueError('Unsafe archive path')
            if member.isdir():
                continue
            if not member.isfile() or len(path.parts) < 2:
                raise ValueError('Unexpected archive entry type or layout')
            relative = PurePosixPath(*path.parts[1:])
            stream = tar.extractfile(member)
            if stream is None:
                raise ValueError('Unreadable archive member')
            if str(relative) == 'manifest.jsonl':
                raw = stream.read()
                records = [json.loads(line) for line in raw.splitlines() if line.strip()]
                target = output / 'manifests' / (name + '.jsonl')
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
                continue
            if relative.parts[0] == 'images':
                target = output.joinpath(*relative.parts)
            else:
                target = output / 'reports' / name / str(relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as destination:
                shutil.copyfileobj(stream, destination)
    if records is None:
        raise ValueError('Archive did not contain a manifest')
    return records


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        p.error('Output directory must be empty; an incomplete download is preserved for inspection')
    output.mkdir(parents=True, exist_ok=True)
    from modelscope_hub import HubApi
    api = HubApi(token=os.environ.get('MODELSCOPE_API_TOKEN'))
    records = []
    for name, expected in ARCHIVES.items():
        path = api.download_file(REPOSITORY, 'dataset', 'data/' + name + '.tar.gz',
                                 local_dir=output / '.downloads', expected_sha256=expected)
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError('Archive checksum mismatch: ' + name)
        records.extend(extract_part(path, output, name))
    if len(records) != 5000 or len({r['id'] for r in records}) != 5000:
        raise ValueError('Expected 5000 unique sample IDs')
    if Counter(r['subset'] for r in records) != {'real': 2000, 'realscan': 2000, 'enhanced': 1000}:
        raise ValueError('Unexpected subset counts')
    seen = set()
    for row in records:
        image = output / row['image']
        if not image.resolve().is_relative_to(output):
            raise ValueError('Unsafe manifest image path')
        digest = hashlib.sha256(image.read_bytes()).hexdigest()
        if digest != image.stem or digest in seen:
            raise ValueError('Image checksum mismatch or duplicate PNG bytes')
        seen.add(digest)
    manifest = ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in records)
    if hashlib.sha256(manifest.encode()).hexdigest() != MANIFEST_SHA256:
        raise ValueError('Frozen manifest checksum mismatch')
    (output / 'manifest.jsonl').write_text(manifest, encoding='utf-8')
    receipt = {'repo': REPOSITORY, 'images': 5000, 'unique_png_sha256': len(seen),
               'archive_sha256': ARCHIVES,
               'manifest_sha256': hashlib.sha256(manifest.encode()).hexdigest()}
    (output / 'download_receipt.json').write_text(json.dumps(receipt, indent=2))
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
