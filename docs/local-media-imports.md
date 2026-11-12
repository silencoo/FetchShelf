# Local media accounts

Immersive browsing supports separate Douyin, TikTok, Kuaishou, Rednote, and Weibo libraries. The selected platform filters discovery, search, feeds, likes, saves, and follows. The selection is remembered in the current browser.

Existing media can be registered without creating scraping targets. Place `media_imports.json` next to `settings.json`:

```json
[
  {
    "platform": "rednote",
    "id": "stable-account-id",
    "name": "Account display name",
    "folder": "imports/rednote/stable-account-id"
  }
]
```

`folder` is relative to the configured download root. Absolute paths and paths outside that root are rejected. Each platform/ID pair must be unique. Names can be changed without changing the account identity. Use the original platform account ID when known; otherwise assign a stable local ID once and retain it.

After registering media, refresh the immersive index. Media remains in the supplied folder. This manifest does not copy files, import credentials, or enable collection for additional platforms. Back up the manifest before editing it; removing entries removes those accounts from the rebuilt browsing index, not their files.

Keep imported folders beneath a dedicated `imports/<platform>/` directory to avoid the collector's legacy account-folder matching. Keep backups and old settings/databases outside the media root. When consolidating old folders, verify filenames and retain a move journal; never overwrite an existing file merely because its name matches.
