from pathlib import Path
from re import findall


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = PROJECT_ROOT.joinpath("src", "webui", "static")
SOURCE_ROOT = PROJECT_ROOT.joinpath("webui")


def _assert_prepaint_theme_bootstrap(index: str):
    storage_marker = index.index('"webui.theme"')
    script_start = index.rfind("<script", 0, storage_marker)
    script_tag_end = index.index(">", script_start)
    script_end = index.index("</script>", storage_marker)
    head_start = index.index("<head>")
    head_end = index.index("</head>")
    theme_color_meta = index.index('<meta name="theme-color"')

    assert head_start < theme_color_meta < script_start
    assert script_start < storage_marker < script_end < head_end
    assert index[script_start : script_tag_end + 1] == "<script>"

    render_blockers = [
        offset
        for marker in ('<script type="module"', '<link rel="stylesheet"')
        if (offset := index.find(marker)) != -1
    ]
    assert render_blockers
    assert script_end < min(render_blockers)

    bootstrap = index[script_start:script_end]
    assert 'new Set(["system", "light", "dark"])' in bootstrap
    assert 'window.matchMedia("(prefers-color-scheme: dark)")' in bootstrap
    assert "document.documentElement.dataset.theme = resolvedTheme" in bootstrap
    assert "document.documentElement.dataset.themePreference = preference" in bootstrap
    assert "document.documentElement.style.colorScheme = resolvedTheme" in bootstrap
    assert 'meta[name="theme-color"]' in bootstrap


def test_webui_production_bundle_references_existing_assets():
    index = STATIC_ROOT.joinpath("index.html").read_text(encoding="utf-8")
    asset_urls = findall(r'(?:src|href)="(/ui/static/[^"#?]+)', index)

    assert asset_urls
    for asset_url in asset_urls:
        relative_path = asset_url.removeprefix("/ui/static/")
        assert STATIC_ROOT.joinpath(relative_path).is_file(), asset_url

    entry_scripts = [
        STATIC_ROOT.joinpath(url.removeprefix("/ui/static/"))
        for url in asset_urls
        if url.endswith(".js")
    ]
    dynamic_chunks = set()
    for entry_script in entry_scripts:
        dynamic_chunks.update(
            findall(r'app-[A-Za-z0-9_-]+\.js', entry_script.read_text(encoding="utf-8")),
        )
    assert len(dynamic_chunks) == 1, dynamic_chunks

    legacy_chunk = STATIC_ROOT.joinpath("assets", dynamic_chunks.pop())
    assert legacy_chunk.is_file()
    assert "/ui/ws/logs" in legacy_chunk.read_text(encoding="utf-8")


def test_webui_bundle_keeps_core_interaction_hooks():
    index = STATIC_ROOT.joinpath("index.html").read_text(encoding="utf-8")

    required_hooks = (
        'id="token-input"',
        'id="settings-form"',
        'id="log-stream"',
        'id="files-list"',
        'id="board-grid"',
        'id="monitor-list"',
        'id="schedule-list"',
        'id="task-queue-list"',
        'id="command-title"',
        'id="magic-grid-root"',
        'id="magic-metrics-root"',
        'id="theme-control-root"',
    )
    for hook in required_hooks:
        assert hook in index

    assert "/ui/static/app.js" not in index
    assert "/ui/static/styles.css" not in index


def test_webui_source_keeps_complete_theme_contract():
    index = SOURCE_ROOT.joinpath("index.html").read_text(encoding="utf-8")
    script = SOURCE_ROOT.joinpath("src", "main.tsx").read_text(encoding="utf-8")
    styles = SOURCE_ROOT.joinpath("src", "styles.css").read_text(encoding="utf-8")

    _assert_prepaint_theme_bootstrap(index)
    assert index.count('id="theme-control-root"') == 1
    assert '<meta name="theme-color"' in index

    assert 'const THEME_STORAGE_KEY = "webui.theme"' in script
    for preference in ("system", "light", "dark"):
        assert f'value: "{preference}"' in script
    assert 'preference === "system"' in script
    assert 'systemPrefersDark ? "dark" : "light"' in script
    assert "window.localStorage.setItem(THEME_STORAGE_KEY, preference)" in script
    assert "root.dataset.theme = resolvedTheme" in script
    assert "root.dataset.themePreference = preference" in script
    assert "data-theme-option={value}" in script
    assert 'renderRoot("theme-control-root", <ThemeControl />)' in script

    assert ':root[data-theme="light"]' in styles
    assert "color-scheme: light" in styles


def test_webui_production_bundle_includes_theme_runtime_and_styles():
    index = STATIC_ROOT.joinpath("index.html").read_text(encoding="utf-8")
    scripts = "\n".join(
        path.read_text(encoding="utf-8")
        for path in STATIC_ROOT.joinpath("assets").glob("*.js")
    )
    styles = "\n".join(
        path.read_text(encoding="utf-8")
        for path in STATIC_ROOT.joinpath("assets").glob("*.css")
    )

    _assert_prepaint_theme_bootstrap(index)
    assert "webui.theme" in scripts
    assert "prefers-color-scheme: dark" in scripts
    assert "theme-control-root" in scripts
    assert all(preference in scripts for preference in ("system", "light", "dark"))
    assert ':root[data-theme="light"]' in styles or ":root[data-theme=light]" in styles
    assert "color-scheme:light" in styles


def test_webui_source_keeps_compact_brand_shell():
    index = SOURCE_ROOT.joinpath("index.html").read_text(encoding="utf-8")
    script = SOURCE_ROOT.joinpath("src", "legacy", "app.js").read_text(
        encoding="utf-8",
    )

    assert index.count('id="command-title"') == 1
    for asset_name in (
        "douk-mark-48.png",
        "douk-mark-96.png",
        "douk-favicon-32.png",
        "douk-touch-icon-180.png",
    ):
        assert asset_name in index
        assert SOURCE_ROOT.joinpath("src", "assets", "brand", asset_name).is_file()

    for retired_copy in (
        "DOUK CONTROL",
        "OPERATIONS CONSOLE",
        "NAS 运维控制台 · 下载、监控与媒体管理",
        "统一管理下载队列、账户更新与本地媒体。",
    ):
        assert retired_copy not in index

    assert 'commandTitle: document.getElementById("command-title")' in script
    assert "document.title = `${activeLabel} · DouK Downloader`" in script


def test_webui_source_contains_every_legacy_dom_reference_once():
    index = SOURCE_ROOT.joinpath("index.html").read_text(encoding="utf-8")
    script = SOURCE_ROOT.joinpath("src", "legacy", "app.js").read_text(
        encoding="utf-8",
    )
    element_ids = findall(r'id="([^"]+)"', index)
    referenced_ids = set(findall(r'getElementById\("([^"]+)"\)', script))

    assert len(element_ids) == len(set(element_ids)), "Duplicate element IDs"
    assert referenced_ids <= set(element_ids), sorted(referenced_ids - set(element_ids))

    tab_targets = set(findall(r'data-tab-target="([^"]+)"', index))
    panel_targets = set(findall(r'data-tab-panel="([^"]+)"', index))
    assert tab_targets == panel_targets
