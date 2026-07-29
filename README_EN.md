# FetchShelf

Docker-first Douyin / TikTok collection, download, and media management.

> [!IMPORTANT]
> Docker Compose and the WebUI are the primary deployment and maintenance targets.
> Desktop executables and the interactive terminal remain historical entry points
> and are not guaranteed to stay in feature parity.

## What it provides

- Douyin and TikTok account collection
- Multi-account batch and daily scheduled tasks
- Task progress, history, pause, resume, and stop controls
- Searchable and sortable account dashboard
- Paginated masonry media browser with image and video lightbox previews
- Settings, Cookie, collector identity, proxy, and routing management
- FastAPI documentation and endpoints

## Support status

| Interface | Status |
| --- | --- |
| Docker Compose | Primary |
| Local Docker build | Primary |
| WebUI | Primary |
| Web API | Maintained |
| Source terminal mode | Advanced / historical |
| Windows and macOS executables | Not a primary release target |

## Quick start

Requirements:

- Git
- Docker Engine or Docker Desktop
- Docker Compose v2

Clone the current repository:

```bash
git clone https://github.com/silencoo/FetchShelf.git
cd FetchShelf
cp .env.example .env
```

Generate two different random values:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
python -c "import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
```

Add them to `.env`:

```dotenv
TZ=Asia/Shanghai
WEBUI_PORT=5555
SETTINGS_DIR=./settings
DOWNLOADS_DIR=./downloads
FETCHSHELF_API_TOKEN=replace-with-the-first-value
FETCHSHELF_IDENTITY_KEY=replace-with-the-second-value
```

Build and start:

```bash
docker compose up -d --build
docker compose ps
```

Open `http://HOST_IP:5555/ui` and enter `FETCHSHELF_API_TOKEN`. In
Settings, set the download root to `/app/downloads`.

## Persistent data

| Host setting | Container path | Contents |
| --- | --- | --- |
| `SETTINGS_DIR` | `/app/settings` | Settings, databases, task state, cache, and account avatars |
| `DOWNLOADS_DIR` | `/app/downloads` | Downloaded images, videos, and exported data |
| `.env` | Environment variables | WebUI token, identity key, and mount paths |

Back up the two directories, `.env`, and especially
`FETCHSHELF_IDENTITY_KEY`. Changing or losing the identity key makes existing
encrypted Cookies, proxies, and device information unreadable. A Docker Secret
can be supplied through `FETCHSHELF_IDENTITY_KEY_FILE`; a key file takes
precedence over the environment variable.

Do not commit `.env`, Tokens, Cookies, or identity keys.

## Common operations

```bash
docker compose logs --tail=100
docker compose logs -f
docker compose stop
docker compose restart
docker compose up -d --build
```

## Updating and migrating

Before an update, stop active collection writes and back up `.env`,
`SETTINGS_DIR`, and `DOWNLOADS_DIR`.

```bash
git pull
docker compose build --pull
docker compose up -d
docker compose ps
docker compose logs --tail=100
```

When replacing an older container:

1. Record its environment variables and mounts.
2. Stop active collection and wait for current writes to finish.
3. Back up or snapshot the settings and downloads directories.
4. Point the new Compose configuration at the same persistent directories.
5. Stop the old container before starting FetchShelf.
6. Verify accounts, schedules, task history, media files, and latest-work times.

Never run two containers against the same writable settings and downloads
directories.

For upgrades from the pre-rename release:

- Move the old WebUI token and identity key values to
  `FETCHSHELF_API_TOKEN` and `FETCHSHELF_IDENTITY_KEY`; old variable names are
  not accepted.
- Keep the identity key value unchanged.
- The Compose service and container are both named `fetchshelf`.
- On first startup, the old application database is copied once to
  `FetchShelf.db`; the source database is not modified or deleted.

## Security notes

- Public-account collection often works without a Cookie.
- A logged-in Cookie can improve visibility for some content, but can also
  increase rate-limit or account-control risk.
- An empty `FETCHSHELF_API_TOKEN` only permits loopback requests; Docker and LAN
  requests normally receive `403`.
- Do not expose the WebUI directly to the public Internet. Use HTTPS, a reverse
  proxy, and additional access control when remote access is required.
- Only load a trusted external `encipher.py`; it runs with application
  permissions.

## API and development

After startup:

- WebUI: `http://HOST_IP:5555/ui`
- Swagger: `http://HOST_IP:5555/docs`
- ReDoc: `http://HOST_IP:5555/redoc`

Frontend development instructions are in
[webui/README.md](./webui/README.md). The Chinese
[README](./README.md) is the primary deployment guide.

## License and acknowledgement

This project is provided for lawful, authorized learning and research use.
Users are responsible for complying with local law, platform rules, privacy
requirements, and intellectual-property rights.

Distributed under the
[GNU General Public License v3.0](./license).

FetchShelf evolved from
[TikTokDownloader](https://github.com/JoeanAmier/TikTokDownloader). Thanks to
the original author and all open-source contributors.
