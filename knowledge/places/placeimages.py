"""The place image manifest: every picture is an AI illustration, labelled as one (#1987, F-5).

JT decided (2026-11-27) that place pictures are generated flat illustrations, not photos, and that the
place page and the bubble card say "示意图". The binaries (1600x1200 main, 512x512 thumbnail) are too big
for git and are stored outside it; what is committed is `images/manifest.v1.json`, which records for each
picture its file names, exact pixel size, SHA-256, licence, label and the prompt that made it. This
module validates that manifest, and (given the Codex output folder) the files themselves.

Codex's `codex-inbox/C2/manifest.json` entry is {id, file, thumb, prompt, model, generated_at, license,
note}; `build_manifest` turns a folder of such pictures into the committed manifest, measuring sizes and
hashes itself instead of trusting the draft.
"""
import hashlib
import json
from pathlib import Path
import re
import struct

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import placelib  # noqa: E402

VERSION = 'g2c-place-images.1'
MANIFEST = placelib.PLACES_DIR / 'images/manifest.v1.json'
MAIN_SIZE, THUMB_SIZE = (1600, 1200), (512, 512)
LICENSE = 'ai-generated'
LABEL_ZH, LABEL_EN = '示意图', 'Illustration'
KEYS = ('id', 'file', 'thumb', 'width', 'height', 'thumb_width', 'thumb_height', 'sha256', 'thumb_sha256', 'license',
        'label_zh', 'label_en', 'prompt', 'model', 'generated_at', 'note')
PNG_MAGIC = b'\x89PNG\r\n\x1a\n'
MAX_BYTES = 12 * 1024 * 1024


def png_size(data):
    """(width, height) of a PNG from its header, or raise Invalid."""
    if data[:8] != PNG_MAGIC or data[12:16] != b'IHDR' or len(data) < 24:
        raise placelib.Invalid('not a PNG file')
    return struct.unpack('>II', data[16:24])


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def check_entry(item, where):
    placelib._require(type(item) is dict and set(item) == set(KEYS), f'{where}: keys must be exactly {list(KEYS)}')
    ident = item['id']
    placelib._require(type(ident) is str and re.fullmatch(r'pl_[a-z]{2}_[a-z0-9]+(_[a-z0-9]+)*', ident) is not None, f'{where}.id')
    where = ident
    placelib._require(item['file'] == f'{ident}.png' and item['thumb'] == f'{ident}_thumb.png', f'{where}: file names must be <id>.png and <id>_thumb.png')
    placelib._require((item['width'], item['height']) == MAIN_SIZE, f'{where}: main picture must be {MAIN_SIZE[0]}x{MAIN_SIZE[1]}')
    placelib._require((item['thumb_width'], item['thumb_height']) == THUMB_SIZE, f'{where}: thumbnail must be {THUMB_SIZE[0]}x{THUMB_SIZE[1]}')
    for key in ('sha256', 'thumb_sha256'):
        placelib._require(type(item[key]) is str and re.fullmatch(r'[0-9a-f]{64}', item[key]) is not None, f'{where}.{key}')
    placelib._require(item['sha256'] != item['thumb_sha256'], f'{where}: thumbnail is the same file as the main picture')
    placelib._require(item['license'] == LICENSE, f'{where}.license: must be {LICENSE!r}, got {item["license"]!r}')
    placelib._require(item['label_zh'] == LABEL_ZH and item['label_en'] == LABEL_EN, f'{where}: must be labelled {LABEL_ZH} / {LABEL_EN}')
    placelib.text(item['prompt'], f'{where}.prompt', limit=2000)
    placelib.text(item['model'], f'{where}.model', limit=200)
    placelib.day(item['generated_at'], f'{where}.generated_at')
    placelib.text(item['note'], f'{where}.note', nullable=True)


def load_manifest(path=MANIFEST, raw=None):
    """The validated manifest document; raise Invalid on the first problem."""
    text = (Path(path).read_bytes() if raw is None else raw).decode('utf-8')
    doc = json.loads(text, object_pairs_hook=placelib._pairs)
    placelib._require(type(doc) is dict and set(doc) == {'version', 'images'}, 'manifest keys: version, images')
    placelib._require(doc['version'] == VERSION, 'version')
    placelib._require(type(doc['images']) is list, 'images: a list')
    seen = set()
    for index, item in enumerate(doc['images']):
        check_entry(item, f'images[{index}]')
        placelib._require(item['id'] not in seen, f'{item["id"]}: duplicate image')
        seen.add(item['id'])
    ids = [item['id'] for item in doc['images']]
    placelib._require(ids == sorted(ids), 'images must be sorted by id')
    return doc


