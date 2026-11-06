# Post metadata for media browsing

SQLite post metadata keeps one current row per post ID within each existing
account/export table. This applies to detail-shaped SQLite records (including
mix and search exports); comment/user records and CSV/XLSX exports retain their
existing behavior. Account tables and existing platform separation are retained.
Scrape pagination, date limits, and media download skipping are unchanged.

On each observation:
- A new post gets its first current record.
- An existing post refreshes available metadata, counters, URLs and last-seen time.
- A change to a previously known caption, hashtags, post type or stable video URI
  saves the previous record in `_post_metadata_history`, then updates the current row.
- Collection timestamps, counts, signed URLs, and profile changes do not create
  snapshots. An unchanged observation adds no post or history row.
- Blank, null and `-1` values mean unavailable data and cannot erase known values.
  Zero is valid. Explicit caption removal cannot currently be distinguished from
  a partial response, so a blank caption is conservatively ignored.
- Older observations cannot replace newer metadata. The original publication time
  stays fixed, preserving the feed's file join and chronological ordering.

History contains JSON of the previous metadata, changed field names, and the time
we observed the change. It does not claim to know when the actual edit happened.
Media composition changes are detected only when represented by a stable video
URI or post type; expiring image/download URLs are not reliable content identities.

## Existing databases

Migration runs transactionally when a detail table is next opened for writing.
For a table with repeated nonempty post IDs, it first copies **all original rows**
and their row IDs into `_legacy_posts_<hash>`. `_post_metadata_legacy` maps that
archive to its original table name. The active table retains the latest row per
ID, filling missing fields from earlier observations. Legacy rows lacking a post
ID are retained; new records without a post ID are skipped.

Old observations remain an archive, not newly inferred edit snapshots. No
historical data is deleted from the database. Disk usage may initially grow:
this is not a space-reclamation migration, and it does not run VACUUM. Existing
deployments should have a backup and room for the per-table archive before enabling
writes. Editing this repository does not deploy or migrate the NAS database.

A unique index prevents future duplicate post IDs. `_first_seen_at` and
`_last_seen_at` track observations separately from publication time. `_revision`
increments for every accepted observation; the feed uses it to ingest updates
incrementally and still supports legacy row-ID watermarks. Snapshots and current
row changes commit or roll back together. Legacy archives are excluded from feed
discovery because their names do not start with the account UID prefix.

Future removal of old archives or merging export tables is a separate migration.
