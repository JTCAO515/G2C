"""Offline candidate-package inventory checks; never grants restore/read authority."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import PurePosixPath
import re
import stat
import sys

FORMAT = 'cj027-offline-candidate-v1'
MANIFEST_LIMIT = 1024 * 1024
FILE_LIMIT = 10000


def parts(path):
    if not isinstance(path, str) or not path or '\\' in path or '\x00' in path:
        raise ValueError('unsafe_path')
    p = PurePosixPath(path)
    if p.is_absolute() or any(s in ('', '.', '..') for s in path.split('/')):
        raise ValueError('unsafe_path')
    return path.split('/')


def open_beneath(directory, path, directory_only=False):
    """Traverse pinned descriptors, refusing symlinks at every component."""
    components = parts(path)
    current = os.dup(directory)
    try:
        for index, component in enumerate(components):
            is_dir = index < len(components) - 1 or directory_only
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            if is_dir:
                flags |= os.O_DIRECTORY
            if not is_dir:
                declared = os.stat(component, dir_fd=current, follow_symlinks=False)
                if not stat.S_ISREG(declared.st_mode) or declared.st_nlink != 1:
                    raise ValueError('not_single_link_regular_file')
            following = os.open(component, flags, dir_fd=current)
            os.close(current)
            current = following
        info = os.fstat(current)
        if not directory_only and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
            raise ValueError('not_single_link_regular_file')
        result, current = current, None
        return result
    finally:
        if current is not None:
            os.close(current)


def open_root(path):
    if not isinstance(path, str) or not path.startswith('/'):
        raise ValueError('absolute_root_required')
    anchor = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        return open_beneath(anchor, path[1:], directory_only=True)
    finally:
        os.close(anchor)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate_json_key')
        result[key] = value
    return result


def inspect(root, manifest):
    report = {'input_format': FORMAT, 'checks': [], 'missing_files': [],
              'restore_authorization': 'UNRUN', 'read_enable': False}

    def check(item, status, reason):
        report['checks'].append({'item': item, 'status': status, 'reason': reason})

    root_fd = None
    try:
        root_fd = open_root(root)
        fd = open_beneath(root_fd, manifest)
        with os.fdopen(fd, 'rb') as source:
            raw = source.read(MANIFEST_LIMIT + 1)
        if len(raw) > MANIFEST_LIMIT:
            raise ValueError('manifest_too_large')
        data = json.loads(raw, object_pairs_hook=unique_object)
        if not isinstance(data, dict):
            raise ValueError('manifest_not_object')
    except (OSError, ValueError, RecursionError):
        check('manifest', 'FAIL', 'missing_unreadable_unsafe_or_invalid_manifest')
        if root_fd is not None:
            os.close(root_fd)
        return finish(report)

    try:
        version = data.get('manifest_version')
        check('manifest_version', 'PASS' if version == FORMAT else
              ('UNKNOWN' if version is None else 'FAIL'),
              'supported_internal_candidate_format' if version == FORMAT else 'unsupported_or_missing_version')
        commit = data.get('candidate_commit')
        valid_commit = isinstance(commit, str) and re.fullmatch('[0-9a-f]{40}', commit)
        check('candidate_commit', 'PASS' if valid_commit else ('UNKNOWN' if commit is None else 'FAIL'),
              'syntactically_explicit_only' if valid_commit else 'missing_or_invalid_commit')
        timestamp = data.get('backup_time')
        try:
            parsed = dt.datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            valid_time = parsed.utcoffset() is not None
        except (AttributeError, TypeError, ValueError, OverflowError):
            valid_time = False
        check('backup_time', 'PASS' if valid_time else ('UNKNOWN' if timestamp is None else 'FAIL'),
              'explicit_offset_time_not_freshness_proof' if valid_time else 'missing_or_invalid_offset_time')
        versions = data.get('component_versions')
        valid_versions = (isinstance(versions, dict) and bool(versions) and
                          all(isinstance(k, str) and k.strip() and isinstance(v, str) and
                              v.strip() and v.strip().lower() not in ('unknown', 'unrun', 'latest', '*')
                              for k, v in versions.items()))
        check('component_versions', 'PASS' if valid_versions else 'UNKNOWN',
              'declared_only_coverage_and_compatibility_unverified' if valid_versions else 'versions_not_explicit')
        entries = data.get('files')
        if not isinstance(entries, list) or not entries or len(entries) > FILE_LIMIT:
            check('files', 'FAIL', 'nonempty_bounded_inventory_required')
            entries = []
        seen = set()
        for index, entry in enumerate(entries):
            label = f'files[{index}]'
            if not isinstance(entry, dict):
                check(label, 'FAIL', 'entry_not_object')
                continue
            path = entry.get('path')
            try:
                parts(path)
            except ValueError:
                check(label, 'FAIL', 'unsafe_path')
                continue
            if path in seen:
                check(label, 'FAIL', 'duplicate_path')
                continue
            seen.add(path)
            size, digest = entry.get('size_bytes'), entry.get('sha256')
            if (type(size) is not int or size < 0 or not isinstance(digest, str) or
                    re.fullmatch('[0-9a-f]{64}', digest) is None):
                check(label, 'FAIL', 'invalid_size_or_sha256')
                continue
            try:
                fd = open_beneath(root_fd, path)
                with os.fdopen(fd, 'rb') as source:
                    before = os.fstat(source.fileno())
                    if before.st_size != size:
                        check(label, 'FAIL', 'size_mismatch')
                        continue
                    actual = hashlib.sha256()
                    count = 0
                    while True:
                        block = source.read(min(65536, size - count + 1))
                        if not block:
                            break
                        actual.update(block)
                        count += len(block)
                        if count > size:
                            break
                    after = os.fstat(source.fileno())
                stable = ((before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                          (after.st_size, after.st_mtime_ns, after.st_ctime_ns))
                good = stable and count == size and actual.hexdigest() == digest
                check(label, 'PASS' if good else 'FAIL',
                      'local_bytes_match_declaration_only' if good else 'hash_or_concurrent_change_mismatch')
            except FileNotFoundError:
                report['missing_files'].append(path)
                check(label, 'FAIL', 'missing_file')
            except (OSError, ValueError):
                check(label, 'FAIL', 'unreadable_or_not_safe_regular_file')
        for item in ('actual_restore', 'application_compatibility', 'latest_withdrawal_replay'):
            check(item, 'UNKNOWN', 'external_evidence_not_verified_by_offline_tool')
    finally:
        os.close(root_fd)
    return finish(report)


def finish(report):
    statuses = {c['status'] for c in report['checks']}
    report['offline_check_status'] = 'FAIL' if 'FAIL' in statuses else 'UNKNOWN' if 'UNKNOWN' in statuses else 'PASS'
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, help='Explicit absolute local package directory, without symlink components')
    parser.add_argument('--manifest', required=True, help='Explicit package-relative candidate JSON manifest')
    args = parser.parse_args(argv)
    report = inspect(args.root, args.manifest)
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 1 if report['offline_check_status'] == 'FAIL' else 2


if __name__ == '__main__':
    sys.exit(main())
