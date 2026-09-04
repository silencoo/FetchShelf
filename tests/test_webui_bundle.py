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
        'id="files-breadcrumb"',
        'id="files-home-btn"',
        'id="files-search-clear-btn"',
        'id="board-grid"',
        'id="monitor-list"',
        'id="schedule-list"',
        'id="task-queue-list"',
        'id="task-filter-group"',
        'id="task-search-input"',
        'id="task-raw-result"',
        'id="task-account-checkpoints"',
        'id="schedule-overlap-policy"',
        'id="schedule-identity-failure-action"',
        'id="schedule-identity-failure-threshold"',
        'id="workflow-detail-form"',
        'id="workbench-overview"',
        'id="workbench-task-center"',
        'id="workbench-automation"',
        'id="workbench-developer-tools"',
        'id="command-title"',
        'id="magic-grid-root"',
        'id="magic-metrics-root"',
        'id="theme-control-root"',
    )
    for hook in required_hooks:
        assert hook in index

    assert "/ui/static/app.js" not in index
    assert "/ui/static/styles.css" not in index


def test_task_account_rows_offer_safe_external_navigation():
    index = SOURCE_ROOT.joinpath("index.html").read_text(encoding="utf-8")
    script = SOURCE_ROOT.joinpath("src", "legacy", "app.js").read_text(
        encoding="utf-8",
    )
    styles = SOURCE_ROOT.joinpath("src", "styles.css").read_text(encoding="utf-8")

    assert "function safeExternalHttpUrl(value)" in script
    assert 'parsed.protocol === "http:" || parsed.protocol === "https:"' in script
    assert 'nameNode.target = "_blank"' in script
    assert 'nameNode.rel = "noopener noreferrer"' in script
    assert 'action.textContent = "无可用链接"' in script
    assert 'document.createTextNode("打开账号")' in script
    assert "refreshIcons(refs.taskAccountList)" in script
    assert ".task-account-open" in styles
    assert ".task-account-link:hover" in styles
    assert 'visibility: "私密 / 可见性"' in script
    assert 'private_followed_empty: "已关注的私密账号未返回作品"' in script
    assert 'attemptedIdentityIds.join(" → ")' in script
    assert "account.recovered_by_identity" in script
    assert ".task-account-diagnostic-grid" in styles
    assert 'id="task-account-archive-dialog"' in index
    assert 'id="task-account-select-page-btn"' in index
    assert 'id="task-account-clear-selection-btn"' in index
    assert 'id="task-account-open-selected-btn"' in index
    assert 'id="task-account-archive-selected-btn"' in index
    assert 'document.createTextNode("移出名单")' in script
    assert '"/ui/api/accounts/archive-batch"' in script
    assert '"/ui/api/accounts/archive"' in script
    assert "account.configured !== false" in script
    assert "taskAccountSelected: new Map()" in script
    assert "function selectVisibleTaskAccounts()" in script
    assert "function clearTaskAccountSelection()" in script
    assert "selectedTaskAccountItems().map((item) => item.url)" in script
    assert "closeTaskAccountArchiveDialog" in script
    assert ".task-account-bulk-toolbar" in styles
    assert ".task-account-select" in styles
    assert ".task-account-actions" in styles
    assert ".task-account-archive" in styles


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


def test_webui_source_exposes_tiktok_identity_modes_without_requiring_cookie():
    index = SOURCE_ROOT.joinpath("index.html").read_text(encoding="utf-8")
    script = SOURCE_ROOT.joinpath("src", "legacy", "app.js").read_text(
        encoding="utf-8",
    )

    for value in ("anonymous", "authenticated", "adult_authenticated"):
        assert f'<option value="{value}">' in index
    assert 'id="collector-identity-auth-mode"' in index
    assert "identity.route_configured" in script
    assert 'collectorCredentialChip("Cloak 会话", true)' in script
    assert 'refs.collectorIdentityConcurrency.disabled = isAnonymous' in script
    assert 'auth_mode: refs.collectorIdentityPlatform.value === "tiktok"' in script