def thumbs(path=MANIFEST):
    """{place id: thumbnail file name} for the App copy."""
    return {item['id']: item['thumb'] for item in load_manifest(path)['images']}


def check_files(doc, folder):
    """Problems (strings) between a manifest and the picture files in `folder`: missing, wrong size, wrong hash."""
    problems = []
    for item in doc['images']:
        for name, size, digest in ((item['file'], MAIN_SIZE, item['sha256']), (item['thumb'], THUMB_SIZE, item['thumb_sha256'])):
            path = Path(folder) / name
            if not path.is_file():
                problems.append(f'{item["id"]}: {name} is missing')
                continue
            data = path.read_bytes()
            try:
                found = png_size(data)
            except placelib.Invalid:
                problems.append(f'{item["id"]}: {name} is not a PNG')
                continue
            if found != size:
                problems.append(f'{item["id"]}: {name} is {found[0]}x{found[1]}, expected {size[0]}x{size[1]}')
            if sha256(data) != digest:
                problems.append(f'{item["id"]}: {name} differs from the manifest (hash)')
    return problems


def coverage(doc, library_docs, require_all_main=False):
    """Problems between the manifest and the library: a picture for an unknown place, or (optionally) a main
    attraction without one. Run at release time; pictures arrive before their place is approved."""
    known = {p['id']: p for d in library_docs for p in d['places']}
    problems = [f'{item["id"]}: picture for a place that is not in the library' for item in doc['images'] if item['id'] not in known]
    if require_all_main:
        have = {item['id'] for item in doc['images']}
        problems += [f'{pid}: no picture' for pid, p in sorted(known.items())
                     if p['tier'] == 'main' and p['category'] == 'attraction' and pid not in have]
    return problems


def build_manifest(folder, today):
    """Build the manifest from a Codex C2 folder. Returns (document, rejected) where rejected is [(id, reason)].

    Sizes and hashes are measured from the files; the draft's own claims are not used. An entry that is not
    `ai-generated`, has a missing or wrongly sized file, or has no prompt or model is rejected, not fixed.
    """
    folder = Path(folder)
    drafts = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    placelib._require(type(drafts) is list, 'C2 manifest must be a list')
    images, rejected = [], []
    for draft in drafts:
        ident = draft.get('id') if isinstance(draft, dict) else None
        try:
            placelib._require(isinstance(draft, dict), 'not an object')
            main, thumb = (folder / str(draft.get('file'))), (folder / str(draft.get('thumb')))
            placelib._require(main.is_file() and thumb.is_file(), 'a picture file is missing')
            placelib._require(main.stat().st_size <= MAX_BYTES and thumb.stat().st_size <= MAX_BYTES, 'picture file is too large')
            main_bytes, thumb_bytes = main.read_bytes(), thumb.read_bytes()
            (w, h), (tw, th) = png_size(main_bytes), png_size(thumb_bytes)
            item = {'id': ident, 'file': draft.get('file'), 'thumb': draft.get('thumb'), 'width': w, 'height': h,
                    'thumb_width': tw, 'thumb_height': th, 'sha256': sha256(main_bytes), 'thumb_sha256': sha256(thumb_bytes),
                    'license': draft.get('license'), 'label_zh': LABEL_ZH, 'label_en': LABEL_EN, 'prompt': draft.get('prompt'),
                    'model': draft.get('model'), 'generated_at': draft.get('generated_at'), 'note': draft.get('note')}
            check_entry(item, str(ident))
            placelib._require(ident not in {i['id'] for i in images}, 'duplicate id')
            images.append(item)
        except (placelib.Invalid, OSError) as error:
            rejected.append((ident, str(error)))
    images.sort(key=lambda i: i['id'])
    return {'version': VERSION, 'images': images}, rejected


def dumps(doc):
    return json.dumps(doc, ensure_ascii=False, indent=2) + '\n'
