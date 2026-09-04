import { refs } from "./dom-refs.js";
import {
  fetchJson,
  headerOptions,
  setApiStatus,
  withBusyButton,
} from "./runtime.js";
import { state } from "./state.js";

export function createCollectorController({
  escapeHtml,
  parseBooleanValue,
  renderCollectMonitorList,
  renderScheduleList,
  syncAccountVerifyIdentityHelp,
  syncMonitorIdentityOverrides,
  syncScheduleIdentityOverrides,
  syncTaskIdentitySelector,
  syncWorkflowAccountIdentityOverrides,
  syncWorkflowDetailIdentitySelector,
}) {
  function collectorIdentityId(item) {
    return String(item?.identity_id ?? item?.id ?? "").trim();
  }

  function normalizeCollectorIdentity(item) {
    const identity = item && typeof item === "object" ? item : {};
    const platform = String(identity.platform || "douyin").toLowerCase() === "tiktok"
      ? "tiktok"
      : "douyin";
    const requestedAuthMode = String(identity.auth_mode || "authenticated").toLowerCase();
    const authMode = platform === "tiktok" && [
      "anonymous",
      "authenticated",
      "adult_authenticated",
    ].includes(requestedAuthMode)
      ? requestedAuthMode
      : "authenticated";
    const status = String(identity.status || identity.validation_status || "unknown").toLowerCase();
    const cookieConfigured = parseBooleanValue(identity.cookie_configured, false);
    return {
      identity_id: collectorIdentityId(identity),
      name: String(identity.name || identity.label || collectorIdentityId(identity) || "未命名身份"),
      platform,
      auth_mode: authMode,
      enabled: parseBooleanValue(identity.enabled, true),
      weight: Math.max(1, Number(identity.weight || 1)),
      request_delay: Math.max(0, Number(identity.request_delay ?? 6)),
      max_concurrency: Math.max(1, Number(identity.max_concurrency || 1)),
      status,
      credential_configured: parseBooleanValue(
        identity.credential_configured,
        parseBooleanValue(identity.cookie_configured, false),
      ),
      cookie_configured: cookieConfigured,
      proxy_configured: parseBooleanValue(identity.proxy_configured, false),
      user_agent_configured: parseBooleanValue(identity.user_agent_configured, false),
      device_id_configured: parseBooleanValue(identity.device_id_configured, false),
      login_browser_active: parseBooleanValue(identity.login_browser_active, false),
      route_configured: parseBooleanValue(
        identity.route_configured,
        authMode === "anonymous" || cookieConfigured,
      ),
      active_leases: Math.max(0, Number(identity.active_leases || 0)),
      cooldown_until: String(identity.cooldown_until || ""),
      last_validated_at: String(identity.last_validated_at || ""),
      // The public API exposes only a bounded error code. Never render an
      // arbitrary backend error string here because it may contain request or
      // credential material.
      last_error_code: String(identity.last_error_code || ""),
    };
  }

  function collectorItemsFromPayload(payload) {
    if (Array.isArray(payload)) {
      return payload;
    }
    if (Array.isArray(payload?.items)) {
      return payload.items;
    }
    if (Array.isArray(payload?.identities)) {
      return payload.identities;
    }
    if (Array.isArray(payload?.data?.items)) {
      return payload.data.items;
    }
    if (Array.isArray(payload?.data?.identities)) {
      return payload.data.identities;
    }
    return [];
  }

  function collectorPlatformLabel(platform) {
    return platform === "tiktok" ? "TikTok" : "抖音";
  }

  function collectorAuthModeLabel(authMode) {
    return {
      anonymous: "匿名",
      authenticated: "登录",
      adult_authenticated: "18+ 登录",
    }[authMode] || "登录";
  }

  function isFutureTimestamp(value) {
    if (!value) {
      return false;
    }
    const timestamp = Date.parse(value);
    return Number.isFinite(timestamp) && timestamp > Date.now();
  }

  function collectorIdentityState(identity) {
    if (identity.login_browser_active) {
      return "login";
    }
    if (!identity.enabled) {
      return "disabled";
    }
    if (isFutureTimestamp(identity.cooldown_until) || identity.status === "cooldown") {
      return "cooldown";
    }
    if (!identity.route_configured) {
      return "unconfigured";
    }
    if (["ready", "valid", "healthy", "available", "idle"].includes(identity.status)) {
      return "ready";
    }
    if (["invalid", "error", "failed", "blocked", "unavailable"].includes(identity.status)) {
      return "error";
    }
    return "unknown";
  }

  function collectorStateLabel(value) {
    return {
      ready: "可用",
      login: "登录中",
      disabled: "已停用",
      cooldown: "冷却中",
      unconfigured: "待配置",
      error: "异常",
      unknown: "待验证",
    }[value] || "待验证";
  }

  function collectorStateClass(value) {
    if (value === "ready") {
      return "success";
    }
    if (["error", "unconfigured"].includes(value)) {
      return "failed";
    }
    if (value === "disabled") {
      return "canceled";
    }
    return "pending";
  }

  function collectorTimeLabel(value) {
    if (!value) {
      return "—";
    }
    const timestamp = Date.parse(value);
    if (!Number.isFinite(timestamp)) {
      return value;
    }
    return new Intl.DateTimeFormat("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(timestamp));
  }

  function updateCollectorOverview() {
    const identities = state.collectorIdentities;
    const ready = identities.filter((item) => collectorIdentityState(item) === "ready").length;
    const attention = identities.filter((item) =>
      ["cooldown", "unconfigured", "error", "unknown", "login"].includes(
        collectorIdentityState(item),
      ),
    ).length;
    const leases = identities.reduce(
      (total, item) => total + Math.max(0, Number(item.active_leases || 0)),
      0,
    );
    refs.collectorTotalCount.textContent = String(identities.length);
    refs.collectorReadyCount.textContent = String(ready);
    refs.collectorAttentionCount.textContent = String(attention);
    refs.collectorLeaseCount.textContent = String(leases);
  }

  function filteredCollectorIdentities() {
    const platform = refs.collectorPlatformFilter.value;
    const status = refs.collectorStatusFilter.value;
    return state.collectorIdentities.filter((item) => {
      const identityState = collectorIdentityState(item);
      const platformMatches = platform === "all" || item.platform === platform;
      const statusMatches =
        status === "all" ||
        (status === "ready" && identityState === "ready") ||
        (status === "disabled" && identityState === "disabled") ||
        (status === "attention" &&
          ["cooldown", "unconfigured", "error", "unknown"].includes(identityState));
      return platformMatches && statusMatches;
    });
  }

  function collectorCredentialChip(label, configured) {
    return `<span class="collector-credential-chip ${configured ? "configured" : "missing"}">${
      configured ? "✓" : "—"
    } ${escapeHtml(label)}</span>`;
  }

  function renderCollectorIdentities() {
    const items = filteredCollectorIdentities();
    delete refs.collectorListStatus.dataset.state;
    refs.collectorIdentityList.innerHTML = "";
    refs.collectorIdentityList.setAttribute("aria-busy", "false");
    updateCollectorOverview();
    if (!state.collectorIdentities.length) {
      refs.collectorIdentityList.innerHTML = `
        <div class="empty-state collector-empty-state">
          <div>
            <strong>还没有采集身份</strong>
            <p>先创建抖音登录身份或 TikTok 匿名／登录身份，再配置自动路由。</p>
            <button type="button" class="btn primary" data-collector-action="create">创建第一个身份</button>
          </div>
        </div>
      `;
      refs.collectorListStatus.textContent = "暂无采集身份";
      return;
    }
    if (!items.length) {
      refs.collectorIdentityList.innerHTML = `
        <div class="empty-state collector-empty-state">
          <div>
            <strong>没有匹配的身份</strong>
            <p>调整平台或状态筛选，查看其他采集身份。</p>
            <button type="button" class="btn ghost" data-collector-action="clear-filter">清除筛选</button>
          </div>
        </div>
      `;
      refs.collectorListStatus.textContent = `已加载 ${state.collectorIdentities.length} 个身份，当前筛选无结果`;
      return;
    }
    const fragment = document.createDocumentFragment();
    items.forEach((identity) => {
      const visualState = collectorIdentityState(identity);
      const card = document.createElement("article");
      card.className = `collector-identity-card state-${visualState}`;
      card.dataset.identityId = identity.identity_id;
      const tiktokChips = identity.platform === "tiktok"
        ? `${collectorCredentialChip("Device ID", identity.device_id_configured)}${collectorCredentialChip(
            "User-Agent",
            identity.user_agent_configured,
          )}`
        : "";
      const loginBrowserChip = identity.login_browser_active
        ? collectorCredentialChip("登录浏览器运行中", true)
        : "";
      const loginBrowserAction = identity.auth_mode === "anonymous"
        ? ""
        : `<button type="button" class="btn ${
            identity.login_browser_active ? "primary" : "ghost"
          }" data-collector-action="login-browser">${
            identity.login_browser_active ? "继续登录" : "登录浏览器"
          }</button>`;
      const authModeBadge = identity.platform === "tiktok"
        ? `<span class="badge">${escapeHtml(collectorAuthModeLabel(identity.auth_mode))}</span>`
        : "";
      const issue = identity.last_error_code
        ? `<p class="collector-identity-error">最近异常：${escapeHtml(identity.last_error_code)}</p>`
        : "";
      const cooldown = isFutureTimestamp(identity.cooldown_until)
        ? `<span>冷却至 ${escapeHtml(collectorTimeLabel(identity.cooldown_until))}</span>`
        : "";
      card.innerHTML = `
        <div class="collector-identity-head">
          <div>
            <div class="collector-identity-badges">
              <span class="badge">${escapeHtml(collectorPlatformLabel(identity.platform))}</span>
              ${authModeBadge}
              <span class="task-status ${collectorStateClass(visualState)}">${escapeHtml(
                collectorStateLabel(visualState),
              )}</span>
            </div>
            <h4>${escapeHtml(identity.name)}</h4>
            <span class="collector-identity-id">${escapeHtml(identity.identity_id || "—")}</span>
          </div>
          <span class="collector-lease-badge" title="当前占用租约">${identity.active_leases} 占用</span>
        </div>
        <dl class="collector-identity-meta">
          <div><dt>权重</dt><dd>${identity.weight}</dd></div>
          <div><dt>请求间隔</dt><dd>${identity.request_delay}s</dd></div>
          <div><dt>最大并发</dt><dd>${identity.max_concurrency}</dd></div>
        </dl>
        <div class="collector-credential-list" aria-label="凭据配置状态">
          ${identity.auth_mode === "anonymous"
            ? collectorCredentialChip("Cloak 会话", true)
            : collectorCredentialChip("Cookie", identity.cookie_configured)}
          ${collectorCredentialChip("代理", identity.proxy_configured)}
          ${tiktokChips}
          ${loginBrowserChip}
        </div>
        <div class="collector-identity-timeline">
          <span>上次验证 ${escapeHtml(collectorTimeLabel(identity.last_validated_at))}</span>
          ${cooldown}
        </div>
        ${issue}
        <div class="collector-identity-actions">
          ${loginBrowserAction}
          <button type="button" class="btn ghost" data-collector-action="edit">编辑</button>
          <button type="button" class="btn ghost" data-collector-action="validate">验证</button>
          <button type="button" class="btn ghost" data-collector-action="proxy-test" ${
            identity.proxy_configured ? "" : "disabled"
          }>测代理</button>
          <button type="button" class="btn ghost" data-collector-action="toggle">${
            identity.enabled ? "停用" : "启用"
          }</button>
          <button type="button" class="btn ghost danger" data-collector-action="delete">删除</button>
        </div>
      `;
      fragment.appendChild(card);
    });
    refs.collectorIdentityList.appendChild(fragment);
    refs.collectorListStatus.textContent = `显示 ${items.length} / ${state.collectorIdentities.length} 个身份`;
  }

  function collectorOptionLabel(identity) {
    const authMode = identity.platform === "tiktok"
      ? ` · ${collectorAuthModeLabel(identity.auth_mode)}`
      : "";
    return `${identity.name}${authMode} · ${collectorStateLabel(collectorIdentityState(identity))}`;
  }

  function collectorIdentityIsRoutable(identity) {
    if (!identity?.enabled || !identity.route_configured || identity.login_browser_active) {
      return false;
    }
    if (isFutureTimestamp(identity.cooldown_until)) {
      return false;
    }
    return !["invalid", "disabled", "cooldown"].includes(String(identity.status || "").toLowerCase());
  }

  function collectorIdentityById(identityId) {
    return state.collectorIdentities.find((identity) => identity.identity_id === identityId) || null;
  }

  function populateCollectorIdentitySelect(select, platform, emptyLabel, options = {}) {
    if (!select) {
      return;
    }
    const {
      includeUnavailable = false,
      preserveUnavailable = false,
      selectedValue = select.value,
    } = options;
    const previousValue = String(selectedValue || "");
    select.innerHTML = "";
    delete select.dataset.unavailableSelection;
    const empty = document.createElement("option");
    empty.value = "";
    empty.textContent = emptyLabel;
    select.appendChild(empty);
    state.collectorIdentities
      .filter(
        (item) =>
          item.platform === platform && (includeUnavailable || collectorIdentityIsRoutable(item)),
      )
      .forEach((identity) => {
        const option = document.createElement("option");
        option.value = identity.identity_id;
        option.textContent = collectorOptionLabel(identity);
        select.appendChild(option);
      });
    const hasPrevious = Array.from(select.options).some((option) => option.value === previousValue);
    if (hasPrevious) {
      select.value = previousValue;
      return;
    }
    const unavailableIdentity = collectorIdentityById(previousValue);
    if (
      preserveUnavailable &&
      previousValue &&
      unavailableIdentity?.platform === platform
    ) {
      const unavailable = document.createElement("option");
      unavailable.value = previousValue;
      unavailable.textContent = `${unavailableIdentity.name} · 当前不可路由（仅供识别）`;
      unavailable.disabled = true;
      unavailable.selected = true;
      select.appendChild(unavailable);
      select.dataset.unavailableSelection = "true";
    }
  }

  function syncCollectorIdentitySelectors() {
    populateCollectorIdentitySelect(
      refs.accountsDouyinIdentity,
      "douyin",
      "自动路由",
      { preserveUnavailable: true },
    );
    populateCollectorIdentitySelect(
      refs.accountsTikTokIdentity,
      "tiktok",
      "自动路由",
      { preserveUnavailable: true },
    );
    populateCollectorIdentitySelect(
      refs.workflowAccountIdentity,
      refs.workflowAccountPlatform.value,
      "自动路由",
      { preserveUnavailable: true },
    );
    populateCollectorIdentitySelect(
      refs.scheduleIdentity,
      refs.schedulePlatform.value,
      "自动路由",
      { preserveUnavailable: true },
    );
    populateCollectorIdentitySelect(
      refs.collectorPolicyDefaultIdentity,
      refs.collectorPolicyPlatform.value,
      "自动选择",
      { includeUnavailable: true, preserveUnavailable: true },
    );
    populateCollectorIdentitySelect(
      refs.collectorAssignmentIdentity,
      refs.collectorAssignmentPlatform.value,
      "选择一个可路由身份",
      { preserveUnavailable: true },
    );
    syncWorkflowDetailIdentitySelector();
    populateCollectorIdentitySelect(
      refs.monitorIdentity,
      "douyin",
      "自动路由",
      { preserveUnavailable: true },
    );
    syncTaskIdentitySelector();
    syncAccountVerifyIdentityHelp("douyin");
    syncAccountVerifyIdentityHelp("tiktok");
    syncWorkflowAccountIdentityOverrides();
    syncScheduleIdentityOverrides();
    syncMonitorIdentityOverrides();
  }

  async function loadCollectorIdentities() {
    if (state.collectorListLoading) {
      return;
    }
    state.collectorListLoading = true;
    refs.collectorIdentityList.setAttribute("aria-busy", "true");
    refs.collectorListStatus.textContent = "正在加载采集身份…";
    if (!state.collectorIdentities.length) {
      refs.collectorIdentityList.innerHTML = '<div class="loading-state">正在读取身份状态…</div>';
    }
    try {
      const payload = await fetchJson("/ui/api/collector-identities", {
        method: "GET",
        headers: headerOptions(false),
      });
      state.collectorIdentities = collectorItemsFromPayload(payload)
        .map(normalizeCollectorIdentity)
        .filter((item) => item.identity_id);
      renderCollectorIdentities();
      syncCollectorIdentitySelectors();
      if (state.collectorAssignmentsLoaded[refs.collectorAssignmentPlatform.value]) {
        renderCollectorAssignments(refs.collectorAssignmentPlatform.value);
      }
      if (Array.isArray(state.settingsData.ui_schedules)) {
        renderScheduleList(state.settingsData.ui_schedules);
      }
      if (Array.isArray(state.collectMonitorItems)) {
        renderCollectMonitorList(state.collectMonitorItems);
      }
      setApiStatus("就绪", "ok");
    } catch (error) {
      refs.collectorIdentityList.setAttribute("aria-busy", "false");
      refs.collectorIdentityList.innerHTML = `
        <div class="error-state collector-error-state">
          <div>
            <strong>采集身份加载失败</strong>
            <p>${escapeHtml(error.message)}</p>
            <button type="button" class="btn ghost" data-collector-action="retry">重试</button>
          </div>
        </div>
      `;
      refs.collectorListStatus.textContent = `加载失败：${error.message}`;
      refs.collectorListStatus.dataset.state = "error";
      setApiStatus(`异常: ${error.message}`, "error");
    } finally {
      state.collectorListLoading = false;
    }
  }

  function setCollectorStatus(element, message, stateValue = "") {
    if (!element) {
      return;
    }
    element.textContent = message;
    if (stateValue) {
      element.dataset.state = stateValue;
    } else {
      delete element.dataset.state;
    }
  }

  function syncCollectorCredentialFields() {
    const isTikTok = refs.collectorIdentityPlatform.value === "tiktok";
    const authMode = isTikTok ? refs.collectorIdentityAuthMode.value : "authenticated";
    const isAnonymous = authMode === "anonymous";
    refs.collectorTikTokAuthFields.hidden = !isTikTok;
    refs.collectorIdentityAuthMode.disabled = !isTikTok;
    refs.collectorTikTokCredentialFields.hidden = !isTikTok;
    refs.collectorIdentityDeviceId.disabled = !isTikTok;
    refs.collectorIdentityUserAgent.disabled = !isTikTok;
    refs.collectorIdentityCookie.disabled = isAnonymous;
    refs.collectorIdentityCookieLabel.textContent = isAnonymous
      ? "完整 Cookie（匿名模式不使用）"
      : "完整 Cookie（手动备用）";
    refs.collectorIdentityCookieHelp.textContent = isAnonymous
      ? "匿名身份会忽略已保存的登录 Cookie，由独立 Cloak profile 自动建立和复用会话。"
      : authMode === "adult_authenticated"
        ? "请使用已经完成年龄确认且可访问 18+ 内容的 TikTok Web Cookie。"
        : "保存身份后可从身份卡片打开登录浏览器；也可以在这里手动粘贴 Cookie。";
    refs.collectorIdentityAuthModeHelp.textContent = isAnonymous
      ? "匿名身份无需 Cookie；临时会话不写入凭据库，每个身份使用独立 Cloak profile。"
      : authMode === "adult_authenticated"
        ? "用于可能存在年龄门槛的公开内容；平台实际权限仍以该账号状态和地区为准。"
        : "普通登录身份可补充匿名访客不可见的公开内容，但不绕过作品隐私设置。";
    if (isAnonymous) {
      refs.collectorIdentityConcurrency.value = "1";
    }
    refs.collectorIdentityConcurrency.disabled = isAnonymous;
  }

  function clearCollectorCredentialInputs() {
    refs.collectorIdentityCookie.value = "";
    refs.collectorIdentityProxy.value = "";
    refs.collectorIdentityDeviceId.value = "";
    refs.collectorIdentityUserAgent.value = "";
  }

  function openCollectorIdentityDialog(identityId = "", trigger = document.activeElement) {
    const identity = state.collectorIdentities.find((item) => item.identity_id === identityId);
    refs.collectorIdentityForm.reset();
    clearCollectorCredentialInputs();
    refs.collectorIdentityId.value = identity?.identity_id || "";
    refs.collectorIdentityName.value = identity?.name || "";
    refs.collectorIdentityPlatform.value = identity?.platform || "douyin";
    refs.collectorIdentityAuthMode.value = identity?.auth_mode || "anonymous";
    refs.collectorIdentityPlatform.disabled = Boolean(identity);
    refs.collectorIdentityWeight.value = String(identity?.weight || 1);
    refs.collectorIdentityDelay.value = String(identity?.request_delay ?? 6);
    refs.collectorIdentityConcurrency.value = String(identity?.max_concurrency || 1);
    refs.collectorIdentityEnabled.checked = identity ? identity.enabled : true;
    refs.collectorDialogTitle.textContent = identity ? "编辑采集身份" : "创建采集身份";
    refs.collectorDialogDescription.textContent = identity
      ? "修改调度参数；敏感凭据留空时保持现有值不变。"
      : "先创建身份元数据，再按需写入登录与网络凭据。";
    refs.collectorDialogSaveBtn.textContent = identity ? "保存修改" : "创建身份";
    setCollectorStatus(refs.collectorDialogStatus, "");
    syncCollectorCredentialFields();
    state.collectorDialogRestoreFocus = trigger instanceof HTMLElement ? trigger : null;
    if (!refs.collectorIdentityDialog.open) {
      refs.collectorIdentityDialog.showModal();
    }
    window.setTimeout(() => refs.collectorIdentityName.focus(), 0);
  }

  function closeCollectorIdentityDialog(identityId = "") {
    clearCollectorCredentialInputs();
    if (refs.collectorIdentityDialog.open) {
      refs.collectorIdentityDialog.close();
    }
    let restoreTarget = state.collectorDialogRestoreFocus;
    state.collectorDialogRestoreFocus = null;
    if (!restoreTarget?.isConnected && identityId) {
      const refreshedCard = Array.from(
        refs.collectorIdentityList.querySelectorAll("[data-identity-id]"),
      ).find((card) => card.dataset.identityId === identityId);
      restoreTarget = refreshedCard?.querySelector('[data-collector-action="edit"]') || null;
    }
    if (!restoreTarget?.isConnected) {
      restoreTarget = refs.collectorCreateBtn?.isConnected ? refs.collectorCreateBtn : null;
    }
    if (restoreTarget) {
      window.setTimeout(() => restoreTarget.focus(), 0);
    }
  }

  function collectorLoginBrowserBaseUrl(identityId, sessionId = "") {
    const base = `/ui/api/collector-identities/${encodeURIComponent(identityId)}/login-browser`;
    return sessionId ? `${base}/${encodeURIComponent(sessionId)}` : base;
  }

  function setCollectorLoginBrowserOverlay(message, detail = "", stateValue = "loading") {
    const overlay = refs.collectorLoginBrowserOverlay;
    if (!overlay) {
      return;
    }
    overlay.hidden = !message;
    overlay.dataset.state = stateValue;
    const title = overlay.querySelector("strong");
    const description = overlay.querySelector("strong + span");
    if (title) {
      title.textContent = message;
    }
    if (description) {
      description.textContent = detail;
    }
  }

  function clearCollectorLoginBrowserCountdown() {
    if (state.collectorLoginBrowser.countdownTimer) {
      window.clearInterval(state.collectorLoginBrowser.countdownTimer);
      state.collectorLoginBrowser.countdownTimer = null;
    }
  }

  function updateCollectorLoginBrowserCountdown() {
    const expiresAt = Date.parse(state.collectorLoginBrowser.expiresAt || "");
    if (!Number.isFinite(expiresAt)) {
      refs.collectorLoginBrowserExpiry.textContent = "20 分钟后自动停止";
      return;
    }
    const remaining = Math.max(0, Math.ceil((expiresAt - Date.now()) / 1000));
    const minutes = Math.floor(remaining / 60);
    const seconds = remaining % 60;
    refs.collectorLoginBrowserExpiry.textContent = remaining
      ? `剩余 ${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`
      : "会话已到期";
    if (!remaining) {
      clearCollectorLoginBrowserCountdown();
      disconnectCollectorLoginBrowserViewer();
      refs.collectorLoginBrowserSaveBtn.disabled = true;
      refs.collectorLoginBrowserReconnectBtn.hidden = true;
      setCollectorLoginBrowserOverlay(
        "登录会话已到期",
        "返回身份卡片可以重新启动登录浏览器。",
        "error",
      );
      setCollectorStatus(
        refs.collectorLoginBrowserStatus,
        "会话已自动回收，尚未保存新的 Cookie",
        "error",
      );
    }
  }

  function startCollectorLoginBrowserCountdown() {
    clearCollectorLoginBrowserCountdown();
    updateCollectorLoginBrowserCountdown();
    state.collectorLoginBrowser.countdownTimer = window.setInterval(
      updateCollectorLoginBrowserCountdown,
      1000,
    );
  }

  function disconnectCollectorLoginBrowserViewer() {
    const rfb = state.collectorLoginBrowser.rfb;
    state.collectorLoginBrowser.rfb = null;
    state.collectorLoginBrowser.connecting = false;
    if (rfb) {
      try {
        rfb.disconnect();
      } catch (error) {
        console.debug("[collector-login-browser] viewer cleanup failed", error);
      }
    }
    refs.collectorLoginBrowserViewport.replaceChildren();
  }

  async function connectCollectorLoginBrowserViewer(viewerTicket, protocolPrefix) {
    if (!viewerTicket || !state.collectorLoginBrowser.sessionId) {
      throw new Error("服务端未返回浏览器查看凭证");
    }
    disconnectCollectorLoginBrowserViewer();
    state.collectorLoginBrowser.connecting = true;
    refs.collectorLoginBrowserReconnectBtn.hidden = true;
    refs.collectorLoginBrowserSaveBtn.disabled = false;
    setCollectorLoginBrowserOverlay(
      "正在连接身份浏览器…",
      "浏览器画面将在连接完成后显示",
    );
    setCollectorStatus(refs.collectorLoginBrowserStatus, "正在建立安全查看通道…");

    const { default: RFB } = await import("@novnc/novnc");
    const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
    const identityId = encodeURIComponent(state.collectorLoginBrowser.identityId);
    const sessionId = encodeURIComponent(state.collectorLoginBrowser.sessionId);
    const wsUrl = `${scheme}//${window.location.host}/ui/ws/collector-identities/${identityId}/login-browser/${sessionId}`;
    const rfb = new RFB(refs.collectorLoginBrowserViewport, wsUrl, {
      wsProtocols: ["binary", `${protocolPrefix}${viewerTicket}`],
    });
    state.collectorLoginBrowser.rfb = rfb;
    rfb.scaleViewport = true;
    rfb.resizeSession = false;
    rfb.clipViewport = false;
    rfb.showDotCursor = true;
    rfb.viewOnly = false;

    rfb.addEventListener("connect", () => {
      if (state.collectorLoginBrowser.rfb !== rfb) {
        return;
      }
      state.collectorLoginBrowser.connecting = false;
      setCollectorLoginBrowserOverlay("");
      setCollectorStatus(
        refs.collectorLoginBrowserStatus,
        "浏览器已连接，请在画面中完成平台登录",
        "success",
      );
      refs.collectorLoginBrowserViewport.focus();
    });
    rfb.addEventListener("disconnect", (event) => {
      if (state.collectorLoginBrowser.rfb !== rfb) {
        return;
      }
      state.collectorLoginBrowser.rfb = null;
      state.collectorLoginBrowser.connecting = false;
      refs.collectorLoginBrowserReconnectBtn.hidden = false;
      setCollectorLoginBrowserOverlay(
        "浏览器画面已断开",
        event.detail?.clean ? "可以重新连接继续操作。" : "连接异常，可以尝试重新连接。",
        event.detail?.clean ? "idle" : "error",
      );
      setCollectorStatus(
        refs.collectorLoginBrowserStatus,
        event.detail?.clean ? "查看通道已断开" : "浏览器连接异常",
        event.detail?.clean ? "" : "error",
      );
    });
    rfb.addEventListener("securityfailure", (event) => {
      if (state.collectorLoginBrowser.rfb !== rfb) {
        return;
      }
      setCollectorLoginBrowserOverlay(
        "无法验证浏览器查看通道",
        String(event.detail?.reason || "请刷新查看凭证后重试。"),
        "error",
      );
    });
  }

  async function requestCollectorLoginBrowserTicket() {
    const { identityId, sessionId } = state.collectorLoginBrowser;
    if (!identityId || !sessionId) {
      throw new Error("登录浏览器会话不存在");
    }
    return fetchJson(
      `${collectorLoginBrowserBaseUrl(identityId, sessionId)}/viewer-ticket`,
      {
        method: "POST",
        headers: headerOptions(false),
      },
    );
  }

  async function reconnectCollectorLoginBrowser() {
    setCollectorLoginBrowserOverlay("正在重新连接…", "正在申请新的临时查看凭证");
    try {
      const payload = await requestCollectorLoginBrowserTicket();
      await connectCollectorLoginBrowserViewer(
        payload.viewer_ticket,
        payload.viewer_protocol_prefix || "fetchshelf-login.",
      );
    } catch (error) {
      refs.collectorLoginBrowserReconnectBtn.hidden = false;
      setCollectorLoginBrowserOverlay(
        "重新连接失败",
        error.message,
        "error",
      );
      setCollectorStatus(
        refs.collectorLoginBrowserStatus,
        `重新连接失败：${error.message}`,
        "error",
      );
    }
  }

  async function openCollectorLoginBrowser(identity, trigger = document.activeElement) {
    if (!identity || identity.auth_mode === "anonymous") {
      setCollectorStatus(
        refs.collectorListStatus,
        "匿名身份会自动维护 Cloak 会话，不需要登录浏览器",
        "error",
      );
      return;
    }
    state.collectorLoginBrowser.restoreFocus = trigger instanceof HTMLElement ? trigger : null;
    state.collectorLoginBrowser.identityId = identity.identity_id;
    state.collectorLoginBrowser.sessionId = "";
    state.collectorLoginBrowser.expiresAt = "";
    refs.collectorLoginBrowserTitle.textContent = "身份登录浏览器";
    refs.collectorLoginBrowserIdentity.textContent = `${identity.name} · ${collectorPlatformLabel(
      identity.platform,
    )}`;
    refs.collectorLoginBrowserExpiry.textContent = "会话准备中";
    refs.collectorLoginBrowserSaveBtn.disabled = true;
    refs.collectorLoginBrowserReconnectBtn.hidden = true;
    setCollectorStatus(refs.collectorLoginBrowserStatus, "正在启动隔离浏览器…");
    setCollectorLoginBrowserOverlay(
      "正在启动隔离浏览器…",
      identity.proxy_configured ? "将使用该采集身份配置的代理" : "该身份未配置代理",
    );
    if (!refs.collectorLoginBrowserDialog.open) {
      refs.collectorLoginBrowserDialog.showModal();
    }
    try {
      const payload = await fetchJson(
        collectorLoginBrowserBaseUrl(identity.identity_id),
        {
          method: "POST",
          headers: headerOptions(false),
        },
      );
      const session = payload.session || {};
      if (!session.session_id) {
        throw new Error("服务端未返回登录浏览器会话");
      }
      state.collectorLoginBrowser.sessionId = session.session_id;
      state.collectorLoginBrowser.expiresAt = session.expires_at || "";
      startCollectorLoginBrowserCountdown();
      if (session.startup_warning) {
        setCollectorStatus(
          refs.collectorLoginBrowserStatus,
          session.startup_warning,
          "error",
        );
      }
      await connectCollectorLoginBrowserViewer(
        payload.viewer_ticket,
        payload.viewer_protocol_prefix || "fetchshelf-login.",
      );
      await loadCollectorIdentities({ silent: true });
    } catch (error) {
      refs.collectorLoginBrowserSaveBtn.disabled = true;
      refs.collectorLoginBrowserReconnectBtn.hidden = true;
      setCollectorLoginBrowserOverlay(
        "身份浏览器启动失败",
        error.message,
        "error",
      );
      setCollectorStatus(
        refs.collectorLoginBrowserStatus,
        `启动失败：${error.message}`,
        "error",
      );
    }
  }

  function closeCollectorLoginBrowserDialog() {
    clearCollectorLoginBrowserCountdown();
    disconnectCollectorLoginBrowserViewer();
    if (refs.collectorLoginBrowserDialog.open) {
      refs.collectorLoginBrowserDialog.close();
    }
    const restoreTarget = state.collectorLoginBrowser.restoreFocus;
    state.collectorLoginBrowser.identityId = "";
    state.collectorLoginBrowser.sessionId = "";
    state.collectorLoginBrowser.expiresAt = "";
    state.collectorLoginBrowser.restoreFocus = null;
    if (restoreTarget?.isConnected) {
      window.setTimeout(() => restoreTarget.focus(), 0);
    } else if (refs.collectorCreateBtn?.isConnected) {
      window.setTimeout(() => refs.collectorCreateBtn.focus(), 0);
    }
  }

  async function stopCollectorLoginBrowser() {
    const { identityId, sessionId } = state.collectorLoginBrowser;
    if (!identityId || !sessionId) {
      closeCollectorLoginBrowserDialog();
      return;
    }
    setCollectorStatus(refs.collectorLoginBrowserStatus, "正在停止身份浏览器…");
    try {
      await fetchJson(collectorLoginBrowserBaseUrl(identityId, sessionId), {
        method: "DELETE",
        headers: headerOptions(false),
      });
      closeCollectorLoginBrowserDialog();
      await loadCollectorIdentities();
      setCollectorStatus(refs.collectorListStatus, "身份登录浏览器已停止", "success");
    } catch (error) {
      setCollectorStatus(
        refs.collectorLoginBrowserStatus,
        `停止失败：${error.message}`,
        "error",
      );
    }
  }

  async function captureCollectorLoginBrowserCredentials() {
    const { identityId, sessionId } = state.collectorLoginBrowser;
    if (!identityId || !sessionId) {
      setCollectorStatus(refs.collectorLoginBrowserStatus, "登录浏览器会话不存在", "error");
      return;
    }
    setCollectorStatus(refs.collectorLoginBrowserStatus, "正在检测登录状态并加密保存 Cookie…");
    try {
      const payload = await fetchJson(
        `${collectorLoginBrowserBaseUrl(identityId, sessionId)}/capture`,
        {
          method: "POST",
          headers: headerOptions(false),
        },
      );
      const cookieCount = Math.max(0, Number(payload.cookie_count || 0));
      closeCollectorLoginBrowserDialog();
      await loadCollectorIdentities();
      setCollectorStatus(
        refs.collectorListStatus,
        `${payload.message || "登录 Cookie 已保存"}（${cookieCount} 项）`,
        "success",
      );
      setApiStatus("身份登录凭据已更新", "ok");
    } catch (error) {
      setCollectorStatus(
        refs.collectorLoginBrowserStatus,
        `尚未保存：${error.message}`,
        "error",
      );
      setCollectorLoginBrowserOverlay(
        "还没有检测到完整登录状态",
        "请继续完成登录，然后再次点击“完成登录并保存”。",
        "error",
      );
      window.setTimeout(() => setCollectorLoginBrowserOverlay(""), 2600);
    }
  }

  async function toggleCollectorLoginBrowserFullscreen() {
    const frame = refs.collectorLoginBrowserViewport.closest(".collector-login-browser-frame");
    if (!frame) {
      return;
    }
    try {
      if (document.fullscreenElement === frame) {
        await document.exitFullscreen();
      } else {
        await frame.requestFullscreen();
      }
    } catch (error) {
      setCollectorStatus(
        refs.collectorLoginBrowserStatus,
        `无法切换全屏：${error.message}`,
        "error",
      );
    }
  }

  function collectorIdentityFromPayload(payload) {
    const candidate =
      payload?.identity || payload?.item || payload?.data?.identity || payload?.data?.item || payload?.data || payload;
    if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)) {
      return null;
    }
    const normalized = normalizeCollectorIdentity(candidate);
    return normalized.identity_id ? normalized : null;
  }

  function collectorMetadataFromForm() {
    if (!refs.collectorIdentityForm.checkValidity()) {
      refs.collectorIdentityForm.reportValidity();
      return null;
    }
    const name = refs.collectorIdentityName.value.trim();
    if (!name) {
      refs.collectorIdentityName.setCustomValidity("请输入身份名称");
      refs.collectorIdentityName.reportValidity();
      refs.collectorIdentityName.setCustomValidity("");
      return null;
    }
    return {
      name,
      platform: refs.collectorIdentityPlatform.value,
      auth_mode: refs.collectorIdentityPlatform.value === "tiktok"
        ? refs.collectorIdentityAuthMode.value
        : "authenticated",
      enabled: refs.collectorIdentityEnabled.checked,
      weight: Math.max(1, Number(refs.collectorIdentityWeight.value || 1)),
      request_delay: Math.max(0, Number(refs.collectorIdentityDelay.value || 0)),
      max_concurrency: Math.max(1, Number(refs.collectorIdentityConcurrency.value || 1)),
    };
  }

  function collectorCredentialsFromForm() {
    const credentials = {};
    const cookie = refs.collectorIdentityCookie.value.trim();
    const proxy = refs.collectorIdentityProxy.value.trim();
    const deviceId = refs.collectorIdentityDeviceId.value.trim();
    const userAgent = refs.collectorIdentityUserAgent.value.trim();
    if (cookie) {
      credentials.cookie = cookie;
    }
    if (proxy) {
      credentials.proxy = proxy;
    }
    if (refs.collectorIdentityPlatform.value === "tiktok") {
      if (deviceId) {
        credentials.device_id = deviceId;
      }
      if (userAgent) {
        credentials.user_agent = userAgent;
      }
    }
    return credentials;
  }

  async function saveCollectorIdentity() {
    const metadata = collectorMetadataFromForm();
    if (!metadata) {
      return;
    }
    const credentials = collectorCredentialsFromForm();
    const currentId = refs.collectorIdentityId.value.trim();
    setCollectorStatus(refs.collectorDialogStatus, currentId ? "正在保存身份修改…" : "正在创建身份…");
    try {
      const payload = await fetchJson(
        currentId
          ? `/ui/api/collector-identities/${encodeURIComponent(currentId)}`
          : "/ui/api/collector-identities",
        {
          method: currentId ? "PATCH" : "POST",
          headers: headerOptions(true),
          body: JSON.stringify(metadata),
        },
      );
      const savedIdentity = collectorIdentityFromPayload(payload);
      const identityId = currentId || savedIdentity?.identity_id;
      if (!identityId) {
        throw new Error("服务端未返回新身份 ID，无法继续写入凭据");
      }
      if (!currentId) {
        refs.collectorIdentityId.value = identityId;
        refs.collectorIdentityPlatform.disabled = true;
        refs.collectorDialogTitle.textContent = "编辑采集身份";
        refs.collectorDialogSaveBtn.textContent = "保存修改";
      }
      if (Object.keys(credentials).length) {
        setCollectorStatus(refs.collectorDialogStatus, "身份已保存，正在安全写入凭据…");
        try {
          await fetchJson(
            `/ui/api/collector-identities/${encodeURIComponent(identityId)}/credentials`,
            {
              method: "PUT",
              headers: headerOptions(true),
              body: JSON.stringify(credentials),
            },
          );
        } catch {
          throw new Error("身份已创建，但凭据写入失败；请检查 Cookie、代理和浏览器参数后重试");
        }
        clearCollectorCredentialInputs();
      }
      setCollectorStatus(refs.collectorDialogStatus, "保存成功", "success");
      await loadCollectorIdentities();
      closeCollectorIdentityDialog(identityId);
      setCollectorStatus(refs.collectorListStatus, currentId ? "身份修改已保存" : "采集身份创建成功", "success");
    } catch (error) {
      setCollectorStatus(refs.collectorDialogStatus, `保存失败：${error.message}`, "error");
      setApiStatus(`异常: ${error.message}`, "error");
    }
  }

  async function patchCollectorIdentity(identityId, patch) {
    await fetchJson(`/ui/api/collector-identities/${encodeURIComponent(identityId)}`, {
      method: "PATCH",
      headers: headerOptions(true),
      body: JSON.stringify(patch),
    });
  }

  async function runCollectorIdentityAction(action, identityId, button) {
    const identity = state.collectorIdentities.find((item) => item.identity_id === identityId);
    if (!identity) {
      return;
    }
    if (action === "edit") {
      openCollectorIdentityDialog(identityId, button);
      return;
    }
    if (action === "login-browser") {
      await openCollectorLoginBrowser(identity, button);
      return;
    }
    if (action === "delete") {
      const confirmed = window.confirm(`确认删除采集身份“${identity.name}”？已有目标绑定可能会回退或暂停。`);
      if (!confirmed) {
        return;
      }
    }
    const busyLabels = {
      validate: "验证中",
      "proxy-test": "测试中",
      toggle: identity.enabled ? "停用中" : "启用中",
      delete: "删除中",
    };
    await withBusyButton(button, busyLabels[action] || "处理中", async () => {
      setCollectorStatus(refs.collectorListStatus, `正在处理：${identity.name}`);
      try {
        let successMessage = "操作已完成";
        let successState = "success";
        if (action === "validate" || action === "proxy-test") {
          const endpoint = action === "validate" ? "validate" : "proxy-test";
          const result = await fetchJson(
            `/ui/api/collector-identities/${encodeURIComponent(identityId)}/${endpoint}`,
            {
              method: "POST",
              headers: headerOptions(true),
              body: JSON.stringify({}),
            },
          );
          successMessage = result?.message || `${action === "validate" ? "身份验证" : "代理测试"}已完成`;
          successState = parseBooleanValue(result?.ok ?? result?.success, true) ? "success" : "error";
        } else if (action === "toggle") {
          await patchCollectorIdentity(identityId, { enabled: !identity.enabled });
          successMessage = identity.enabled ? "身份已停用" : "身份已启用";
        } else if (action === "delete") {
          await fetchJson(`/ui/api/collector-identities/${encodeURIComponent(identityId)}`, {
            method: "DELETE",
            headers: headerOptions(false),
          });
          successMessage = "身份已删除";
        }
        await loadCollectorIdentities();
        setCollectorStatus(refs.collectorListStatus, successMessage, successState);
        setApiStatus("就绪", "ok");
      } catch (error) {
        const message =
          action === "proxy-test"
            ? "代理测试失败；请重新写入代理配置或检查网络连通性"
            : action === "validate"
              ? "身份验证失败；请重新写入 Cookie 或检查网络连通性"
              : `操作失败：${error.message}`;
        setCollectorStatus(refs.collectorListStatus, message, "error");
        setApiStatus(
          action === "proxy-test"
            ? "代理测试失败"
            : action === "validate"
              ? "身份验证失败"
              : `异常: ${error.message}`,
          "error",
        );
      }
    });
  }

  function normalizeCollectorPolicy(payload, platform) {
    const source = payload?.policy || payload?.data?.policy || payload?.data || payload || {};
    return {
      platform: source.platform === "tiktok" ? "tiktok" : platform,
      strategy: ["sticky_balanced", "least_loaded"].includes(source.strategy || source.mode)
        ? source.strategy || source.mode
        : "sticky_balanced",
      default_identity_id: String(source.default_identity_id || ""),
      global_max_parallel: Math.max(1, Number(source.global_max_parallel || 2)),
      binding_failure: source.binding_failure === "fallback" ? "fallback" : "pause",
      failure_threshold: Math.max(1, Number(source.failure_threshold || 3)),
      cooldown_seconds: Math.max(0, Number(source.cooldown_seconds ?? 1800)),
    };
  }

  function mapCollectorPolicyToForm(policy) {
    refs.collectorPolicyStrategy.value = policy.strategy;
    refs.collectorPolicyParallel.value = String(policy.global_max_parallel);
    refs.collectorPolicyBindingFailure.value = policy.binding_failure;
    refs.collectorPolicyThreshold.value = String(policy.failure_threshold);
    refs.collectorPolicyCooldown.value = String(policy.cooldown_seconds);
    populateCollectorIdentitySelect(
      refs.collectorPolicyDefaultIdentity,
      policy.platform,
      "自动选择",
      {
        includeUnavailable: true,
        preserveUnavailable: true,
        selectedValue: policy.default_identity_id,
      },
    );
    if (
      policy.default_identity_id &&
      !Array.from(refs.collectorPolicyDefaultIdentity.options).some(
        (option) => option.value === policy.default_identity_id,
      )
    ) {
      const unavailable = document.createElement("option");
      unavailable.value = policy.default_identity_id;
      unavailable.textContent = `不可用身份 · ${policy.default_identity_id}`;
      refs.collectorPolicyDefaultIdentity.appendChild(unavailable);
    }
    refs.collectorPolicyDefaultIdentity.value = policy.default_identity_id;
  }

  async function loadCollectorPolicy(platform = refs.collectorPolicyPlatform.value) {
    const controlsVisiblePolicy = refs.collectorPolicyPlatform.value === platform;
    if (controlsVisiblePolicy) {
      setCollectorStatus(refs.collectorPolicyStatus, `正在加载${collectorPlatformLabel(platform)}路由策略…`);
    }
    try {
      const payload = await fetchJson(
        `/ui/api/collector-policies/${encodeURIComponent(platform)}`,
        {
          method: "GET",
          headers: headerOptions(false),
        },
      );
      const policy = normalizeCollectorPolicy(payload, platform);
      state.collectorPolicies[platform] = policy;
      if (refs.collectorPolicyPlatform.value === platform) {
        mapCollectorPolicyToForm(policy);
        setCollectorStatus(refs.collectorPolicyStatus, `${collectorPlatformLabel(platform)}策略已载入`);
      }
    } catch (error) {
      const fallback = normalizeCollectorPolicy({}, platform);
      state.collectorPolicies[platform] = fallback;
      if (refs.collectorPolicyPlatform.value === platform) {
        mapCollectorPolicyToForm(fallback);
        setCollectorStatus(refs.collectorPolicyStatus, `策略加载失败：${error.message}`, "error");
      }
    }
  }

  function collectorPolicyFromForm() {
    return {
      platform: refs.collectorPolicyPlatform.value,
      strategy: refs.collectorPolicyStrategy.value,
      default_identity_id: refs.collectorPolicyDefaultIdentity.value || "",
      global_max_parallel: Math.max(1, Number(refs.collectorPolicyParallel.value || 1)),
      binding_failure: refs.collectorPolicyBindingFailure.value,
      failure_threshold: Math.max(1, Number(refs.collectorPolicyThreshold.value || 1)),
      cooldown_seconds: Math.max(0, Number(refs.collectorPolicyCooldown.value || 0)),
    };
  }

  async function saveCollectorPolicy() {
    const policy = collectorPolicyFromForm();
    setCollectorStatus(refs.collectorPolicyStatus, "正在保存路由策略…");
    try {
      const payload = await fetchJson(
        `/ui/api/collector-policies/${encodeURIComponent(policy.platform)}`,
        {
          method: "PUT",
          headers: headerOptions(true),
          body: JSON.stringify(policy),
        },
      );
      const saved = normalizeCollectorPolicy(payload, policy.platform);
      state.collectorPolicies[policy.platform] = saved;
      mapCollectorPolicyToForm(saved);
      setCollectorStatus(refs.collectorPolicyStatus, "路由策略保存成功", "success");
      setApiStatus("就绪", "ok");
    } catch (error) {
      setCollectorStatus(refs.collectorPolicyStatus, `保存失败：${error.message}`, "error");
      setApiStatus(`异常: ${error.message}`, "error");
    }
  }

  function normalizeCollectorAccountTargetKey(value) {
    const input = String(value || "").trim();
    if (!input) {
      return "";
    }
    try {
      const url = new URL(input);
      if (url.protocol && url.host) {
        const path = url.pathname.replace(/\/+$/, "");
        return `${url.protocol.toLowerCase()}//${url.host.toLowerCase()}${path}`;
      }
    } catch {}
    return input.split("?", 1)[0].split("#", 1)[0].replace(/\/+$/, "");
  }

  function collectorAssignmentsFromPayload(payload) {
    if (Array.isArray(payload)) {
      return payload;
    }
    if (Array.isArray(payload?.assignments)) {
      return payload.assignments;
    }
    if (Array.isArray(payload?.items)) {
      return payload.items;
    }
    if (Array.isArray(payload?.data?.assignments)) {
      return payload.data.assignments;
    }
    return [];
  }

  function normalizeCollectorAssignment(item, platform) {
    const assignment = item && typeof item === "object" ? item : {};
    return {
      platform: assignment.platform === "tiktok" ? "tiktok" : platform,
      target_type: String(assignment.target_type || "account").toLowerCase(),
      target_key: String(assignment.target_key || "").trim(),
      identity_id: String(assignment.identity_id || "").trim(),
      source: String(assignment.source || "explicit").toLowerCase(),
      updated_at: String(assignment.updated_at || ""),
    };
  }

  function collectorAssignmentSourceLabel(source) {
    return {
      explicit: "手动固定",
      policy: "自动粘连",
      legacy: "旧配置迁移",
    }[source] || "账号绑定";
  }

  function collectorAssignmentPageState(platform = refs.collectorAssignmentPlatform.value) {
    return state.collectorAssignmentPagination[platform];
  }

  function renderCollectorAssignmentPager(platform = refs.collectorAssignmentPlatform.value) {
    if (refs.collectorAssignmentPlatform.value !== platform) {
      return;
    }
    const pagination = collectorAssignmentPageState(platform);
    const loading = state.collectorAssignmentsLoading[platform];
    const start = pagination.total
      ? (pagination.page - 1) * pagination.pageSize + 1
      : 0;
    const end = Math.min(pagination.total, pagination.page * pagination.pageSize);
    refs.collectorBindingPager.hidden = pagination.total === 0;
    refs.collectorBindingPageRange.textContent = `${start}–${end} / ${pagination.total.toLocaleString("zh-CN")}`;
    refs.collectorBindingPageSize.value = String(pagination.pageSize);
    refs.collectorBindingPrevBtn.disabled = loading || pagination.page <= 1;
    refs.collectorBindingNextBtn.disabled = loading || pagination.page >= pagination.pages;
    refs.collectorBindingPageInput.min = "1";
    refs.collectorBindingPageInput.max = String(pagination.pages);
    refs.collectorBindingPageInput.value = String(pagination.page);
    refs.collectorBindingPageInput.disabled = loading;
    refs.collectorBindingPageJumpBtn.disabled = loading;
    refs.collectorBindingPageMeta.textContent = `第 ${pagination.page} / ${pagination.pages} 页`;
  }

  function renderCollectorAssignments(platform = refs.collectorAssignmentPlatform.value) {
    if (refs.collectorAssignmentPlatform.value !== platform) {
      return;
    }
    const items = state.collectorAssignments[platform] || [];
    const pagination = collectorAssignmentPageState(platform);
    refs.collectorAssignmentList.innerHTML = "";
    refs.collectorAssignmentList.setAttribute("aria-busy", "false");
    refs.collectorBindingCount.textContent = pagination.total.toLocaleString("zh-CN");
    renderCollectorAssignmentPager(platform);
    if (!items.length) {
      if (pagination.search) {
        refs.collectorAssignmentList.innerHTML = `
          <div class="empty-tip collector-binding-empty">
            <span>没有与“${escapeHtml(pagination.search)}”匹配的账号绑定。</span>
            <button type="button" class="btn ghost" data-collector-binding-action="clear-search">清除搜索</button>
          </div>
        `;
        refs.collectorBindingListStatus.textContent = "当前搜索没有结果";
      } else {
        refs.collectorAssignmentList.innerHTML = `
          <div class="empty-tip collector-binding-empty">
            该平台还没有账号绑定；未绑定账号会按平台策略自动选择身份。
          </div>
        `;
        refs.collectorBindingListStatus.textContent = "暂无账号绑定";
      }
      return;
    }
    const fragment = document.createDocumentFragment();
    items.forEach((assignment) => {
      const identity = collectorIdentityById(assignment.identity_id);
      const row = document.createElement("article");
      row.className = "collector-binding-row";
      row.dataset.targetKey = assignment.target_key;
      row.dataset.identityId = assignment.identity_id;
      const main = document.createElement("div");
      main.className = "collector-binding-main";
      const target = document.createElement("strong");
      target.textContent = assignment.target_key;
      target.title = assignment.target_key;
      const meta = document.createElement("span");
      const identityLabel = identity
        ? `${identity.name} · ${collectorStateLabel(collectorIdentityState(identity))}`
        : `${assignment.identity_id || "未知身份"} · 已不存在`;
      meta.textContent = `${collectorAssignmentSourceLabel(assignment.source)} → ${identityLabel}`;
      main.append(target, meta);
      const actions = document.createElement("div");
      actions.className = "collector-binding-actions";
      const loadButton = document.createElement("button");
      loadButton.type = "button";
      loadButton.className = "btn ghost";
      loadButton.dataset.collectorBindingAction = "load";
      loadButton.textContent = "载入";
      const unbindButton = document.createElement("button");
      unbindButton.type = "button";
      unbindButton.className = "btn ghost danger";
      unbindButton.dataset.collectorBindingAction = "unbind";
      unbindButton.textContent = "解除绑定";
      actions.append(loadButton, unbindButton);
      row.append(main, actions);
      fragment.appendChild(row);
    });
    refs.collectorAssignmentList.appendChild(fragment);
    const rangeStart = (pagination.page - 1) * pagination.pageSize + 1;
    const rangeEnd = Math.min(pagination.total, rangeStart + items.length - 1);
    refs.collectorBindingListStatus.textContent = `${collectorPlatformLabel(platform)} · 显示 ${rangeStart}–${rangeEnd} / ${pagination.total.toLocaleString("zh-CN")}`;
  }

  async function loadCollectorAssignments(platform = refs.collectorAssignmentPlatform.value) {
    const pagination = collectorAssignmentPageState(platform);
    state.collectorAssignmentRequests[platform]?.abort();
    const controller = new AbortController();
    state.collectorAssignmentRequests[platform] = controller;
    const requestId = ++pagination.requestId;
    state.collectorAssignmentsLoading[platform] = true;
    if (refs.collectorAssignmentPlatform.value === platform) {
      if (state.collectorAssignmentsLoaded[platform]) {
        renderCollectorAssignments(platform);
      }
      renderCollectorAssignmentPager(platform);
      refs.collectorAssignmentList.setAttribute("aria-busy", "true");
      refs.collectorBindingListStatus.textContent = `正在加载${collectorPlatformLabel(platform)}账号绑定…`;
      if (!state.collectorAssignmentsLoaded[platform]) {
        refs.collectorBindingCount.textContent = "…";
        refs.collectorAssignmentList.innerHTML = '<div class="loading-state">正在读取账号绑定…</div>';
      }
    }
    try {
      const query = new URLSearchParams({
        platform,
        target_type: "account",
        page: String(pagination.page),
        page_size: String(pagination.pageSize),
      });
      if (pagination.search) {
        query.set("search", pagination.search);
      }
      const payload = await fetchJson(
        `/ui/api/collector-assignments?${query.toString()}`,
        {
          method: "GET",
          headers: headerOptions(false),
          signal: controller.signal,
        },
      );
      if (requestId !== pagination.requestId) {
        return;
      }
      state.collectorAssignments[platform] = collectorAssignmentsFromPayload(payload)
        .map((item) => normalizeCollectorAssignment(item, platform))
        .filter((item) => item.target_key && item.identity_id && item.target_type === "account");
      pagination.total = Math.max(
        0,
        Number(payload?.total ?? state.collectorAssignments[platform].length),
      );
      pagination.pageSize = Math.max(1, Number(payload?.page_size ?? pagination.pageSize));
      pagination.pages = Math.max(1, Number(payload?.pages ?? 1));
      pagination.page = Math.min(
        pagination.pages,
        Math.max(1, Number(payload?.page ?? pagination.page)),
      );
      state.collectorAssignmentsLoaded[platform] = true;
      renderCollectorAssignments(platform);
    } catch (error) {
      if (error?.name === "AbortError" || requestId !== pagination.requestId) {
        return;
      }
      if (refs.collectorAssignmentPlatform.value === platform) {
        refs.collectorAssignmentList.setAttribute("aria-busy", "false");
        refs.collectorAssignmentList.innerHTML = `
          <div class="error-state collector-binding-empty">
            <strong>账号绑定加载失败</strong>
            <button type="button" class="btn ghost" data-collector-binding-action="retry">重试</button>
          </div>
        `;
        refs.collectorBindingListStatus.textContent = `加载失败：${error.message}`;
      }
    } finally {
      if (requestId === pagination.requestId) {
        state.collectorAssignmentsLoading[platform] = false;
        state.collectorAssignmentRequests[platform] = null;
        renderCollectorAssignmentPager(platform);
      }
    }
  }

  function collectorAssignmentFromForm() {
    return {
      platform: refs.collectorAssignmentPlatform.value,
      target_type: "account",
      target_key: normalizeCollectorAccountTargetKey(refs.collectorAssignmentKey.value),
      identity_id: refs.collectorAssignmentIdentity.value || "",
      source: "explicit",
    };
  }

  function loadCollectorAssignmentIntoForm(assignment) {
    refs.collectorAssignmentKey.value = assignment.target_key;
    populateCollectorIdentitySelect(
      refs.collectorAssignmentIdentity,
      assignment.platform,
      "选择一个可路由身份",
      {
        preserveUnavailable: true,
        selectedValue: assignment.identity_id,
      },
    );
    setCollectorStatus(
      refs.collectorAssignmentStatus,
      collectorIdentityIsRoutable(collectorIdentityById(assignment.identity_id))
        ? "已载入账号绑定，可更换身份或明确解除绑定"
        : "已载入账号绑定；当前身份不可路由，只能更换身份或解除绑定",
    );
    refs.collectorAssignmentIdentity.focus();
  }

  async function saveCollectorAssignment() {
    if (!refs.collectorAssignmentForm.checkValidity()) {
      refs.collectorAssignmentForm.reportValidity();
      return;
    }
    const assignment = collectorAssignmentFromForm();
    const identity = collectorIdentityById(assignment.identity_id);
    if (!assignment.identity_id || !collectorIdentityIsRoutable(identity)) {
      setCollectorStatus(
        refs.collectorAssignmentStatus,
        "请选择一个当前可路由的身份；如需解除绑定，请使用“解除绑定”按钮",
        "error",
      );
      refs.collectorAssignmentIdentity.focus();
      return;
    }
    refs.collectorAssignmentKey.value = assignment.target_key;
    setCollectorStatus(refs.collectorAssignmentStatus, "正在保存账号绑定…");
    try {
      await fetchJson("/ui/api/collector-assignments", {
        method: "PUT",
        headers: headerOptions(true),
        body: JSON.stringify({ assignments: [assignment] }),
      });
      await loadCollectorAssignments(assignment.platform);
      setCollectorStatus(refs.collectorAssignmentStatus, "账号已固定到指定身份", "success");
      setApiStatus("就绪", "ok");
    } catch (error) {
      setCollectorStatus(refs.collectorAssignmentStatus, `保存失败：${error.message}`, "error");
      setApiStatus(`异常: ${error.message}`, "error");
    }
  }

  async function removeCollectorAssignment(platform, targetKey, { confirmAction = true } = {}) {
    const normalizedTarget = normalizeCollectorAccountTargetKey(targetKey);
    if (!normalizedTarget) {
      setCollectorStatus(refs.collectorAssignmentStatus, "请先填写要解除绑定的账号主页 URL", "error");
      refs.collectorAssignmentKey.focus();
      return false;
    }
    if (confirmAction && !window.confirm(`确认解除该账号的身份绑定？\n${normalizedTarget}`)) {
      return false;
    }
    setCollectorStatus(refs.collectorAssignmentStatus, "正在解除账号绑定…");
    try {
      const payload = await fetchJson("/ui/api/collector-assignments", {
        method: "PUT",
        headers: headerOptions(true),
        body: JSON.stringify({
          assignments: [
            {
              platform,
              target_type: "account",
              target_key: normalizedTarget,
              identity_id: "",
            },
          ],
        }),
      });
      const removed = Math.max(0, Number(payload?.removed ?? payload?.data?.removed ?? 0));
      await loadCollectorAssignments(platform);
      if (removed < 1) {
        setCollectorStatus(
          refs.collectorAssignmentStatus,
          "未找到完全匹配的账号绑定，没有删除任何记录",
          "warning",
        );
        return false;
      }
      if (normalizeCollectorAccountTargetKey(refs.collectorAssignmentKey.value) === normalizedTarget) {
        refs.collectorAssignmentIdentity.value = "";
      }
      setCollectorStatus(refs.collectorAssignmentStatus, "账号绑定已解除，将恢复自动路由", "success");
      setApiStatus("就绪", "ok");
      return true;
    } catch (error) {
      setCollectorStatus(refs.collectorAssignmentStatus, `解绑失败：${error.message}`, "error");
      setApiStatus(`异常: ${error.message}`, "error");
      return false;
    }
  }

  function collectorPreviewItems(payload) {
    if (Array.isArray(payload)) {
      return payload;
    }
    if (Array.isArray(payload?.assignments)) {
      return payload.assignments;
    }
    if (Array.isArray(payload?.items)) {
      return payload.items;
    }
    if (Array.isArray(payload?.data?.assignments)) {
      return payload.data.assignments;
    }
    return [];
  }

  function renderCollectorPreview(payload, requestedCount) {
    const items = collectorPreviewItems(payload);
    refs.collectorPreviewResult.innerHTML = "";
    refs.collectorPreviewResult.hidden = false;
    if (!items.length) {
      refs.collectorPreviewResult.innerHTML = '<div class="empty-tip">没有可展示的路由结果</div>';
      return;
    }
    const fragment = document.createDocumentFragment();
    items.forEach((item) => {
      const identityId = String(item.identity_id || item.selected_identity_id || "");
      const identity = state.collectorIdentities.find((entry) => entry.identity_id === identityId);
      const row = document.createElement("div");
      row.className = "collector-preview-row";
      const rawReason = String(item.reason || item.source || item.strategy || "policy");
      const reason = {
        stored_binding: "已有绑定",
        fixed_binding: "固定绑定",
        explicit: "明确绑定",
        sticky_balanced: "稳定粘连 + 均衡",
        least_loaded: "当前最空闲",
        policy: "平台策略",
      }[rawReason] || rawReason;
      row.innerHTML = `
        <div>
          <strong>${escapeHtml(item.target_key || item.target || "—")}</strong>
          <span>${escapeHtml(reason)}</span>
        </div>
        <span class="collector-preview-arrow" aria-hidden="true">→</span>
        <div class="collector-preview-identity">
          <strong>${escapeHtml(identity?.name || identityId || "未分配")}</strong>
          <span>${escapeHtml(identity ? collectorPlatformLabel(identity.platform) : "无可用身份")}</span>
        </div>
      `;
      fragment.appendChild(row);
    });
    refs.collectorPreviewResult.appendChild(fragment);
    const counts = payload?.counts || payload?.data?.counts || {};
    const assigned = Number(counts.assigned ?? items.filter((item) => item.identity_id).length);
    setCollectorStatus(
      refs.collectorPreviewStatus,
      `预览 ${requestedCount} 个目标 · 已分配 ${assigned} · 未分配 ${Math.max(0, requestedCount - assigned)}`,
      assigned === requestedCount ? "success" : "",
    );
  }

  async function previewCollectorRouting() {
    const fallbackTarget = refs.collectorAssignmentKey.value.trim();
    const targets = String(refs.collectorPreviewTargets.value || fallbackTarget)
      .split(/\r?\n/)
      .map(normalizeCollectorAccountTargetKey)
      .filter(Boolean);
    if (!targets.length) {
      setCollectorStatus(refs.collectorPreviewStatus, "请至少输入一个目标标识", "error");
      refs.collectorPreviewTargets.focus();
      return;
    }
    const body = {
      platform: refs.collectorAssignmentPlatform.value,
      target_type: "account",
      targets: targets.map((targetKey) => ({ target_key: targetKey })),
    };
    setCollectorStatus(refs.collectorPreviewStatus, "正在计算路由结果…");
    refs.collectorPreviewResult.hidden = true;
    try {
      const payload = await fetchJson("/ui/api/collector-policies/preview", {
        method: "POST",
        headers: headerOptions(true),
        body: JSON.stringify(body),
      });
      renderCollectorPreview(payload, targets.length);
      setApiStatus("就绪", "ok");
    } catch (error) {
      setCollectorStatus(refs.collectorPreviewStatus, `预览失败：${error.message}`, "error");
      setApiStatus(`异常: ${error.message}`, "error");
    }
  }
  return {
    collectorAuthModeLabel,
    renderCollectorIdentities,
    collectorIdentityIsRoutable,
    collectorIdentityById,
    populateCollectorIdentitySelect,
    syncCollectorIdentitySelectors,
    loadCollectorIdentities,
    setCollectorStatus,
    syncCollectorCredentialFields,
    openCollectorIdentityDialog,
    closeCollectorIdentityDialog,
    reconnectCollectorLoginBrowser,
    openCollectorLoginBrowser,
    closeCollectorLoginBrowserDialog,
    stopCollectorLoginBrowser,
    captureCollectorLoginBrowserCredentials,
    toggleCollectorLoginBrowserFullscreen,
    saveCollectorIdentity,
    runCollectorIdentityAction,
    loadCollectorPolicy,
    saveCollectorPolicy,
    collectorAssignmentPageState,
    loadCollectorAssignments,
    loadCollectorAssignmentIntoForm,
    saveCollectorAssignment,
    removeCollectorAssignment,
    previewCollectorRouting,
  };
}