def test_collector_assignments_are_lazy_paginated_and_searchable():
    index = SOURCE_ROOT.joinpath("index.html").read_text(encoding="utf-8")
    script = SOURCE_ROOT.joinpath("src", "legacy", "app.js").read_text(
        encoding="utf-8",
    )
    styles = SOURCE_ROOT.joinpath("src", "styles.css").read_text(encoding="utf-8")

    for hook in (
        'id="collector-binding-search"',
        'id="collector-binding-search-clear-btn"',
        'id="collector-binding-pager"',
        'id="collector-binding-page-size"',
        'id="collector-binding-page-input"',
        'id="collector-binding-page-jump-btn"',
    ):
        assert index.count(hook) == 1
    assert "new AbortController()" in script
    assert 'page_size: String(pagination.pageSize)' in script
    assert 'query.set("search", pagination.search)' in script
    assert 'if (nextTab === "collectors")' in script
    bootstrap = script[script.index("async function bootstrap()") :]
    assert 'if (state.activeTab === "collectors")' in bootstrap
    assert ".collector-binding-search" in styles
    assert ".collector-binding-pager" in styles


def test_webui_source_exposes_identity_login_browser_without_cookie_copying():
    index = SOURCE_ROOT.joinpath("index.html").read_text(encoding="utf-8")
    script = SOURCE_ROOT.joinpath("src", "legacy", "app.js").read_text(
        encoding="utf-8",
    )
    styles = SOURCE_ROOT.joinpath("src", "styles.css").read_text(encoding="utf-8")
    dockerfile = PROJECT_ROOT.joinpath("Dockerfile").read_text(encoding="utf-8")

    for hook in (
        'id="collector-login-browser-dialog"',
        'id="collector-login-browser-viewport"',
        'id="collector-login-browser-reconnect-btn"',
        'id="collector-login-browser-fullscreen-btn"',
        'id="collector-login-browser-stop-btn"',
        'id="collector-login-browser-save-btn"',
    ):
        assert index.count(hook) == 1
    assert "完成登录并保存" in index
    assert 'data-collector-action="login-browser"' in script
    assert 'await import("@novnc/novnc")' in script
    assert "viewer_protocol_prefix" in script
    assert "login_browser_active" in script
    assert ".collector-login-browser-viewport" in styles
    assert ".collector-login-browser-frame:fullscreen" in styles
    assert "x11vnc" in dockerfile
    assert "fonts-noto-cjk" in dockerfile


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
        "fetchshelf-mark-48.png",
        "fetchshelf-mark-96.png",
        "fetchshelf-favicon-32.png",
        "fetchshelf-touch-icon-180.png",
    ):
        assert asset_name in index
        assert SOURCE_ROOT.joinpath("src", "assets", "brand", asset_name).is_file()

    for retired_copy in (
        "OPERATIONS CONSOLE",
        "统一管理下载队列、账户更新与本地媒体。",
    ):
        assert retired_copy not in index

    assert 'commandTitle: document.getElementById("command-title")' in script
    assert "document.title = `${activeLabel} · FetchShelf`" in script
    assert 'class="topbar command-header"' not in index
    assert '<span class="nav-label">设置</span>' in index
    assert 'class="sidebar-runtime-status"' in index

    settings_panel = index[index.index('id="panel-control-settings"') :]
    assert settings_panel.index('id="theme-control-root"') < settings_panel.index(
        'id="settings-form"',
    )
    assert settings_panel.index('id="token-input"') < settings_panel.index(
        'id="settings-form"',
    )


def test_webui_source_persists_token_and_supports_authenticated_media():
    script = SOURCE_ROOT.joinpath("src", "legacy", "app.js").read_text(
        encoding="utf-8",
    )
    server = PROJECT_ROOT.joinpath(
        "src",
        "application",
        "main_server.py",
    ).read_text(encoding="utf-8")

    assert 'const TOKEN_STORAGE_KEY = "webui.api.token"' in script
    assert "localStorage.setItem(TOKEN_STORAGE_KEY, token)" in script
    assert "localStorage.removeItem(TOKEN_STORAGE_KEY)" in script
    assert "state.token = readStoredToken()" in script
    assert "await establishWebUiSession()" in script
    assert 'fetchJson("/ui/api/session"' in script

    assert 'WEBUI_SESSION_COOKIE = "fetchshelf_webui_session"' in server
    assert "request.cookies.get(WEBUI_SESSION_COOKIE)" in server
    assert "response.set_cookie(" in server
    assert "response.delete_cookie(" in server


