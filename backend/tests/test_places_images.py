"""The place image manifest: AI illustrations only, labelled 示意图, exact sizes and hashes (#1987)."""
import copy
import json
from pathlib import Path
import struct
import sys
import zlib

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'knowledge/places'))
sys.path.insert(0, str(ROOT / 'knowledge/places/images'))
sys.path.insert(0, str(ROOT / 'backend/tests'))
import check_images  # noqa: E402
import generate  # noqa: E402
import placeimages as images  # noqa: E402
import placelib  # noqa: E402
from test_places_pipeline import C1, library_entry, city_doc, write_city, layout as pipeline_layout  # noqa: E402


def png(width, height):
    """A real, tiny-on-disk grey PNG of the given size."""
    def chunk(kind, body):
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))
    rows = zlib.compress((b'\x00' + b'\xf6' * width) * height, 9)
    return images.PNG_MAGIC + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 0, 0, 0, 0)) + chunk(b'IDAT', rows) + chunk(b'IEND', b'')


def make_folder(tmp_path, ids=('pl_bj_gugong',), **draft_change):
    folder = tmp_path / 'C2'
    folder.mkdir()
    manifest = []
    for n, ident in enumerate(ids):
        (folder / f'{ident}.png').write_bytes(png(*images.MAIN_SIZE) + bytes([n]) * 0)
        (folder / f'{ident}_thumb.png').write_bytes(png(*images.THUMB_SIZE))
        manifest.append({'id': ident, 'file': f'{ident}.png', 'thumb': f'{ident}_thumb.png', 'prompt': 'Flat illustration of the Meridian Gate, warm palette, no text.',
                         'model': 'image-model-1', 'generated_at': '2026-11-30', 'license': 'ai-generated', 'note': None, **draft_change})
    (folder / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    return folder


def test_a_clean_codex_folder_becomes_a_valid_manifest(tmp_path):
    doc, rejected = images.build_manifest(make_folder(tmp_path, ('pl_bj_tiantan', 'pl_bj_gugong')), '2026-11-30')
    assert rejected == [] and [i['id'] for i in doc['images']] == ['pl_bj_gugong', 'pl_bj_tiantan']
    item = doc['images'][0]
    assert (item['width'], item['height'], item['thumb_width'], item['thumb_height']) == (1600, 1200, 512, 512)
    assert item['label_zh'] == '示意图' and item['label_en'] == 'Illustration' and len(item['sha256']) == 64
    path = tmp_path / 'manifest.v1.json'
    path.write_text(images.dumps(doc), encoding='utf-8')
    assert images.load_manifest(path)['images'] == doc['images']
    assert images.check_files(doc, tmp_path / 'C2') == []


@pytest.mark.parametrize('change', [
    {'license': 'CC-BY-4.0'},            # only our own generated pictures
    {'license': None},
    {'license': 'AI-Generated'},
    {'prompt': None},
    {'model': ''},
    {'generated_at': '30/11/2026'},
    {'thumb': 'missing.png'},
])
def test_entries_that_are_not_ai_generated_or_incomplete_are_rejected_not_fixed(tmp_path, change):
    doc, rejected = images.build_manifest(make_folder(tmp_path, **change), '2026-11-30')
    assert doc['images'] == [] and rejected and rejected[0][0] == 'pl_bj_gugong'


def test_wrong_picture_sizes_are_rejected(tmp_path):
    folder = make_folder(tmp_path)
    (folder / 'pl_bj_gugong.png').write_bytes(png(800, 600))
    assert images.build_manifest(folder, '2026-11-30')[1]
    again = tmp_path / 'again'
    again.mkdir()
    folder = make_folder(again)
    (folder / 'pl_bj_gugong_thumb.png').write_bytes(b'not a png at all, just text')
    assert 'not a PNG' in images.build_manifest(folder, '2026-11-30')[1][0][1]


def test_duplicate_ids_and_a_thumbnail_that_is_the_main_file(tmp_path):
    folder = make_folder(tmp_path, ('pl_bj_gugong', 'pl_bj_gugong'))
    assert [r[1] for r in images.build_manifest(folder, '2026-11-30')[1]] == ['duplicate id']


def _valid(tmp_path):
    doc, _ = images.build_manifest(make_folder(tmp_path), '2026-11-30')
    return doc


@pytest.mark.parametrize('change', [
    lambda i: i.update(license='ai-generated '),
    lambda i: i.update(label_zh='插画'),
    lambda i: i.update(label_en=''),
    lambda i: i.update(width=1200),
    lambda i: i.update(thumb_height=511),
    lambda i: i.update(sha256='abc'),
    lambda i: i.update(thumb_sha256=i['sha256']),
    lambda i: i.update(file='other.png'),
    lambda i: i.update(id='gugong'),
    lambda i: i.update(extra=1),
    lambda i: i.pop('prompt'),
])
def test_committed_manifest_rejects_a_broken_entry(tmp_path, change):
    doc = _valid(tmp_path)
    change(doc['images'][0])
    path = tmp_path / 'manifest.v1.json'
    path.write_text(images.dumps(doc), encoding='utf-8')
    with pytest.raises(placelib.Invalid):
        images.load_manifest(path)


def test_manifest_must_be_sorted_and_unique(tmp_path):
    doc, _ = images.build_manifest(make_folder(tmp_path, ('pl_bj_gugong', 'pl_bj_tiantan')), '2026-11-30')
    doc['images'].reverse()
    with pytest.raises(placelib.Invalid):
        images.load_manifest(tmp_path / 'x.json', raw=images.dumps(doc).encode('utf-8'))


def test_check_files_finds_missing_resized_and_swapped_pictures(tmp_path):
    doc = _valid(tmp_path)
    folder = tmp_path / 'C2'
    (folder / 'pl_bj_gugong.png').write_bytes(png(1600, 1200)[:-1] + b'\x00')       # same size, different bytes
    (folder / 'pl_bj_gugong_thumb.png').unlink()
    problems = images.check_files(doc, folder)
    assert any('hash' in p for p in problems) and any('missing' in p for p in problems)


def test_release_coverage(tmp_path):
    doc = _valid(tmp_path)
    gugong = library_entry(C1)
    other = library_entry(C1, id='pl_bj_other', name_zh='别处', name_en='Elsewhere', aliases_zh=[], aliases_en=[], rank=2)
    assert images.coverage(doc, [city_doc(gugong)], require_all_main=True) == []
    assert 'pl_bj_other: no picture' in images.coverage(doc, [city_doc(gugong, other)], require_all_main=True)
    assert images.coverage(doc, [city_doc(other)]) == ['pl_bj_gugong: picture for a place that is not in the library']


def test_app_copy_carries_the_thumbnail_name_from_the_manifest(tmp_path):
    lay = pipeline_layout(tmp_path)._replace(images_path=tmp_path / 'manifest.v1.json')
    write_city(tmp_path, city_doc(library_entry(C1)))
    doc = _valid(tmp_path)
    lay.images_path.write_text(images.dumps(doc), encoding='utf-8')
    generate.write(lay)
    app = json.loads(lay.app_path.read_text(encoding='utf-8'))
    assert app['places'][0]['thumb'] == 'pl_bj_gugong_thumb.png'
    lay.images_path.unlink()
    assert generate.stale(lay)                       # a place that lost its picture changes the App copy


def test_cli_build_and_check(tmp_path, capsys):
    folder = make_folder(tmp_path)
    target = tmp_path / 'out' / 'manifest.v1.json'
    assert check_images.main(['build', str(folder), '--today', '2026-11-30', '--manifest', str(target)]) == 0
    assert check_images.main(['check', '--manifest', str(target), '--files', str(folder)]) == 0
    (folder / 'pl_bj_gugong.png').write_bytes(png(1600, 1200)[:-1] + b'\x01')
    assert check_images.main(['check', '--manifest', str(target), '--files', str(folder)]) == 1


def test_committed_manifest_is_valid():
    if images.MANIFEST.is_file():
        doc = images.load_manifest()
        assert all(i['license'] == 'ai-generated' and i['label_zh'] == '示意图' for i in doc['images'])
