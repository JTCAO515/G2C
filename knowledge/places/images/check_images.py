"""Build and check the place image manifest (#1987, F-5).

  python3 -B knowledge/places/images/check_images.py build ../codex-inbox/C2 --today 2026-11-30
      read Codex's C2 folder (manifest.json + PNGs), measure sizes and hashes, reject entries that are not
      `ai-generated`/1600x1200 + 512x512 PNG, and write knowledge/places/images/manifest.v1.json
  python3 -B knowledge/places/images/check_images.py check [--files ../codex-inbox/C2] [--release]
      validate the committed manifest; with --files also the picture files; with --release also that every
      picture belongs to a library place and every main attraction has one
"""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import placeimages  # noqa: E402
import placelib  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    build = sub.add_parser('build')
    build.add_argument('folder')
    build.add_argument('--today', required=True)
    build.add_argument('--manifest', default=str(placeimages.MANIFEST))
    check = sub.add_parser('check')
    check.add_argument('--files')
    check.add_argument('--release', action='store_true')
    check.add_argument('--manifest', default=str(placeimages.MANIFEST))
    args = parser.parse_args(argv)
    try:
        if args.command == 'build':
            placelib.day(args.today, '--today')
            doc, rejected = placeimages.build_manifest(args.folder, args.today)
            for ident, reason in rejected:
                print(f'REJECTED {ident}: {reason}', file=sys.stderr)
            target = Path(args.manifest)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(placeimages.dumps(doc), encoding='utf-8')
            placeimages.load_manifest(target)  # what we wrote must itself be valid
            print(f'wrote {len(doc["images"])} images to {target}; {len(rejected)} rejected')
            return 1 if rejected else 0
        doc = placeimages.load_manifest(args.manifest)
        problems = placeimages.check_files(doc, args.files) if args.files else []
        if args.release:
            docs = [placelib.load_city(path) for path in placelib.city_files()]
            problems += placeimages.coverage(doc, docs, require_all_main=True)
        for problem in problems:
            print(f'FAIL: {problem}', file=sys.stderr)
        if not problems:
            print(f'PASS: {len(doc["images"])} images, all ai-generated and labelled 示意图')
        return 1 if problems else 0
    except placelib.Invalid as error:
        print(f'FAIL: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
