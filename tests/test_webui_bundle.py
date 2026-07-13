from pathlib import Path
from re import findall


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = PROJECT_ROOT.joinpath("src", "webui", "static")
SOURCE_ROOT = PROJECT_ROOT.joinpath("webui")


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
        'id="magic-grid-root"',
        'id="magic-metrics-root"',
    )
    for hook in required_hooks:
        assert hook in index

    assert "/ui/static/app.js" not in index
    assert "/ui/static/styles.css" not in index


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