def test_webui_source_keeps_file_browser_navigation_contract():
    index = SOURCE_ROOT.joinpath("index.html").read_text(encoding="utf-8")
    script = SOURCE_ROOT.joinpath("src", "legacy", "app.js").read_text(
        encoding="utf-8",
    )

    for hook in (
        'id="files-breadcrumb"',
        'id="files-home-btn"',
        'id="files-up-btn"',
        'id="files-search-clear-btn"',
        'id="file-account-tools"',
        'id="file-lightbox"',
        'id="file-lightbox-stage"',
        'id="file-lightbox-prev-btn"',
        'id="file-lightbox-next-btn"',
    ):
        assert index.count(hook) == 1

    assert 'id="file-preview"' not in index
    assert 'value="folder_updated_desc"' in index
    assert "配置文件顺序" in index
    assert "function renderFileBreadcrumb()" in script
    assert "function navigateToFilePath(" in script
    assert 'card.addEventListener("click"' in script
    assert "state.filePageSize" in script
    assert "file-masonry" in index
    assert 'if (event.key === "Enter")' in script
    assert "function formatFileSize(" in script
    assert "function formatFileDate(" in script
    assert "fileAccessUrl(entry.path)" in script
    assert "function updateFileMasonryLayout()" in script
    assert "function observeFileMasonryCards()" in script
    assert "function openFileLightbox(" in script
    assert "function moveFileLightbox(" in script
    assert "renderFilePreview" not in script
    assert 'video.addEventListener("loadedmetadata"' in script
    assert 'image.addEventListener("load"' in script


def test_account_board_cards_remain_usable_at_high_density():
    index = SOURCE_ROOT.joinpath("index.html").read_text(encoding="utf-8")
    script = SOURCE_ROOT.joinpath("src", "legacy", "app.js").read_text(
        encoding="utf-8",
    )
    styles = SOURCE_ROOT.joinpath("src", "styles.css").read_text(encoding="utf-8")

    assert "refs.boardGrid?.clientWidth" in script
    assert "const minimumCardWidth = compactMode ? 156 : 248" in script
    assert 'name.title = item.mark || item.url || "未设置 mark"' in script
    assert 'class="profile-actions-menu"' in script
    assert 'aria-label="更多账户操作"' in script
    assert 'data-action="board-open-gallery"' in script
    assert 'data-action="board-open-files"' in script
    assert "浏览原始目录" in script
    assert 'data-action="board-refresh-media"' in script
    assert 'data-action="board-generate-avatar"' in script
    assert 'event.key !== "Escape"' in script
    assert "function openAccountGallery(" in script
    assert "function loadAccountGallery(" in script
    assert 'fetchJson(`/ui/api/accounts/board/gallery?' in script
    assert "refs.accountGalleryDialog.showModal()" in script
    assert "account-gallery-media-frame-${item.kind}" in script

    for hook in (
        'id="account-gallery-dialog"',
        'id="account-gallery-stage"',
        'id="account-gallery-grid"',
        'id="account-gallery-kind"',
        'id="account-gallery-pin-btn"',
    ):
        assert index.count(hook) == 1

    assert "column-count: var(--board-columns);" in styles
    assert ".profile-board > .empty-tip {\n  column-span: all;" in styles
    assert (
        ".profile-card {\n"
        "  position: relative;\n"
        "  display: flex;\n"
        "  width: 100%;"
    ) in styles
    profile_card_styles = styles[
        styles.index(".profile-card {") : styles.index(".profile-card:hover")
    ]
    assert "break-inside: avoid;" in profile_card_styles
    assert "-webkit-line-clamp: 2;" in styles
    assert ".profile-state-row" in styles
    assert ".profile-actions-popover" in styles
    assert ".profile-latest-short" in styles
    assert ".account-gallery-layout" in styles
    assert ".account-gallery-thumb" in styles
    assert ".account-gallery-media-frame-video" in styles
    assert "aspect-ratio: var(--media-aspect, 9 / 16);" in styles
    assert "overflow-x: hidden;" in styles
    assert 'class="account-gallery-scroll"' in index
    assert ".account-gallery-scroll" in styles
    assert "column-count: 3;" in styles
    assert "break-inside: avoid;" in styles
    assert "column-span: all;" in styles
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in styles
    assert (
        ".account-gallery-thumb-media :is(img, video) {\n"
        "  width: 100%;\n"
        "  height: 100%;\n"
        "  object-fit: contain;"
    ) in styles
    assert "function syncNaturalMediaRatio(" in script
    assert 'container.style.setProperty("--media-aspect"' in script
    assert 'state.accountBoard.viewMode === "avatar" && hasMedia' in script
    assert '<option value="avatar">紧凑媒体</option>' in index
    assert ".profile-board.profile-board-compact .profile-media-wrap {\n  border-radius:" in styles
    assert "account-gallery-thumb-media-${item.kind}" in script
    assert ".account-gallery-thumb-media-image img {\n  width: 100%;\n  height: auto;" in styles
    assert ".profile-media-wrap-image img {\n  width: 100%;\n  height: auto;" in styles
    assert (
        ".account-gallery-media-frame :is(img, video) {\n"
        "  display: block;\n"
        "  width: auto;\n"
        "  max-width: 100%;\n"
        "  height: auto;\n"
        "  max-height: 100%;\n"
        "  object-fit: contain;"
    ) in styles
    assert 'id="account-gallery-kind" data-ui-select="false"' in index
    assert 'id="account-gallery-page-size" data-ui-select="false"' in index


