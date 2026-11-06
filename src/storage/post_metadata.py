"""Current post metadata and content revisions for SQLite detail loggers.

All mutations run inside the caller's BEGIN IMMEDIATE transaction. Legacy
observations are retained verbatim before consolidating an existing table.
"""
import json
from hashlib import sha256


def quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


# Stable content only: counters, collection times and signed URLs are volatile.
CONTENT_FIELDS = {"作品描述", "作品话题", "作品类型", "视频URI"}
INTERNAL_FIELDS = ("_first_seen_at", "_last_seen_at", "_revision")


def meaningful(value):
    # Extractors use blanks and -1 for absent fields. Zero is a valid counter.
    return value is not None and value not in ("", -1, "-1")


async def prepare(db, table):
    q = quote(table)
    await db.execute("""CREATE TABLE IF NOT EXISTS _post_metadata_tables (
        table_name TEXT PRIMARY KEY, revision INTEGER NOT NULL)""")
    await db.execute("""CREATE TABLE IF NOT EXISTS _post_metadata_history (
        id INTEGER PRIMARY KEY, table_name TEXT NOT NULL, post_id TEXT NOT NULL,
        changed_at TEXT NOT NULL, changed_fields TEXT NOT NULL, metadata TEXT NOT NULL)""")
    await db.execute("""CREATE INDEX IF NOT EXISTS _post_history_lookup
        ON _post_metadata_history(table_name, post_id)""")
    await db.execute("""CREATE TABLE IF NOT EXISTS _post_metadata_legacy (
        archive_table TEXT PRIMARY KEY, source_table TEXT NOT NULL)""")
    state = await db.execute_fetchall(
        "SELECT revision FROM _post_metadata_tables WHERE table_name=?", (table,)
    )
    if state:
        return
    maximum = (await db.execute_fetchall(f"SELECT COALESCE(MAX(rowid),0) FROM {q}"))[0][0]
    duplicate = await db.execute_fetchall(
        f'SELECT 1 FROM {q} WHERE "作品ID" IS NOT NULL AND "作品ID" != \'\' '
        'GROUP BY "作品ID" HAVING count(*) > 1 LIMIT 1'
    )
    if duplicate:
        archive_name = "_legacy_posts_" + sha256(table.encode()).hexdigest()[:24]
        archive = quote(archive_name)
        columns = [r[1] for r in await db.execute_fetchall(f"PRAGMA table_info({q})")]
        originals = await db.execute_fetchall(f"SELECT * FROM {q} ORDER BY rowid")
        consolidated = {}
        first_seen = {}
        for row in originals:
            observation = dict(zip(columns, row))
            identity = observation["作品ID"]
            if not meaningful(identity):
                continue
            known = consolidated.setdefault(identity, {})
            for key, value in observation.items():
                if meaningful(value) or key not in known:
                    known[key] = value
            timestamp = observation.get("采集时间")
            if timestamp:
                first_seen[identity] = min(first_seen.get(identity, timestamp), timestamp)
        # No IF NOT EXISTS: an unexpected archive collision must roll back.
        await db.execute(f"CREATE TABLE {archive} AS SELECT rowid AS original_rowid, * FROM {q}")
        await db.execute("INSERT INTO _post_metadata_legacy VALUES (?, ?)", (archive_name, table))
        await db.execute(f"""DELETE FROM {q} WHERE "作品ID" IS NOT NULL AND "作品ID" != ''
            AND rowid NOT IN (SELECT MAX(rowid) FROM {q} GROUP BY "作品ID")""")
    for column, kind in (("_first_seen_at", "TEXT"), ("_last_seen_at", "TEXT"), ("_revision", "INTEGER")):
        await db.execute(f"ALTER TABLE {q} ADD COLUMN {quote(column)} {kind}")
    await db.execute(f'UPDATE {q} SET _first_seen_at="采集时间", _last_seen_at="采集时间", _revision=rowid')
    if duplicate:
        assignments = ", ".join(f"{quote(key)}=?" for key in columns)
        await db.executemany(
            f'UPDATE {q} SET {assignments}, _first_seen_at=?, _last_seen_at=? WHERE "作品ID"=?',
            [(*[record[key] for key in columns], first_seen.get(identity, ""),
              record.get("采集时间", ""), identity)
             for identity, record in consolidated.items()],
        )
    if maximum:
        # A pre-existing feed watermark may already point at the last legacy
        # row. Publish consolidated/backfilled rows as fresh observations too.
        await db.execute(f"UPDATE {q} SET _revision=rowid+?", (maximum,))
        maximum *= 2
    index = quote("_post_id_" + sha256(table.encode()).hexdigest()[:24])
    await db.execute(f"""CREATE UNIQUE INDEX {index} ON {q} ("作品ID")
        WHERE "作品ID" IS NOT NULL AND "作品ID" != ''""")
    revision_index = quote("_post_revision_" + sha256(table.encode()).hexdigest()[:24])
    await db.execute(f"CREATE INDEX {revision_index} ON {q} (_revision)")
    await db.execute("INSERT INTO _post_metadata_tables VALUES (?, ?)", (table, maximum))


async def save(db, table, columns, data):
    incoming = dict(zip(columns, data))
    post_id = incoming.get("作品ID")
    if not meaningful(post_id):
        # Without identity a record cannot be safely merged or shown as a post.
        return
    q = quote(table)
    fields = ", ".join(map(quote, columns))
    rows = await db.execute_fetchall(
        f'SELECT {fields}, _first_seen_at, _last_seen_at FROM {q} WHERE "作品ID"=?', (post_id,)
    )
    seen = incoming.get("采集时间") or ""
    old = dict(zip((*columns, "_first_seen_at", "_last_seen_at"), rows[0])) if rows else None
    if old and seen and old["_last_seen_at"] and seen < old["_last_seen_at"]:
        return  # A delayed scrape must not roll back newer content.
    merged = {key: value if meaningful(value) or not old else old[key]
              for key, value in incoming.items()}
    if old:
        # Publication time is identity for the feed's media join, not refresh time.
        if meaningful(old.get("发布时间")):
            merged["发布时间"] = old["发布时间"]
        changed = sorted(key for key in CONTENT_FIELDS if key in merged
                         and meaningful(old.get(key)) and merged[key] != old[key])
        if changed:
            await db.execute("""INSERT INTO _post_metadata_history
                (table_name, post_id, changed_at, changed_fields, metadata) VALUES (?, ?, ?, ?, ?)""",
                (table, str(post_id), seen, json.dumps(changed, ensure_ascii=False),
                 json.dumps(old, ensure_ascii=False)))
    await db.execute("UPDATE _post_metadata_tables SET revision=revision+1 WHERE table_name=?", (table,))
    revision = (await db.execute_fetchall(
        "SELECT revision FROM _post_metadata_tables WHERE table_name=?", (table,)
    ))[0][0]
    if old:
        assignments = ", ".join(f"{quote(key)}=?" for key in columns)
        await db.execute(f'UPDATE {q} SET {assignments}, _last_seen_at=?, _revision=? WHERE "作品ID"=?',
                         (*[merged[key] for key in columns], seen or old["_last_seen_at"], revision, post_id))
    else:
        marks = ", ".join("?" for _ in columns)
        await db.execute(f"""INSERT INTO {q}
            ({fields}, _first_seen_at, _last_seen_at, _revision) VALUES ({marks}, ?, ?, ?)""",
            (*[merged[key] for key in columns], seen, seen, revision))
