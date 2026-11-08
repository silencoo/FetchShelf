# WebUI screenshots

These screenshots show the built FetchShelf WebUI with fictional accounts, tasks,
and statistics. Playwright intercepts browser requests and serves local fixtures;
the capture does not contact a production service or use login credentials.
The photos illustrate the interface and are not scraped Douyin or TikTok posts.

| Screenshot | Viewport |
| --- | --- |
| [Download workbench](workbench.jpg) | 1440 × 1000 |
| [Account board](account-board.jpg) | 1440 × 900 |
| [Desktop immersive viewer](immersive-desktop.jpg) | 1440 × 900 |
| [Mobile immersive viewer](immersive-mobile.jpg) | 390 × 844 |

The mobile screenshot uses Chromium's mobile viewport and touch emulation; it is
an interface preview, not an iOS Safari compatibility test.

## Photo credits

Photos are used under the [Unsplash License](https://unsplash.com/license).

| Local fixture filename | Photographer and source |
| --- | --- |
| `mountains.jpg` | [Hanna Lazar — Mountain lake with rocky slopes](https://unsplash.com/photos/mountain-lake-with-rocky-slopes-NKqZdTSlyEM) |
| `coffee.jpg` | [Jeffrey Wegrzyn — Cup of coffee](https://unsplash.com/photos/cup-of-coffee-hdnsLAU35kY) |
| `city.jpg` | [Adam Borkowski — City street at night](https://unsplash.com/photos/a-city-street-at-night-with-a-lot-of-traffic-UUxSdGZ4ii0) |
| `lake.jpg` | [Filippo Molinari — Mountain lake at dawn](https://unsplash.com/photos/tranquil-mountain-lake-at-dawn-with-distant-snow-capped-peaks-6tcvf72JOmg) |

## Reproduce

From the repository root, build the WebUI and install Playwright in a dedicated
Python environment:

```sh
npm --prefix webui ci
npm --prefix webui run build
python3 -m venv /tmp/fetchshelf-readme-venv
/tmp/fetchshelf-readme-venv/bin/pip install playwright
/tmp/fetchshelf-readme-venv/bin/playwright install chromium
```

Download the four credited photos into a directory using the filenames above,
then capture the screenshots (replace the media directory with your own):

```sh
/tmp/fetchshelf-readme-venv/bin/python scripts/capture_readme.py \
  --media-dir /tmp/fetchshelf-readme-media
```

The script writes the four JPEGs in this directory and fails on browser script
errors. Use `--chromium /path/to/chromium` to select an existing Chromium browser.
Only screenshots are committed; the original photo files remain outside the
repository.