def test_webui_websocket_uses_http_only_session_cookie_not_token_query():
    script = SOURCE_ROOT.joinpath("src", "legacy", "app.js").read_text(
        encoding="utf-8",
    )
    server = PROJECT_ROOT.joinpath("src", "application", "main_server.py").read_text(
        encoding="utf-8",
    )

    assert 'params.set("token"' not in script
    assert "websocket.cookies.get(WEBUI_SESSION_COOKIE)" in server
    assert 'websocket.query_params.get("token")' not in server


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


def test_webui_source_prioritizes_the_download_workflow():
    index = SOURCE_ROOT.joinpath("index.html").read_text(encoding="utf-8")
    script = SOURCE_ROOT.joinpath("src", "legacy", "app.js").read_text(
        encoding="utf-8",
    )

    overview = index.index('id="workbench-overview"')
    quick_download = index.index('id="workflow-detail-form"')
    task_center = index.index('id="workbench-task-center"')
    automation = index.index('id="workbench-automation"')
    developer_tools = index.index('id="workbench-developer-tools"')
    assert overview < quick_download < task_center < automation < developer_tools

    assert index.count('id="workflow-detail-count"') == 1
    assert '<option value="auto">自动识别</option>' in index
    assert 'id="workflow-detail-status"' in index
    assert 'role="status"' in index
    assert 'aria-live="polite"' in index

    for details_id in ("workbench-automation", "workbench-developer-tools"):
        opening_tag = index[index.index(f'<details id="{details_id}"') :]
        opening_tag = opening_tag[: opening_tag.index(">") + 1]
        assert " open" not in opening_tag
        assert "<summary>" in index[index.index(opening_tag) : index.index(opening_tag) + 300]

    for retired_copy in (
        "DOWNLOAD OPERATIONS",
        "DAILY AUTOMATION",
        "ACCOUNT BATCH",
        "LINK INGEST",
        "API LAB",
        "LINK RESOLVER",
    ):
        assert retired_copy not in index

    assert "function detectWorkflowLinkPlatform" in script
    assert 'state.activeTab === "workbench"' in script
    assert "!document.hidden" in script
    assert 'main.className = "task-main task-main-button"' in script
    assert 'taskEndpointLabel(task.endpoint)' in script
    assert 'status.className = `task-state-text ${taskStateClass(taskStatus)}`' in script
    assert "function renderFilteredTaskList()" in script
    assert 'data-task-filter="attention"' in index
    assert 'id="task-search-input"' in index
    assert 'id="task-raw-result"' in index
    assert 'refs.taskAccountCheckpoints.open = true' in script
    assert '.task-filter-btn[aria-pressed="true"]' in SOURCE_ROOT.joinpath(
        "src", "styles.css"
    ).read_text(encoding="utf-8")
    assert 'pausing: "暂停中"' in script
    assert 'paused: "已暂停"' in script
    assert "task.pause_supported" in script
    assert 'taskControl(task.task_id, "pause")' in script
    assert 'taskControl(task.task_id, "resume")' in script
    assert 'taskControl(task.task_id, "retry-failed")' in script
    assert "function loadTaskAccounts(" in script
    assert "function loadOverview(" in script
    assert 'fetchJson(`/ui/api/overview${query}`' in script
    assert 'loadOverview({ refreshMedia: true })' in script
    assert 'id="schedule-notify-identity-failure"' in index
    assert "等待完成后执行（推荐）" in index
    assert "未配置 Cookie 的普通账号不会因此暂停" in index
    assert "容器重启后记录会清空" not in index
    assert '["pending", "running", "pausing", "paused"].includes(taskStatus)' in script
    assert "const focusedTaskId =" in script
    assert "focusTarget?.focus({ preventScroll: true })" in script


