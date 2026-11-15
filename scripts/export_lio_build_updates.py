"""Export the same packaged, versioned text shown by Go2China's demo information page."""
import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend/strict_json'))
from cj_strict_json import reject_duplicates

RESOURCE = ROOT / 'ios/Modules/CJShell/Sources/CJLioUser/Resources/LioBuildUpdates.v1.json'


def load_book(path):
    def reject_constant(value):
        raise ValueError('non-finite build update number')
    return json.loads(path.read_text(), object_pairs_hook=reject_duplicates(ValueError, 'duplicate build update field'), parse_constant=reject_constant)


def render(release, language):
    return '\n\n'.join(
        f'{index}. {section["title"][language]}\n' + '\n'.join('- ' + text for text in section['items'][language])
        for index, section in enumerate(release['sections'], 1)
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=int, required=True)
    parser.add_argument('--language', choices=('en', 'zh', 'both'), default='both')
    parser.add_argument('--source-commit', help='Public source commit for the issue heading; never a credential or request identifier.')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    book = load_book(RESOURCE)
    if book['schema'] != 1 or len(book['releases']) != 2:
        parser.error('Unsupported release book')
    matching = [r for r in book['releases'] if r['build'] == args.build]
    if len(matching) != 1:
        parser.error('No notes for this exact build')
    release = matching[0]
    if [s['id'] for s in release['sections']] != ['changes', 'comparison', 'testing', 'known', 'service']:
        parser.error('Five release-note sections are required')
    languages = ('zh', 'en') if args.language == 'both' else (args.language,)
    content = '\n\n'.join((('中文' if language == 'zh' else 'English') + '\n\n' if len(languages) == 2 else '') + render(release, language) for language in languages)
    if args.source_commit:
        if not re.fullmatch(r'[0-9a-f]{40}', args.source_commit):
            parser.error('Expected an exact public source commit')
        content = f'内部构建 {release["build"]}（源 commit {args.source_commit}，上一个构建 {release["previousBuild"]}）\n\n' + content
    if args.output:
        args.output.write_text(content + '\n')
    else:
        print(content)


if __name__ == '__main__':
    main()
