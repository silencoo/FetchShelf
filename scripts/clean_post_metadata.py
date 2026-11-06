#!/usr/bin/env python3
"""Build a deduplicated copy. Never edits the source database.

Run with the application's Python environment: python -m scripts.clean_post_metadata
SOURCE OUTPUT. Stop source writers before switching to the verified output.
"""
import argparse
import json
import sqlite3
from hashlib import sha256
from pathlib import Path

from src.storage.post_metadata import CONTENT_FIELDS, INTERNAL_FIELDS, meaningful, quote


def clean(source: Path, output: Path):
    if output.exists():
        raise FileExistsError(output)
    work = output.with_suffix('.working.db')
    if work.exists():
        raise FileExistsError(work)
    src = sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True, timeout=30)
    db = sqlite3.connect(work)
    totals = dict(tables=0, input_observations=0, current_posts=0, snapshots=0, unidentified=0, archives_removed=0)
    try:
        src.backup(db, pages=4096)
        src.close()
        db.row_factory = sqlite3.Row
        names = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        tables = []
        for name in names:
            if name.startswith('_'):
                continue
            cols = [r[1] for r in db.execute(f'PRAGMA table_info({quote(name)})')]
            if {'作品ID', '作品描述', '采集时间'}.issubset(cols):
                tables.append((name, cols))
        db.executescript('''
            CREATE TABLE IF NOT EXISTS _post_metadata_tables (table_name TEXT PRIMARY KEY, revision INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS _post_metadata_history (id INTEGER PRIMARY KEY, table_name TEXT NOT NULL,
              post_id TEXT NOT NULL, changed_at TEXT NOT NULL, changed_fields TEXT NOT NULL, metadata TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS _post_history_lookup ON _post_metadata_history(table_name,post_id);
            CREATE TABLE IF NOT EXISTS _post_metadata_legacy (archive_table TEXT PRIMARY KEY, source_table TEXT NOT NULL);
        ''')
        archives = {}
        for archive, original in db.execute('SELECT archive_table,source_table FROM _post_metadata_legacy'):
            # Index names survive account-table renaming; archive provenance keeps the old name.
            idx = '_post_id_' + sha256(original.encode()).hexdigest()[:24]
            owner = db.execute("SELECT tbl_name FROM sqlite_master WHERE type='index' AND name=?", (idx,)).fetchone()
            target = owner[0] if owner else original
            if target not in {t for t, _ in tables}:
                raise ValueError(f'Unresolved legacy archive: {archive}')
            archives.setdefault(target, []).append(archive)
        if set(n for n in names if n.startswith('_legacy_posts_')) != {a for rows in archives.values() for a in rows}:
            raise ValueError('Unregistered legacy archive; refusing to discard history')
        for table, all_cols in tables:
            q = quote(table)
            columns = [c for c in all_cols if c not in INTERNAL_FIELDS]
            active_rows = [dict(r) for r in db.execute(f'SELECT * FROM {q} ORDER BY rowid')]
            events = []
            for archive in archives.get(table, []):
                events.extend((dict(r), '') for r in db.execute(f'SELECT * FROM {quote(archive)} ORDER BY original_rowid'))
            events.extend((json.loads(r['metadata']), r['changed_at']) for r in db.execute(
                'SELECT metadata,changed_at FROM _post_metadata_history WHERE table_name=? ORDER BY id', (table,)))
            events.extend((r, '') for r in active_rows if meaningful(r.get('作品ID')))
            totals['input_observations'] += len(events)
            events.sort(key=lambda pair: str(pair[0].get('采集时间') or ''))
            current, boundaries, snapshots = {}, {}, []
            for row, end_at in events:
                identity = row.get('作品ID')
                if not meaningful(identity):
                    continue
                identity = str(identity)
                seen = row.get('采集时间') or ''
                previous = current.get(identity)
                merged = {c: row.get(c) if meaningful(row.get(c)) or not previous else previous.get(c) for c in columns}
                if previous:
                    if meaningful(previous.get('发布时间')):
                        merged['发布时间'] = previous['发布时间']
                    changed = sorted(c for c in CONTENT_FIELDS if c in columns and meaningful(previous.get(c)) and previous[c] != merged[c])
                    if changed:
                        snapshots.append((table, identity, boundaries.get(identity) or seen,
                                          json.dumps(changed, ensure_ascii=False), json.dumps(previous, ensure_ascii=False)))
                        boundaries.pop(identity, None)
                merged['_first_seen_at'] = previous['_first_seen_at'] if previous else row.get('_first_seen_at') or seen
                merged['_last_seen_at'] = seen
                current[identity] = merged
                if end_at:
                    boundaries[identity] = end_at
            unidentified = [r for r in active_rows if not meaningful(r.get('作品ID'))]
            state = db.execute('SELECT revision FROM _post_metadata_tables WHERE table_name=?', (table,)).fetchone()
            revision = max(state[0] if state else 0, db.execute(f'SELECT COALESCE(MAX(rowid),0) FROM {q}').fetchone()[0])
            with db:
                for col, typ in zip(INTERNAL_FIELDS, ('TEXT', 'TEXT', 'INTEGER')):
                    if col not in all_cols:
                        db.execute(f'ALTER TABLE {q} ADD COLUMN {quote(col)} {typ}')
                db.execute(f'DELETE FROM {q}')
                fields = columns + list(INTERNAL_FIELDS)
                rows = []
                for row in [*current.values(), *unidentified]:
                    revision += 1
                    row['_revision'] = revision
                    rows.append([row.get(c) for c in fields])
                db.executemany(f'INSERT INTO {q} ({",".join(map(quote, fields))}) VALUES ({",".join("?" for _ in fields)})', rows)
                db.execute('DELETE FROM _post_metadata_history WHERE table_name=?', (table,))
                db.executemany('INSERT INTO _post_metadata_history (table_name,post_id,changed_at,changed_fields,metadata) VALUES (?,?,?,?,?)', snapshots)
                db.execute('INSERT OR REPLACE INTO _post_metadata_tables VALUES (?,?)', (table, revision))
                for archive in archives.get(table, []):
                    db.execute(f'DROP TABLE {quote(archive)}')
                    db.execute('DELETE FROM _post_metadata_legacy WHERE archive_table=?', (archive,))
                    totals['archives_removed'] += 1
                suffix = sha256(table.encode()).hexdigest()[:24]
                db.execute(f'''CREATE UNIQUE INDEX IF NOT EXISTS {quote('_post_id_'+suffix)} ON {q} ("作品ID")
                  WHERE "作品ID" IS NOT NULL AND "作品ID" != '' ''')
                db.execute(f'CREATE INDEX IF NOT EXISTS {quote("_post_revision_"+suffix)} ON {q} (_revision)')
                assert db.execute(f'SELECT count(*) FROM {q}').fetchone()[0] == len(current) + len(unidentified)
            totals['tables'] += 1
            totals['current_posts'] += len(current)
            totals['snapshots'] += len(snapshots)
            totals['unidentified'] += len(unidentified)
            if totals['tables'] % 100 == 0:
                print(json.dumps(totals), flush=True)
        print('COMPACT_CLEANED_COPY', flush=True)
        db.execute('VACUUM INTO ?', (str(output),))
        db.close()
        with sqlite3.connect(output) as check:
            assert check.execute('PRAGMA quick_check').fetchall() == [('ok',)]
            assert check.execute('SELECT count(*) FROM _post_metadata_legacy').fetchone()[0] == 0
            for table, _ in tables:
                assert not check.execute(f'''SELECT 1 FROM {quote(table)} WHERE "作品ID" IS NOT NULL AND "作品ID" != ''
                  GROUP BY "作品ID" HAVING count(*)>1 LIMIT 1''').fetchone()
        work.unlink()
        print('CLEANUP_RESULT', json.dumps(totals), flush=True)
        return totals
    finally:
        src.close()
        db.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    report = clean(args.source, args.output)
    args.output.with_suffix(".report.json").write_text(json.dumps(report, indent=2))