def test_workbench_live_refresh_preserves_browsing_state():
    script = SOURCE_ROOT.joinpath("src", "legacy", "app.js").read_text(
        encoding="utf-8",
    )

    assert "const TASK_POLL_ACTIVE_MS = 2000" in script
    assert "const TASK_POLL_IDLE_MS = 15000" in script
    assert "function taskRenderKey(task)" in script
    assert "function taskListRenderKey(items)" in script
    assert "if (listChanged)" in script
    assert "taskRenderKey(selected) !== state.selectedTaskRenderKey" in script
    assert "taskChanged || taskFinishedWhileSelected" in script
    assert "const pollDue = Date.now() - state.taskLastPollAt >= pollInterval" in script


def test_webui_source_explains_bark_delivery_and_monitor_failures():
    index = SOURCE_ROOT.joinpath("index.html").read_text(encoding="utf-8")
    script = SOURCE_ROOT.joinpath("src", "legacy", "app.js").read_text(
        encoding="utf-8",
    )
    styles = SOURCE_ROOT.joinpath("src", "styles.css").read_text(encoding="utf-8")

    assert index.count('class="notification-panel"') == 2
    assert "每次下载任务结束都会发送结果" in index
    assert "抓取异常（包括 HTTP 403）会立即通知" in index
    assert 'aria-describedby="schedule-bark-help"' in index
    assert 'aria-describedby="monitor-bark-help"' in index

    assert "Bark：每次任务结束通知" in script
    assert "Bark：异常或发现新增账号时通知" in script
    assert 'statusLabel = "上次运行失败"' in script
    assert 'class="task-time task-result-error"' in script
    assert 'withBusyButton(event.currentTarget, "执行中"' in script

    assert ".notification-panel" in styles
    assert ".task-state-text.is-error" in styles
    assert ".task-result-error" in styles


def test_webui_source_keeps_compact_account_tables_and_collapsible_raw_editor():
    index = SOURCE_ROOT.joinpath("index.html").read_text(encoding="utf-8")
    script = SOURCE_ROOT.joinpath("src", "legacy", "app.js").read_text(
        encoding="utf-8",
    )
    styles = SOURCE_ROOT.joinpath("src", "styles.css").read_text(encoding="utf-8")

    assert 'id="settings-raw-disclosure"' in index
    assert '<summary class="raw-settings-summary">' in index
    assert 'id="settings-raw-fullscreen-btn"' not in index
    assert "toggleRawEditorFullscreen" not in script
    assert 'title="${escapeAttr(item.url)}"' in script

    assert ".raw-settings-disclosure" in styles
    assert ".account-table {\n  width: 100%;\n  min-width: 940px;" in styles
    assert (
        ".account-table:not(.deleted-table) :is(th, td):nth-child(5) {\n"
        "  width: 210px;"
    ) in styles
    assert "#settings-raw-editor {" in styles
    assert "resize: none !important;" in styles
