"""Read-only inventory of a dataset, using Python's standard library."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat


def is_link(path):
    info = path.lstat()
    return path.is_symlink() or bool(
        getattr(info, 'st_file_attributes', 0)
        & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0)
    )


def audit(root):
    files, errors, skipped = [], [], []
    def walk_error(error):
        errors.append({'path': str(error.filename), 'error': str(error)})
    for directory, dirs, names in os.walk(root, followlinks=False, onerror=walk_error):
        for name in list(dirs):
            path = Path(directory) / name
            try:
                if is_link(path):
                    dirs.remove(name)
                    skipped.append(str(path.relative_to(root)))
            except OSError as error:
                dirs.remove(name)
                errors.append({'path': str(path.relative_to(root)), 'error': str(error)})
        dirs.sort()
        for name in sorted(names):
            path = Path(directory) / name
            relative = str(path.relative_to(root))
            try:
                if is_link(path) or not path.is_file():
                    skipped.append(relative)
                    continue
                before = path.stat()
                digest = hashlib.sha256()
                with path.open('rb') as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b''):
                        digest.update(block)
                after = path.stat()
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise OSError('File changed while hashing; repeat audit after download completes')
                files.append({'path': relative, 'bytes': after.st_size,
                              'extension': path.suffix.lower() or '(none)',
                              'sha256': digest.hexdigest()})
            except OSError as error:
                errors.append({'path': relative, 'error': str(error)})
    by_hash = defaultdict(list)
    for item in files:
        by_hash[item['sha256']].append(item['path'])
    return {'created_utc': datetime.now(timezone.utc).isoformat(),
            'root': str(root), 'file_count': len(files),
            'total_bytes': sum(f['bytes'] for f in files),
            'extensions': dict(Counter(f['extension'] for f in files)),
            'duplicate_groups': [paths for paths in by_hash.values() if len(paths) > 1],
            'files': files, 'skipped_links_or_special_files': skipped, 'errors': errors,
            'scope': 'Inventory only. No sensor decoding or detection quality claims.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    root, output = args.input.resolve(), args.output.resolve()
    if not root.is_dir():
        parser.error('Input must be an existing directory')
    if output.is_relative_to(root):
        parser.error('Output must be outside input directory to keep inventory reproducible')
    report = audit(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"Files: {report['file_count']}; bytes: {report['total_bytes']}; errors: {len(report['errors'])}")
    print(f'Report: {output}')
    return 1 if report['errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
