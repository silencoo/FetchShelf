import {
  ArrowUp,
  Braces,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  Copy,
  CornerDownRight,
  Download,
  Ellipsis,
  Eye,
  ExternalLink,
  File,
  FileAudio,
  FileImage,
  FileText,
  FileVideo,
  Folder,
  FolderOpen,
  House,
  ImagePlus,
  KeyRound,
  Maximize2,
  Minimize2,
  PanelLeftClose,
  PanelLeftOpen,
  Pin,
  Play,
  Radar,
  RefreshCw,
  Save,
  Search,
  Settings,
  Trash2,
  Users,
  Video,
  X,
  createIcons,
} from "lucide";

const LUCIDE_ICONS = {
  ArrowUp,
  Braces,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  Copy,
  CornerDownRight,
  Download,
  Ellipsis,
  Eye,
  ExternalLink,
  File,
  FileAudio,
  FileImage,
  FileText,
  FileVideo,
  Folder,
  FolderOpen,
  House,
  ImagePlus,
  KeyRound,
  Maximize2,
  Minimize2,
  PanelLeftClose,
  PanelLeftOpen,
  Pin,
  Play,
  Radar,
  RefreshCw,
  Save,
  Search,
  Settings,
  Trash2,
  Users,
  Video,
  X,
};

function refreshIcons(root = document) {
  createIcons({
    root,
    icons: LUCIDE_ICONS,
    attrs: {
      "aria-hidden": "true",
      "stroke-width": 1.8,
    },
  });
}

const state = {
  token: "",
  logAfterId: 0,
  logCount: 0,
  ws: null,
  wsActive: false,
  wsConnecting: false,
  autoScroll: true,
  showDebugLogs: false,
  logRecords: [],
  fileEntries: [],
  fileSearch: "",
  filePage: 1,
  filePageSize: 24,
  filePages: 1,
  fileTotal: 0,
  fileSearchTimer: null,
  focusFilesAfterLoad: false,
  currentScope: "download",
  currentPath: "",
  currentParentPath: "",
  selectedFilePath: "",
  filePreviewRequestId: 0,
  fileMasonryObserver: null,
  fileMasonryFrame: 0,
  fileLightboxIndex: -1,
  fileLightboxRestoreFocus: null,
  fileAccountContext: {
    platform: "",
    url: "",
    mark: "",
  },
  selectedTaskId: "",
  taskListLoading: false,
  taskAccountsLoading: false,
  settingsData: {},
  collectorIdentities: [],
  collectMonitorItems: [],
  collectorPolicies: {},
  collectorAssignments: {
    douyin: [],
    tiktok: [],
  },
  collectorAssignmentsLoaded: {
    douyin: false,
    tiktok: false,
  },
  collectorAssignmentsLoading: {
    douyin: false,
    tiktok: false,
  },
  collectorListLoading: false,
  collectorDialogRestoreFocus: null,
  accountRows: {
    douyin: [],
    tiktok: [],
  },
  deletedRows: {
    douyin: [],
    tiktok: [],
  },
  deletedPurge: {
    platform: "",
    mode: "",
    restoreFocus: null,
  },
  accountPagination: {
    active: {
      douyin: { page: 1, pageSize: 25 },
      tiktok: { page: 1, pageSize: 25 },
    },
    deleted: {
      douyin: { page: 1, pageSize: 15 },
      tiktok: { page: 1, pageSize: 15 },
    },
  },
  rawSettingsSource: {},
  rawSettingsSecretsIncluded: false,
  activeTab: "workbench",
  selectionAnchors: {
    active: {
      douyin: null,
      tiktok: null,
    },
    deleted: {
      douyin: null,
      tiktok: null,
    },
  },
  accountBoard: {
    platform: "douyin",
    page: 1,
    pageSize: 24,
    pages: 1,
    total: 0,
    unfilteredTotal: 0,
    columns: 4,
    refreshKind: "auto",
    viewMode: "avatar",
    search: "",
    status: "all",
    sort: "configured",
    searchTimer: null,
  },
  accountBoardDirty: true,
  boardAvatarBatchRunning: false,
};

const refs = {
  tabButtons: Array.from(document.querySelectorAll(".tab-btn")),
  sidebar: document.getElementById("primary-sidebar"),
  sidebarToggleBtn: document.getElementById("sidebar-toggle-btn"),
  commandTitle: document.getElementById("command-title"),
  tokenInput: document.getElementById("token-input"),
  applyTokenBtn: document.getElementById("apply-token-btn"),
  wsStatus: document.getElementById("ws-status"),
  apiStatus: document.getElementById("api-status"),

  settingsForm: document.getElementById("settings-form"),
  settingsReloadBtn: document.getElementById("settings-reload-btn"),
  settingsSaveBtn: document.getElementById("settings-save-btn"),
  settingsStatus: document.getElementById("settings-status"),
  settingsRawEditor: document.getElementById("settings-raw-editor"),
  settingsRawLoadBtn: document.getElementById("settings-raw-load-btn"),
  settingsRawSaveBtn: document.getElementById("settings-raw-save-btn"),
  settingsRawFormatBtn: document.getElementById("settings-raw-format-btn"),
  settingsRawStatus: document.getElementById("settings-raw-status"),
  settingsRawScope: document.getElementById("settings-raw-scope"),
  settingsRawIncludeSecrets: document.getElementById("settings-raw-include-secrets"),
  settingsRawSearch: document.getElementById("settings-raw-search"),
  settingsRawSearchBtn: document.getElementById("settings-raw-search-btn"),
  settingsRawWrapBtn: document.getElementById("settings-raw-wrap-btn"),
  settingsRawMeta: document.getElementById("settings-raw-meta"),
  settingsAuthLoadBtn: document.getElementById("settings-auth-load-btn"),
  settingsAuthApplyBtn: document.getElementById("settings-auth-apply-btn"),
  settingsAuthSaveBtn: document.getElementById("settings-auth-save-btn"),
  settingsAuthCookieDouyin: document.getElementById("settings-auth-cookie-douyin"),
  settingsAuthCookieTikTok: document.getElementById("settings-auth-cookie-tiktok"),
  settingsAuthTikTokDeviceId: document.getElementById("settings-auth-tiktok-device-id"),
  settingsAuthTikTokUserAgent: document.getElementById("settings-auth-tiktok-user-agent"),
  settingsAuthStatus: document.getElementById("settings-auth-status"),
  accountsSettingsBlock: document.getElementById("accounts-settings-block"),
  accountsToggleBtn: document.getElementById("accounts-toggle-btn"),
  accountsDouyinBody: document.getElementById("accounts-douyin-body"),
  accountsTiktokBody: document.getElementById("accounts-tiktok-body"),
  accountsDouyinPager: document.getElementById("accounts-douyin-pager"),
  accountsTikTokPager: document.getElementById("accounts-tiktok-pager"),
  accountsDouyinAddBtn: document.getElementById("accounts-douyin-add-btn"),
  accountsTiktokAddBtn: document.getElementById("accounts-tiktok-add-btn"),
  accountsExportJsonBtn: document.getElementById("accounts-export-json-btn"),
  accountsImportJsonBtn: document.getElementById("accounts-import-json-btn"),
  accountsImportJsonFile: document.getElementById("accounts-import-json-file"),
  accountsIoStatus: document.getElementById("accounts-io-status"),
  accountsDouyinSearch: document.getElementById("accounts-douyin-search"),
  accountsTikTokSearch: document.getElementById("accounts-tiktok-search"),
  accountsDouyinFormatBtn: document.getElementById("accounts-douyin-format-btn"),
  accountsTikTokFormatBtn: document.getElementById("accounts-tiktok-format-btn"),
  accountsDouyinCheckBtn: document.getElementById("accounts-douyin-check-btn"),
  accountsTikTokCheckBtn: document.getElementById("accounts-tiktok-check-btn"),
  accountsDouyinIdentity: document.getElementById("accounts-douyin-identity"),
  accountsTikTokIdentity: document.getElementById("accounts-tiktok-identity"),
  accountsDouyinIdentityHelp: document.getElementById("accounts-douyin-identity-help"),
  accountsTikTokIdentityHelp: document.getElementById("accounts-tiktok-identity-help"),
  accountsDouyinSelectAllBtn: document.getElementById("accounts-douyin-select-all-btn"),
  accountsDouyinClearSelectBtn: document.getElementById("accounts-douyin-clear-select-btn"),
  accountsDouyinOpenSelectedBtn: document.getElementById("accounts-douyin-open-selected-btn"),
  accountsDouyinBatchField: document.getElementById("accounts-douyin-batch-field"),
  accountsDouyinBatchValue: document.getElementById("accounts-douyin-batch-value"),
  accountsDouyinApplyBatchBtn: document.getElementById("accounts-douyin-apply-batch-btn"),
  accountsDouyinDeleteSelectedBtn: document.getElementById("accounts-douyin-delete-selected-btn"),
  accountsDouyinStatus: document.getElementById("accounts-douyin-status"),
  accountsDouyinDuplicateStatus: document.getElementById("accounts-douyin-duplicate-status"),
  accountsTikTokSelectAllBtn: document.getElementById("accounts-tiktok-select-all-btn"),
  accountsTikTokClearSelectBtn: document.getElementById("accounts-tiktok-clear-select-btn"),
  accountsTikTokOpenSelectedBtn: document.getElementById("accounts-tiktok-open-selected-btn"),
  accountsTikTokBatchField: document.getElementById("accounts-tiktok-batch-field"),
  accountsTikTokBatchValue: document.getElementById("accounts-tiktok-batch-value"),
  accountsTikTokApplyBatchBtn: document.getElementById("accounts-tiktok-apply-batch-btn"),
  accountsTikTokDeleteSelectedBtn: document.getElementById("accounts-tiktok-delete-selected-btn"),
  accountsTikTokStatus: document.getElementById("accounts-tiktok-status"),
  accountsTikTokDuplicateStatus: document.getElementById("accounts-tiktok-duplicate-status"),
  deletedDouyinBody: document.getElementById("deleted-douyin-body"),
  deletedTikTokBody: document.getElementById("deleted-tiktok-body"),
  deletedDouyinPager: document.getElementById("deleted-douyin-pager"),
  deletedTikTokPager: document.getElementById("deleted-tiktok-pager"),
  deletedDouyinSelectAllBtn: document.getElementById("deleted-douyin-select-all-btn"),
  deletedDouyinClearSelectBtn: document.getElementById("deleted-douyin-clear-select-btn"),
  deletedDouyinOpenSelectedBtn: document.getElementById("deleted-douyin-open-selected-btn"),
  deletedDouyinRestoreSelectedBtn: document.getElementById("deleted-douyin-restore-selected-btn"),
  deletedDouyinPurgeSelectedBtn: document.getElementById(
    "deleted-douyin-purge-selected-btn",
  ),
  deletedDouyinPurgeAllBtn: document.getElementById("deleted-douyin-purge-all-btn"),
  deletedTikTokSelectAllBtn: document.getElementById("deleted-tiktok-select-all-btn"),
  deletedTikTokClearSelectBtn: document.getElementById("deleted-tiktok-clear-select-btn"),
  deletedTikTokOpenSelectedBtn: document.getElementById("deleted-tiktok-open-selected-btn"),
  deletedTikTokRestoreSelectedBtn: document.getElementById("deleted-tiktok-restore-selected-btn"),
  deletedTikTokPurgeSelectedBtn: document.getElementById(
    "deleted-tiktok-purge-selected-btn",
  ),
  deletedTikTokPurgeAllBtn: document.getElementById("deleted-tiktok-purge-all-btn"),
  deletedAccountsDialog: document.getElementById("deleted-accounts-dialog"),
  deletedAccountsDialogTitle: document.getElementById("deleted-accounts-dialog-title"),
  deletedAccountsDialogSummary: document.getElementById(
    "deleted-accounts-dialog-summary",
  ),
  deletedAccountsDialogStatus: document.getElementById(
    "deleted-accounts-dialog-status",
  ),
  deletedAccountsDialogCloseBtn: document.getElementById(
    "deleted-accounts-dialog-close-btn",
  ),
  deletedAccountsDialogCancelBtn: document.getElementById(
    "deleted-accounts-dialog-cancel-btn",
  ),
  deletedAccountsDialogConfirmBtn: document.getElementById(
    "deleted-accounts-dialog-confirm-btn",
  ),
  boardPlatform: document.getElementById("board-platform"),
  boardSearch: document.getElementById("board-search"),
  boardSearchClearBtn: document.getElementById("board-search-clear-btn"),
  boardStatusFilter: document.getElementById("board-status-filter"),
  boardSort: document.getElementById("board-sort"),
  boardPageSize: document.getElementById("board-page-size"),
  boardRefreshKind: document.getElementById("board-refresh-kind"),
  boardViewMode: document.getElementById("board-view-mode"),
  boardDensity: document.getElementById("board-density"),
  boardDensityLabel: document.getElementById("board-density-label"),
  boardPrevBtn: document.getElementById("board-prev-btn"),
  boardNextBtn: document.getElementById("board-next-btn"),
  boardReloadBtn: document.getElementById("board-reload-btn"),
  boardAvatarPageBtn: document.getElementById("board-avatar-page-btn"),
  boardAvatarAllBtn: document.getElementById("board-avatar-all-btn"),
  boardPinAllBtn: document.getElementById("board-pin-all-btn"),
  boardMeta: document.getElementById("board-meta"),
  boardStatus: document.getElementById("board-status"),
  boardGrid: document.getElementById("board-grid"),

  logStream: document.getElementById("log-stream"),
  logsAutoscroll: document.getElementById("logs-autoscroll"),
  logsDebugToggle: document.getElementById("logs-debug-toggle"),
  logsClearBtn: document.getElementById("logs-clear-btn"),
  logCount: document.getElementById("log-count"),

  filesScope: document.getElementById("files-scope"),
  filesPath: document.getElementById("files-path"),
  filesSearch: document.getElementById("files-search"),
  filesSearchClearBtn: document.getElementById("files-search-clear-btn"),
  filesPageSize: document.getElementById("files-page-size"),
  filesPrevBtn: document.getElementById("files-prev-btn"),
  filesNextBtn: document.getElementById("files-next-btn"),
  filesPageMeta: document.getElementById("files-page-meta"),
  filesOpenBtn: document.getElementById("files-open-btn"),
  filesHomeBtn: document.getElementById("files-home-btn"),
  filesUpBtn: document.getElementById("files-up-btn"),
  filesRefreshBtn: document.getElementById("files-refresh-btn"),
  filesStatsRefreshBtn: document.getElementById("files-stats-refresh-btn"),
  filesBreadcrumb: document.getElementById("files-breadcrumb"),
  filesMeta: document.getElementById("files-meta"),
  filesStats: document.getElementById("files-stats"),
  filesAccountTools: document.getElementById("file-account-tools"),
  filesAccountContext: document.getElementById("files-account-context"),
  filesBackToBoardBtn: document.getElementById("files-back-to-board-btn"),
  filesPinProfileBtn: document.getElementById("files-pin-profile-btn"),
  filesGenerateAvatarBtn: document.getElementById("files-generate-avatar-btn"),
  filesPinAvatarBtn: document.getElementById("files-pin-avatar-btn"),
  filesList: document.getElementById("files-list"),
  filePreview: document.getElementById("file-preview"),
  fileLightbox: document.getElementById("file-lightbox"),
  fileLightboxTitle: document.getElementById("file-lightbox-title"),
  fileLightboxMeta: document.getElementById("file-lightbox-meta"),
  fileLightboxPosition: document.getElementById("file-lightbox-position"),
  fileLightboxOpenLink: document.getElementById("file-lightbox-open-link"),
  fileLightboxCloseBtn: document.getElementById("file-lightbox-close-btn"),
  fileLightboxPrevBtn: document.getElementById("file-lightbox-prev-btn"),
  fileLightboxNextBtn: document.getElementById("file-lightbox-next-btn"),
  fileLightboxStage: document.getElementById("file-lightbox-stage"),

  sharePlatform: document.getElementById("share-platform"),
  shareInput: document.getElementById("share-input"),
  shareResolveBtn: document.getElementById("share-resolve-btn"),
  shareCopyBtn: document.getElementById("share-copy-btn"),
  shareStatus: document.getElementById("share-status"),
  shareResult: document.getElementById("share-result"),

  workflowAccountPlatform: document.getElementById("workflow-account-platform"),
  workflowAccountSource: document.getElementById("workflow-account-source"),
  workflowAccountIdentity: document.getElementById("workflow-account-identity"),
  workflowAccountCookie: document.getElementById("workflow-account-cookie"),
  workflowAccountProxy: document.getElementById("workflow-account-proxy"),
  workflowAccountIdentityHelp: document.getElementById("workflow-account-identity-help"),
  workflowAccountRunBtn: document.getElementById("workflow-account-run-btn"),
  workflowAccountStatus: document.getElementById("workflow-account-status"),
  workflowAccountSummary: document.getElementById("workflow-account-summary"),

  workflowDetailPlatform: document.getElementById("workflow-detail-platform"),
  workflowDetailForm: document.getElementById("workflow-detail-form"),
  workflowDetailLinks: document.getElementById("workflow-detail-links"),
  workflowDetailCount: document.getElementById("workflow-detail-count"),
  workflowDetailIdentity: document.getElementById("workflow-detail-identity"),
  workflowDetailIdentityHelp: document.getElementById("workflow-detail-identity-help"),
  workflowDetailCookie: document.getElementById("workflow-detail-cookie"),
  workflowDetailProxy: document.getElementById("workflow-detail-proxy"),
  workflowDetailRunBtn: document.getElementById("workflow-detail-run-btn"),
  workflowDetailStatus: document.getElementById("workflow-detail-status"),
  workflowDetailSummary: document.getElementById("workflow-detail-summary"),

  scheduleName: document.getElementById("schedule-name"),
  schedulePlatform: document.getElementById("schedule-platform"),
  scheduleSource: document.getElementById("schedule-source"),
  scheduleIdentity: document.getElementById("schedule-identity"),
  scheduleHour: document.getElementById("schedule-hour"),
  scheduleMinute: document.getElementById("schedule-minute"),
  scheduleCookie: document.getElementById("schedule-cookie"),
  scheduleProxy: document.getElementById("schedule-proxy"),
  scheduleIdentityHelp: document.getElementById("schedule-identity-help"),
  scheduleUptimeKumaUrl: document.getElementById("schedule-uptime-kuma-url"),
  scheduleBarkUrl: document.getElementById("schedule-bark-url"),
  scheduleOverlapPolicy: document.getElementById("schedule-overlap-policy"),
  scheduleIdentityFailureAction: document.getElementById(
    "schedule-identity-failure-action",
  ),
  scheduleIdentityFailureThreshold: document.getElementById(
    "schedule-identity-failure-threshold",
  ),
  scheduleNotifyIdentityFailure: document.getElementById(
    "schedule-notify-identity-failure",
  ),
  scheduleCreateBtn: document.getElementById("schedule-create-btn"),
  scheduleRefreshBtn: document.getElementById("schedule-refresh-btn"),
  scheduleStatus: document.getElementById("schedule-status"),
  scheduleList: document.getElementById("schedule-list"),

  monitorName: document.getElementById("monitor-name"),
  monitorCollectId: document.getElementById("monitor-collect-id"),
  monitorInterval: document.getElementById("monitor-interval"),
  monitorLimit: document.getElementById("monitor-limit"),
  monitorDefaultTab: document.getElementById("monitor-default-tab"),
  monitorDefaultEarliest: document.getElementById("monitor-default-earliest"),
  monitorDefaultLatest: document.getElementById("monitor-default-latest"),
  monitorBarkUrl: document.getElementById("monitor-bark-url"),
  monitorIdentity: document.getElementById("monitor-identity"),
  monitorIdentityHelp: document.getElementById("monitor-identity-help"),
  monitorCookie: document.getElementById("monitor-cookie"),
  monitorProxy: document.getElementById("monitor-proxy"),
  monitorEnabled: document.getElementById("monitor-enabled"),
  monitorAccountEnable: document.getElementById("monitor-account-enable"),
  monitorImmediateCrawl: document.getElementById("monitor-immediate-crawl"),
  monitorAutoUpdateEarliest: document.getElementById("monitor-auto-update-earliest"),
  monitorCreateBtn: document.getElementById("monitor-create-btn"),
  monitorRefreshBtn: document.getElementById("monitor-refresh-btn"),
  monitorStatus: document.getElementById("monitor-status"),
  monitorList: document.getElementById("monitor-list"),

  collectorRefreshBtn: document.getElementById("collector-refresh-btn"),
  collectorCreateBtn: document.getElementById("collector-create-btn"),
  collectorTotalCount: document.getElementById("collector-total-count"),
  collectorReadyCount: document.getElementById("collector-ready-count"),
  collectorAttentionCount: document.getElementById("collector-attention-count"),
  collectorLeaseCount: document.getElementById("collector-lease-count"),
  collectorPlatformFilter: document.getElementById("collector-platform-filter"),
  collectorStatusFilter: document.getElementById("collector-status-filter"),
  collectorListStatus: document.getElementById("collector-list-status"),
  collectorIdentityList: document.getElementById("collector-identity-list"),
  collectorPolicyForm: document.getElementById("collector-policy-form"),
  collectorPolicyPlatform: document.getElementById("collector-policy-platform"),
  collectorPolicyStrategy: document.getElementById("collector-policy-strategy"),
  collectorPolicyDefaultIdentity: document.getElementById("collector-policy-default-identity"),
  collectorPolicyParallel: document.getElementById("collector-policy-parallel"),
  collectorPolicyThreshold: document.getElementById("collector-policy-threshold"),
  collectorPolicyCooldown: document.getElementById("collector-policy-cooldown"),
  collectorPolicyBindingFailure: document.getElementById("collector-policy-binding-failure"),
  collectorPolicySaveBtn: document.getElementById("collector-policy-save-btn"),
  collectorPolicyStatus: document.getElementById("collector-policy-status"),
  collectorAssignmentForm: document.getElementById("collector-assignment-form"),
  collectorAssignmentPlatform: document.getElementById("collector-assignment-platform"),
  collectorAssignmentType: document.getElementById("collector-assignment-type"),
  collectorAssignmentKey: document.getElementById("collector-assignment-key"),
  collectorAssignmentIdentity: document.getElementById("collector-assignment-identity"),
  collectorAssignmentSaveBtn: document.getElementById("collector-assignment-save-btn"),
  collectorAssignmentUnbindBtn: document.getElementById("collector-assignment-unbind-btn"),
  collectorAssignmentStatus: document.getElementById("collector-assignment-status"),
  collectorAssignmentList: document.getElementById("collector-assignment-list"),
  collectorBindingListStatus: document.getElementById("collector-binding-list-status"),
  collectorBindingCount: document.getElementById("collector-binding-count"),
  collectorPreviewBtn: document.getElementById("collector-preview-btn"),
  collectorPreviewTargets: document.getElementById("collector-preview-targets"),
  collectorPreviewStatus: document.getElementById("collector-preview-status"),
  collectorPreviewResult: document.getElementById("collector-preview-result"),
  collectorIdentityDialog: document.getElementById("collector-identity-dialog"),
  collectorIdentityForm: document.getElementById("collector-identity-form"),
  collectorDialogTitle: document.getElementById("collector-dialog-title"),
  collectorDialogDescription: document.getElementById("collector-dialog-description"),
  collectorDialogCloseBtn: document.getElementById("collector-dialog-close-btn"),
  collectorDialogCancelBtn: document.getElementById("collector-dialog-cancel-btn"),
  collectorDialogSaveBtn: document.getElementById("collector-dialog-save-btn"),
  collectorDialogStatus: document.getElementById("collector-dialog-status"),
  collectorIdentityId: document.getElementById("collector-identity-id"),
  collectorIdentityName: document.getElementById("collector-identity-name"),
  collectorIdentityPlatform: document.getElementById("collector-identity-platform"),
  collectorIdentityWeight: document.getElementById("collector-identity-weight"),
  collectorIdentityDelay: document.getElementById("collector-identity-delay"),
  collectorIdentityConcurrency: document.getElementById("collector-identity-concurrency"),
  collectorIdentityEnabled: document.getElementById("collector-identity-enabled"),
  collectorIdentityCookie: document.getElementById("collector-identity-cookie"),
  collectorIdentityProxy: document.getElementById("collector-identity-proxy"),
  collectorIdentityDeviceId: document.getElementById("collector-identity-device-id"),
  collectorIdentityUserAgent: document.getElementById("collector-identity-user-agent"),
  collectorTikTokCredentialFields: document.getElementById("collector-tiktok-credential-fields"),

  taskEndpoint: document.getElementById("task-endpoint"),
  taskIdentity: document.getElementById("task-identity"),
  taskIdentityHelp: document.getElementById("task-identity-help"),
  taskPayload: document.getElementById("task-payload"),
  taskTemplateBtn: document.getElementById("task-template-btn"),
  taskRunBtn: document.getElementById("task-run-btn"),
  taskLabStatus: document.getElementById("task-lab-status"),
  taskCopyBtn: document.getElementById("task-copy-btn"),
  taskStatus: document.getElementById("task-status"),
  taskSummary: document.getElementById("task-summary"),
  taskProgressBlock: document.getElementById("task-progress-block"),
  taskProgress: document.getElementById("task-progress"),
  taskProgressLabel: document.getElementById("task-progress-label"),
  taskProgressValue: document.getElementById("task-progress-value"),
  taskProgressMeta: document.getElementById("task-progress-meta"),
  taskAccountCheckpoints: document.getElementById("task-account-checkpoints"),
  taskAccountSummary: document.getElementById("task-account-summary"),
  taskAccountList: document.getElementById("task-account-list"),
  taskAccountRefreshBtn: document.getElementById("task-account-refresh-btn"),
  taskResult: document.getElementById("task-result"),
  taskQueueRefreshBtn: document.getElementById("task-queue-refresh-btn"),
  taskQueueMeta: document.getElementById("task-queue-meta"),
  taskQueueList: document.getElementById("task-queue-list"),
};

const TASK_TEMPLATES = {
  "/douyin/detail": {
    detail_id: "7399999999999999999",
    cookie: "",
    proxy: "",
    source: false,
  },
  "/douyin/account": {
    sec_user_id: "MS4wLjABAAAA...",
    tab: "post",
    pages: 1,
    cookie: "",
    proxy: "",
    source: false,
  },
  "/douyin/mix": {
    mix_id: "7399999999999999999",
    detail_id: "",
    cursor: 0,
    count: 12,
    cookie: "",
    proxy: "",
    source: false,
  },
  "/douyin/live": {
    web_rid: "",
    cookie: "",
    proxy: "",
    source: false,
  },
  "/douyin/comment": {
    detail_id: "7399999999999999999",
    pages: 1,
    cursor: 0,
    count: 20,
    count_reply: 3,
    reply: false,
    cookie: "",
    proxy: "",
    source: false,
  },
  "/douyin/reply": {
    detail_id: "7399999999999999999",
    comment_id: "7399999999999999999",
    pages: 1,
    cursor: 0,
    count: 3,
    cookie: "",
    proxy: "",
    source: false,
  },
  "/douyin/search/general": {
    keyword: "关键词",
    pages: 1,
    offset: 0,
    count: 10,
    channel: 0,
    sort_type: 0,
    publish_time: 0,
    duration: 0,
    search_range: 0,
    content_type: 0,
    cookie: "",
    proxy: "",
    source: false,
  },
  "/douyin/search/video": {
    keyword: "关键词",
    pages: 1,
    offset: 0,
    count: 10,
    channel: 1,
    sort_type: 0,
    publish_time: 0,
    duration: 0,
    search_range: 0,
    cookie: "",
    proxy: "",
    source: false,
  },
  "/douyin/search/user": {
    keyword: "关键词",
    pages: 1,
    offset: 0,
    count: 10,
    channel: 2,
    douyin_user_fans: 0,
    douyin_user_type: 0,
    cookie: "",
    proxy: "",
    source: false,
  },
  "/douyin/search/live": {
    keyword: "关键词",
    pages: 1,
    offset: 0,
    count: 10,
    channel: 3,
    cookie: "",
    proxy: "",
    source: false,
  },
  "/tiktok/detail": {
    detail_id: "",
    detail_url: "https://www.tiktok.com/@username/video/7399999999999999999",
    cookie: "",
    proxy: "",
    source: false,
  },
  "/tiktok/account": {
    sec_user_id: "MS4wLjABAAAA...",
    tab: "post",
    pages: 1,
    cookie: "",
    proxy: "",
    source: false,
  },
  "/tiktok/mix": {
    mix_id: "7399999999999999999",
    cursor: 0,
    count: 30,
    cookie: "",
    proxy: "",
    source: false,
  },
  "/tiktok/live": {
    room_id: "",
    cookie: "",
    proxy: "",
    source: false,
  },
  "/workflow/douyin/account_batch": {
    use_settings: false,
    items: [
      {
        mark: "",
        url: "https://www.douyin.com/user/MS4wLjABAAAA...",
        tab: "post",
        earliest: "",
        latest: "",
        enable: true,
      },
    ],
    cookie: "",
    proxy: "",
  },
  "/workflow/tiktok/account_batch": {
    use_settings: false,
    items: [
      {
        mark: "",
        url: "https://www.tiktok.com/@username",
        tab: "post",
        earliest: "",
        latest: "",
        enable: true,
      },
    ],
    cookie: "",
    proxy: "",
  },
  "/workflow/douyin/detail_links": {
    links: ["https://www.douyin.com/video/7399999999999999999"],
    cookie: "",
    proxy: "",
  },
  "/workflow/tiktok/detail_links": {
    links: ["https://www.tiktok.com/@username/video/7399999999999999999"],
    cookie: "",
    proxy: "",
  },
};

const ACCOUNTS_COLLAPSE_STORAGE_KEY = "webui.accounts.collapsed";
const ACTIVE_TAB_STORAGE_KEY = "webui.active.tab";
const LOG_DEBUG_STORAGE_KEY = "webui.logs.debug";
const BOARD_COLUMNS_STORAGE_KEY = "webui.board.columns";
const BOARD_VIEW_MODE_STORAGE_KEY = "webui.board.view_mode";
const TOKEN_STORAGE_KEY = "webui.api.token";
const SIDEBAR_COLLAPSE_STORAGE_KEY = "webui.sidebar.collapsed";

function readStoredBoolean(key, defaultValue = false) {
  try {
    const value = localStorage.getItem(key);
    if (value === null) {
      return defaultValue;
    }
    return value === "true";
  } catch {
    return defaultValue;
  }
}

function applySidebarCollapsed(collapsed, persist = true) {
  const appShell = document.querySelector(".app-shell");
  appShell?.classList.toggle("sidebar-collapsed", collapsed);
  if (!refs.sidebarToggleBtn) {
    return;
  }
  const label = collapsed ? "展开导航" : "收起导航";
  refs.sidebarToggleBtn.setAttribute("aria-expanded", String(!collapsed));
  refs.sidebarToggleBtn.title = label;
  refs.sidebarToggleBtn.querySelector(".sr-only").textContent = label;
  const icon = refs.sidebarToggleBtn.querySelector("svg, [data-lucide]");
  if (icon) {
    icon.setAttribute("data-lucide", collapsed ? "panel-left-open" : "panel-left-close");
  }
  refreshIcons(refs.sidebarToggleBtn);
  refs.tabButtons.forEach((button) => {
    button.title = button.querySelector(".nav-label")?.textContent?.trim() || "";
  });
  if (persist) {
    try {
      localStorage.setItem(SIDEBAR_COLLAPSE_STORAGE_KEY, String(collapsed));
    } catch {
      // The current session can still use the collapsed layout.
    }
  }
}

function setBadge(element, text, kind = "") {
  if (!element) {
    return;
  }
  element.textContent = text;
  element.classList.remove("ok", "warn", "error");
  if (kind) {
    element.classList.add(kind);
  }
}

function setApiStatus(text, kind = "") {
  setBadge(refs.apiStatus, `API: ${text}`, kind);
}

function setWsStatus(text, kind = "") {
  setBadge(refs.wsStatus, `日志: ${text}`, kind);
}

function syncTabOrientation() {
  const tabList = document.querySelector(".top-tabs");
  if (!tabList) {
    return;
  }
  tabList.setAttribute(
    "aria-orientation",
    window.matchMedia("(max-width: 1180px)").matches ? "horizontal" : "vertical",
  );
}

async function withBusyButton(button, busyText, action) {
  if (!button || button.disabled) {
    return;
  }
  const previousMarkup = button.innerHTML;
  button.disabled = true;
  button.classList.add("busy");
  button.setAttribute("aria-busy", "true");
  if (busyText) {
    button.textContent = busyText;
  }
  try {
    await action();
  } finally {
    button.classList.remove("busy");
    button.removeAttribute("aria-busy");
    button.disabled = false;
    button.innerHTML = previousMarkup;
    refreshIcons(button);
  }
}

function headerOptions(json = true) {
  const headers = {};
  if (json) {
    headers["Content-Type"] = "application/json";
  }
  if (state.token) {
    headers.token = state.token;
  }
  return headers;
}

function readStoredToken() {
  try {
    return localStorage.getItem(TOKEN_STORAGE_KEY)?.trim() || "";
  } catch {
    return "";
  }
}

function persistToken(token) {
  try {
    if (token) {
      localStorage.setItem(TOKEN_STORAGE_KEY, token);
    } else {
      localStorage.removeItem(TOKEN_STORAGE_KEY);
    }
    return true;
  } catch {
    return false;
  }
}

async function establishWebUiSession() {
  if (!state.token) {
    return;
  }
  await fetchJson("/token", {
    method: "GET",
    headers: headerOptions(false),
  });
}

async function clearWebUiSession() {
  await fetchJson("/ui/api/session", {
    method: "DELETE",
    headers: headerOptions(false),
  });
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const contentType = response.headers.get("content-type") || "";
  let payload = null;
  if (contentType.includes("application/json")) {
    payload = await response.json();
  } else {
    payload = await response.text();
  }
  if (!response.ok) {
    let detail = "请求失败";
    if (typeof payload === "string" && payload.trim()) {
      detail = payload;
    } else if (payload && typeof payload === "object") {
      detail = payload.detail || payload.message || JSON.stringify(payload);
    }
    throw new Error(detail);
  }
  return payload;
}

function parseLogPayload(payload) {
  if (!payload) {
    return [];
  }
  if (Array.isArray(payload)) {
    return payload;
  }
  if (Array.isArray(payload.logs)) {
    return payload.logs;
  }
  if (Array.isArray(payload.items)) {
    return payload.items;
  }
  if (Array.isArray(payload.data)) {
    return payload.data;
  }
  if (payload.id && payload.message) {
    return [payload];
  }
  return [];
}

function updateLogCount() {
  refs.logCount.textContent = `${state.logCount} 条日志`;
}

function shouldRenderLog(item) {
  const level = String(item?.level || "INFO").toUpperCase();
  if (!state.showDebugLogs && level === "DEBUG") {
    return false;
  }
  const message = String(item?.message || "").trim();
  if (!message) {
    return false;
  }
  const noisyPrefixes = [
    "URL:",
    "Params:",
    "Data:",
    "Headers:",
    "Other:",
    "Response URL:",
    "Response Code:",
    "Response Headers:",
  ];
  if (state.showDebugLogs) {
    return true;
  }
  return !noisyPrefixes.some((prefix) => message.startsWith(prefix));
}

function buildLogRow(item) {
  if (!shouldRenderLog(item)) {
    return null;
  }
  const row = document.createElement("p");
  const level = String(item.level || "INFO").toUpperCase();
  row.className = "log-row";
  row.dataset.level = level;
  row.textContent = `[${item.timestamp || "--"}] [${level}] ${item.message || ""}`;
  state.logCount += 1;
  return row;
}

function rerenderLogs() {
  refs.logStream.innerHTML = "";
  state.logCount = 0;
  const fragment = document.createDocumentFragment();
  for (const item of state.logRecords) {
    const row = buildLogRow(item);
    if (row) {
      fragment.appendChild(row);
    }
  }
  refs.logStream.appendChild(fragment);
  updateLogCount();
  if (state.autoScroll) {
    refs.logStream.scrollTop = refs.logStream.scrollHeight;
  }
}

function appendLogs(logs) {
  if (!logs.length) {
    return;
  }
  const fragment = document.createDocumentFragment();
  for (const item of logs) {
    const id = Number(item.id || 0);
    if (id > state.logAfterId) {
      state.logAfterId = id;
    }
    state.logRecords.push(item);
    const row = buildLogRow(item);
    if (row) {
      fragment.appendChild(row);
    }
  }
  let trimmed = false;
  if (state.logRecords.length > 5000) {
    state.logRecords.splice(0, state.logRecords.length - 5000);
    trimmed = true;
  }
  if (trimmed) {
    rerenderLogs();
    return;
  }
  if (!fragment.childNodes.length) {
    return;
  }
  refs.logStream.appendChild(fragment);
  updateLogCount();
  if (state.autoScroll) {
    refs.logStream.scrollTop = refs.logStream.scrollHeight;
  }
}

function clearLogs() {
  state.logRecords = [];
  refs.logStream.innerHTML = "";
  state.logCount = 0;
  updateLogCount();
}

async function pollLogs() {
  try {
    const query = new URLSearchParams({
      after_id: String(state.logAfterId),
      limit: "200",
    });
    const payload = await fetchJson(`/ui/api/logs?${query.toString()}`, {
      method: "GET",
      headers: headerOptions(false),
    });
    appendLogs(parseLogPayload(payload));
    setApiStatus("就绪", "ok");
  } catch (error) {
    setApiStatus(`异常: ${error.message}`, "error");
  }
}

function closeLogSocket() {
  if (state.ws) {
    state.ws.close();
    state.ws = null;
    state.wsActive = false;
    state.wsConnecting = false;
  }
}

function connectLogSocket() {
  if (state.wsConnecting) {
    return;
  }
  closeLogSocket();
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const params = new URLSearchParams();
  params.set("after_id", String(state.logAfterId || 0));
  const wsUrl = `${protocol}//${location.host}/ui/ws/logs?${params.toString()}`;
  state.wsConnecting = true;
  const ws = new WebSocket(wsUrl);
  state.ws = ws;

  ws.addEventListener("open", () => {
    state.wsActive = true;
    state.wsConnecting = false;
    setWsStatus("WebSocket", "ok");
  });

  ws.addEventListener("message", (event) => {
    try {
      const payload = JSON.parse(event.data);
      appendLogs(parseLogPayload(payload));
    } catch {
      appendLogs([
        {
          id: 0,
          timestamp: new Date().toISOString().slice(0, 19).replace("T", " "),
          level: "INFO",
          message: String(event.data || ""),
        },
      ]);
    }
  });

  ws.addEventListener("close", () => {
    state.wsActive = false;
    state.wsConnecting = false;
    setWsStatus("轮询", "warn");
  });

  ws.addEventListener("error", () => {
    state.wsActive = false;
    state.wsConnecting = false;
    setWsStatus("轮询", "warn");
  });
}

function switchTab(tab) {
  const fallbackTab = "workbench";
  const nextTab = refs.tabButtons.some((button) => button.dataset.tabTarget === tab)
    ? tab
    : fallbackTab;
  state.activeTab = nextTab;
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    const isHidden = panel.dataset.tabPanel !== nextTab;
    panel.classList.toggle("hidden-panel", isHidden);
    panel.hidden = isHidden;
  });
  refs.tabButtons.forEach((button) => {
    const isActive = button.dataset.tabTarget === nextTab;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-selected", String(isActive));
    button.tabIndex = isActive ? 0 : -1;
  });
  const activeButton = refs.tabButtons.find(
    (button) => button.dataset.tabTarget === nextTab,
  );
  const activeLabel = activeButton?.querySelector(".nav-label")?.textContent?.trim();
  if (activeLabel && refs.commandTitle) {
    refs.commandTitle.textContent = activeLabel;
    document.title = `${activeLabel} · DouK Downloader`;
  }
  try {
    localStorage.setItem(ACTIVE_TAB_STORAGE_KEY, nextTab);
  } catch {}
  if (nextTab === "profiles" && state.accountBoardDirty) {
    loadAccountBoard(true);
  }
  if (nextTab === "files") {
    updateFilesAccountContext();
  }
  if (nextTab === "workbench" && !document.hidden) {
    loadTaskList();
  }
  if (nextTab === "collectors") {
    if (!state.collectorIdentities.length) {
      loadCollectorIdentities();
    }
    if (!state.collectorPolicies[refs.collectorPolicyPlatform.value]) {
      loadCollectorPolicy(refs.collectorPolicyPlatform.value);
    }
    const assignmentPlatform = refs.collectorAssignmentPlatform.value;
    if (!state.collectorAssignmentsLoaded[assignmentPlatform]) {
      loadCollectorAssignments(assignmentPlatform);
    }
  }
}

function defaultAccountRow() {
  return {
    mark: "",
    url: "",
    tab: "post",
    earliest: "",
    latest: "",
    enable: true,
    auto_update_earliest: false,
    selected: false,
  };
}

function normalizeAccountRows(rows) {
  if (!Array.isArray(rows)) {
    return [defaultAccountRow()];
  }
  const normalized = rows
    .filter((item) => item && typeof item === "object")
    .map((item) => ({
      mark: String(item.mark || "").trim(),
      url: String(item.url || "").trim(),
      tab: String(item.tab || "post").trim() || "post",
      earliest: String(item.earliest || "").trim(),
      latest: String(item.latest || "").trim(),
      enable: parseBooleanValue(item.enable, true),
      auto_update_earliest: parseBooleanValue(item.auto_update_earliest, false),
      selected: Boolean(item.selected ?? false),
    }));
  return normalized.length ? normalized : [defaultAccountRow()];
}

function defaultDeletedRow() {
  return {
    mark: "",
    url: "",
    tab: "post",
    earliest: "",
    latest: "",
    enable: false,
    auto_update_earliest: false,
    deleted_at: "",
    reason: "",
    selected: false,
  };
}

function normalizeDeletedRows(rows) {
  if (!Array.isArray(rows)) {
    return [];
  }
  return rows
    .filter((item) => item && typeof item === "object")
    .map((item) => ({
      mark: String(item.mark || "").trim(),
      url: String(item.url || "").trim(),
      tab: String(item.tab || "post").trim() || "post",
      earliest: String(item.earliest || "").trim(),
      latest: String(item.latest || "").trim(),
      enable: parseBooleanValue(item.enable, false),
      auto_update_earliest: parseBooleanValue(item.auto_update_earliest, false),
      deleted_at: String(item.deleted_at || "").trim(),
      reason: String(item.reason || "").trim(),
      selected: Boolean(item.selected ?? false),
    }))
    .filter((item) => item.url);
}

function accountRowsKey(platform) {
  return platform === "tiktok" ? "tiktok" : "douyin";
}

function accountBodyRef(platform) {
  return platform === "tiktok" ? refs.accountsTiktokBody : refs.accountsDouyinBody;
}

function deletedBodyRef(platform) {
  return platform === "tiktok" ? refs.deletedTikTokBody : refs.deletedDouyinBody;
}

function escapeAttr(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function escapeHtml(value) {
  return escapeAttr(value);
}

function parseBooleanValue(value, defaultValue = false) {
  if (typeof value === "boolean") {
    return value;
  }
  if (value === null || typeof value === "undefined" || value === "") {
    return defaultValue;
  }
  if (typeof value === "number") {
    return value !== 0;
  }
  const normalized = String(value).trim().toLowerCase();
  const trueValues = new Set(["1", "true", "yes", "on", "enable", "enabled", "启用", "开启"]);
  const falseValues = new Set(["0", "false", "no", "off", "disable", "disabled", "禁用", "关闭"]);
  if (trueValues.has(normalized)) {
    return true;
  }
  if (falseValues.has(normalized)) {
    return false;
  }
  return defaultValue;
}

function duplicateUrlIndexes(platform) {
  const key = accountRowsKey(platform);
  const rows = state.accountRows[key] || [];
  const map = new Map();
  rows.forEach((item, index) => {
    const normalized = normalizeUrl(item.url || "");
    if (!normalized) {
      return;
    }
    const bucket = map.get(normalized) || [];
    bucket.push(index);
    map.set(normalized, bucket);
  });
  const duplicates = new Set();
  map.forEach((indexes) => {
    if (indexes.length > 1) {
      indexes.forEach((index) => duplicates.add(index));
    }
  });
  return {
    duplicates,
    duplicateUrls: Array.from(map.values()).filter((indexes) => indexes.length > 1).length,
  };
}

function setDuplicateStatus(platform, duplicateUrls = 0, duplicateRows = 0) {
  const ref =
    platform === "tiktok"
      ? refs.accountsTikTokDuplicateStatus
      : refs.accountsDouyinDuplicateStatus;
  if (!ref) {
    return;
  }
  if (!duplicateRows) {
    ref.textContent = "未检测到重复 URL";
    return;
  }
  ref.textContent = `检测到重复 URL: ${duplicateUrls} 组，共 ${duplicateRows} 行（建议先规则化 URL）`;
}

function accountSearchQuery(platform) {
  const input = platform === "tiktok" ? refs.accountsTikTokSearch : refs.accountsDouyinSearch;
  return String(input?.value || "").trim().toLowerCase();
}

function indexedAccountRows(platform, section = "active") {
  const key = accountRowsKey(platform);
  const rows = section === "deleted" ? state.deletedRows[key] : state.accountRows[key];
  const query = accountSearchQuery(platform);
  return rows
    .map((item, index) => ({ item, index }))
    .filter(({ item }) => {
      if (!query) {
        return true;
      }
      const text = section === "deleted"
        ? `${item.mark} ${item.url} ${item.tab} ${item.deleted_at} ${item.reason}`
        : `${item.mark} ${item.url} ${item.tab} ${item.earliest} ${item.latest}`;
      return text.toLowerCase().includes(query);
    });
}

function accountPaginationState(platform, section = "active") {
  const key = accountRowsKey(platform);
  const sectionKey = sectionName(section);
  return state.accountPagination[sectionKey][key];
}

function accountPagerRef(platform, section = "active") {
  if (section === "deleted") {
    return platform === "tiktok" ? refs.deletedTikTokPager : refs.deletedDouyinPager;
  }
  return platform === "tiktok" ? refs.accountsTikTokPager : refs.accountsDouyinPager;
}

function pagedAccountRows(platform, section = "active") {
  const matches = indexedAccountRows(platform, section);
  const pagination = accountPaginationState(platform, section);
  const pages = Math.max(1, Math.ceil(matches.length / pagination.pageSize));
  pagination.page = Math.min(Math.max(1, pagination.page), pages);
  const start = (pagination.page - 1) * pagination.pageSize;
  return {
    items: matches.slice(start, start + pagination.pageSize),
    total: matches.length,
    pages,
    start,
  };
}

function renderAccountPager(platform, section = "active") {
  const pager = accountPagerRef(platform, section);
  if (!pager) {
    return;
  }
  const pagination = accountPaginationState(platform, section);
  const { total, pages, start } = pagedAccountRows(platform, section);
  const rows = section === "deleted"
    ? state.deletedRows[accountRowsKey(platform)]
    : state.accountRows[accountRowsKey(platform)];
  const selected = rows.filter((item) => item.selected).length;
  const end = Math.min(total, start + pagination.pageSize);
  pager.innerHTML = `
    <span class="table-pager-summary">
      ${total ? `${start + 1}–${end}` : "0"} / ${total} · 已选 ${selected}
    </span>
    <label class="table-page-size">
      <span>每页</span>
      <select aria-label="每页显示数量">
        ${[15, 25, 50, 100]
          .map(
            (size) =>
              `<option value="${size}" ${pagination.pageSize === size ? "selected" : ""}>${size}</option>`,
          )
          .join("")}
      </select>
    </label>
    <button class="btn ghost pager-prev" type="button" ${pagination.page <= 1 ? "disabled" : ""}>
      <i data-lucide="chevron-left"></i><span>上一页</span>
    </button>
    <span class="table-page-number">第 ${pagination.page} / ${pages} 页</span>
    <button class="btn ghost pager-next" type="button" ${pagination.page >= pages ? "disabled" : ""}>
      <span>下一页</span><i data-lucide="chevron-right"></i>
    </button>
  `;
  pager.querySelector("select")?.addEventListener("change", (event) => {
    pagination.pageSize = Number(event.target.value) || pagination.pageSize;
    pagination.page = 1;
    if (section === "deleted") {
      renderDeletedRows(platform);
    } else {
      renderAccountRows(platform);
    }
  });
  pager.querySelector(".pager-prev")?.addEventListener("click", () => {
    pagination.page = Math.max(1, pagination.page - 1);
    if (section === "deleted") {
      renderDeletedRows(platform);
    } else {
      renderAccountRows(platform);
    }
  });
  pager.querySelector(".pager-next")?.addEventListener("click", () => {
    pagination.page = Math.min(pages, pagination.page + 1);
    if (section === "deleted") {
      renderDeletedRows(platform);
    } else {
      renderAccountRows(platform);
    }
  });
  refreshIcons(pager);
}

function renderAccountRows(platform) {
  const key = accountRowsKey(platform);
  const body = accountBodyRef(platform);
  if (!body) {
    return;
  }
  const { duplicates, duplicateUrls } = duplicateUrlIndexes(platform);
  setDuplicateStatus(platform, duplicateUrls, duplicates.size);
  body.innerHTML = "";
  const fragment = document.createDocumentFragment();
  const page = pagedAccountRows(platform, "active");
  page.items.forEach(({ item, index }) => {
    const tr = document.createElement("tr");
    const duplicate = duplicates.has(index);
    tr.classList.toggle("duplicate-row", duplicate);
    tr.dataset.platform = key;
    tr.dataset.index = String(index);
    tr.dataset.section = "active";
    tr.innerHTML = `
      <td>
        <input data-field="selected" type="checkbox" ${item.selected ? "checked" : ""} />
      </td>
      <td>
        <label class="switch">
          <input data-field="enable" type="checkbox" ${item.enable ? "checked" : ""} />
          <span class="switch-slider"></span>
        </label>
      </td>
      <td>
        <label class="switch">
          <input
            data-field="auto_update_earliest"
            type="checkbox"
            title="下载该账号成功后，自动回写 earliest=今天-回溯天数"
            ${
            item.auto_update_earliest ? "checked" : ""
          }
          />
          <span class="switch-slider"></span>
        </label>
      </td>
      <td>
        <input data-field="mark" type="text" value="${escapeAttr(item.mark)}" placeholder="可选标识" />
      </td>
      <td>
        <input
          data-field="url"
          type="text"
          value="${escapeAttr(item.url)}"
          title="${escapeAttr(item.url)}"
          placeholder="账号主页链接"
        />
      </td>
      <td>
        <input data-field="tab" type="text" value="${escapeAttr(item.tab)}" placeholder="post/favorite/collection" />
      </td>
      <td>
        <input data-field="earliest" type="text" value="${escapeAttr(item.earliest)}" placeholder="YYYY/MM/DD" />
      </td>
      <td>
        <input data-field="latest" type="text" value="${escapeAttr(item.latest)}" placeholder="YYYY/MM/DD" />
      </td>
      <td>
        <button data-action="open-row" class="btn ghost icon-btn-text" type="button">
          <i data-lucide="play"></i><span>打开</span>
        </button>
        <button data-action="remove-row" class="btn ghost danger icon-btn-text" type="button">
          <i data-lucide="trash-2"></i><span>删除</span>
        </button>
        ${duplicate ? '<span class="badge warn duplicate-tag">重复 URL</span>' : ""}
      </td>
    `;
    fragment.appendChild(tr);
  });
  if (!fragment.childNodes.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="9"><span class="empty-tip">无匹配结果</span></td>`;
    fragment.appendChild(tr);
  }
  body.appendChild(fragment);
  renderAccountPager(platform, "active");
  refreshIcons(body);
}

function renderDeletedRows(platform) {
  const key = accountRowsKey(platform);
  const body = deletedBodyRef(platform);
  if (!body) {
    return;
  }
  body.innerHTML = "";
  const fragment = document.createDocumentFragment();
  const page = pagedAccountRows(platform, "deleted");
  page.items.forEach(({ item, index }) => {
    const tr = document.createElement("tr");
    tr.dataset.platform = key;
    tr.dataset.index = String(index);
    tr.dataset.section = "deleted";
    tr.innerHTML = `
      <td>
        <input data-field="selected" type="checkbox" ${item.selected ? "checked" : ""} />
      </td>
      <td>${escapeAttr(item.mark)}</td>
      <td class="url-cell">${escapeAttr(item.url)}</td>
      <td>${escapeAttr(item.tab)}</td>
      <td>${escapeAttr(item.deleted_at || "-")}</td>
      <td>${escapeAttr(item.reason || "-")}</td>
      <td>
        <button data-action="open-row" class="btn ghost icon-btn-text" type="button">
          <i data-lucide="play"></i><span>打开</span>
        </button>
        <button data-action="restore-row" class="btn ghost icon-btn-text" type="button">
          <i data-lucide="refresh-cw"></i><span>撤销</span>
        </button>
      </td>
    `;
    fragment.appendChild(tr);
  });
  if (!fragment.childNodes.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="7"><span class="empty-tip">无匹配结果</span></td>`;
    fragment.appendChild(tr);
  }
  body.appendChild(fragment);
  renderAccountPager(platform, "deleted");
  refreshIcons(body);
}

function setAccountRows(platform, rows) {
  const key = accountRowsKey(platform);
  state.accountRows[key] = normalizeAccountRows(rows);
  state.accountBoardDirty = true;
  renderAccountRows(platform);
}

function setDeletedRows(platform, rows) {
  const key = accountRowsKey(platform);
  state.deletedRows[key] = normalizeDeletedRows(rows);
  renderDeletedRows(platform);
}

function addAccountRow(platform) {
  const key = accountRowsKey(platform);
  state.accountRows[key].unshift(defaultAccountRow());
  accountPaginationState(platform, "active").page = 1;
  renderAccountRows(platform);
}

function removeAccountRow(platform, index, reason = "手动删除") {
  const key = accountRowsKey(platform);
  const rows = state.accountRows[key];
  if (!rows.length) {
    return;
  }
  const [removed] = rows.splice(index, 1);
  if (removed?.url) {
    state.deletedRows[key].unshift(
      defaultDeletedRow(),
    );
    state.deletedRows[key][0] = {
      ...state.deletedRows[key][0],
      ...removed,
      enable: false,
      selected: false,
      deleted_at: new Date().toISOString().slice(0, 19).replace("T", " "),
      reason,
    };
  }
  if (!rows.length) {
    rows.push(defaultAccountRow());
  }
  renderAccountRows(platform);
  renderDeletedRows(platform);
}

function updateAccountRow(platform, index, field, value, section = "active") {
  const key = accountRowsKey(platform);
  const source = section === "deleted" ? state.deletedRows[key] : state.accountRows[key];
  const row = source?.[index];
  if (!row) {
    return;
  }
  row[field] = value;
}

function restoreDeletedRow(platform, index) {
  const key = accountRowsKey(platform);
  const rows = state.deletedRows[key];
  const [row] = rows.splice(index, 1);
  if (row?.url) {
    state.accountRows[key].unshift({
      mark: row.mark,
      url: row.url,
      tab: row.tab || "post",
      earliest: row.earliest || "",
      latest: row.latest || "",
      enable: true,
      auto_update_earliest: Boolean(row.auto_update_earliest ?? false),
      selected: false,
    });
  }
  if (!state.accountRows[key].length) {
    state.accountRows[key].push(defaultAccountRow());
  }
  accountPaginationState(platform, "active").page = 1;
  renderAccountRows(platform);
  renderDeletedRows(platform);
}

function normalizeUrl(url) {
  const value = String(url || "").trim();
  if (!value) {
    return "";
  }
  try {
    const parsed = new URL(value);
    parsed.search = "";
    parsed.hash = "";
    return parsed.toString().replace(/\/$/, "");
  } catch {
    return value.split("?")[0].split("#")[0].replace(/\/$/, "");
  }
}

function formatAccountUrls(platform) {
  const key = accountRowsKey(platform);
  state.accountRows[key] = state.accountRows[key].map((item) => ({
    ...item,
    url: normalizeUrl(item.url),
  }));
  renderAccountRows(platform);
}

function selectedIndexes(platform, section = "active") {
  const key = accountRowsKey(platform);
  const rows = section === "deleted" ? state.deletedRows[key] : state.accountRows[key];
  return rows
    .map((item, index) => ({ selected: Boolean(item.selected), index }))
    .filter((item) => item.selected)
    .map((item) => item.index);
}

function sectionName(section = "active") {
  return section === "deleted" ? "deleted" : "active";
}

function getSelectionAnchor(platform, section = "active") {
  const key = accountRowsKey(platform);
  const sectionKey = sectionName(section);
  const value = state.selectionAnchors[sectionKey]?.[key];
  return Number.isInteger(value) ? value : null;
}

function setSelectionAnchor(platform, section = "active", index = null) {
  const key = accountRowsKey(platform);
  const sectionKey = sectionName(section);
  if (!state.selectionAnchors[sectionKey]) {
    state.selectionAnchors[sectionKey] = {};
  }
  state.selectionAnchors[sectionKey][key] = Number.isInteger(index) ? index : null;
}

function applySelectionRange(platform, section = "active", fromIndex, toIndex, selected = true) {
  const key = accountRowsKey(platform);
  const rows = section === "deleted" ? state.deletedRows[key] : state.accountRows[key];
  if (!rows.length) {
    return;
  }
  const start = Math.max(0, Math.min(rows.length - 1, Math.min(fromIndex, toIndex)));
  const end = Math.max(0, Math.min(rows.length - 1, Math.max(fromIndex, toIndex)));
  for (let index = start; index <= end; index += 1) {
    rows[index].selected = selected;
  }
  if (section === "deleted") {
    renderDeletedRows(platform);
  } else {
    renderAccountRows(platform);
  }
}

function selectAllRows(platform, section = "active", selected = true) {
  const key = accountRowsKey(platform);
  const rows = section === "deleted" ? state.deletedRows[key] : state.accountRows[key];
  if (selected) {
    pagedAccountRows(platform, section).items.forEach(({ index }) => {
      rows[index].selected = true;
    });
  } else {
    rows.forEach((item) => {
      item.selected = false;
    });
  }
  setSelectionAnchor(platform, section, null);
  if (section === "deleted") {
    renderDeletedRows(platform);
  } else {
    renderAccountRows(platform);
  }
}

function openUrls(urls) {
  urls.filter(Boolean).forEach((url) => window.open(url, "_blank", "noopener,noreferrer"));
}

function parseBatchBoolValue(value) {
  return parseBooleanValue(value, null);
}

function batchValuePlaceholder(field) {
  if (field === "enable" || field === "auto_update_earliest") {
    return "批量值：true / false / 启用 / 禁用";
  }
  if (field === "url") {
    return "批量值：账号主页链接";
  }
  if (field === "tab") {
    return "批量值：post / favorite / collection";
  }
  return `批量值：${field}`;
}

function syncBatchValuePlaceholder(platform) {
  const fieldRef =
    platform === "tiktok" ? refs.accountsTikTokBatchField : refs.accountsDouyinBatchField;
  const valueRef =
    platform === "tiktok" ? refs.accountsTikTokBatchValue : refs.accountsDouyinBatchValue;
  if (!fieldRef || !valueRef) {
    return;
  }
  valueRef.placeholder = batchValuePlaceholder(fieldRef.value || "earliest");
}

function applyBatchField(platform, field, rawValue) {
  const key = accountRowsKey(platform);
  const indexes = selectedIndexes(platform, "active");
  if (!indexes.length) {
    return { updated: 0, error: "请先勾选至少一行再批量替换" };
  }
  const editableFields = new Set([
    "mark",
    "url",
    "tab",
    "earliest",
    "latest",
    "enable",
    "auto_update_earliest",
  ]);
  if (!editableFields.has(field)) {
    return { updated: 0, error: `不支持字段: ${field}` };
  }
  let nextValue = rawValue;
  if (field === "enable" || field === "auto_update_earliest") {
    const parsed = parseBatchBoolValue(rawValue);
    if (parsed === null) {
      return {
        updated: 0,
        error: `${field} 只支持 true/false/1/0/启用/禁用`,
      };
    }
    nextValue = parsed;
  }
  indexes.forEach((index) => {
    const row = state.accountRows[key][index];
    if (!row) {
      return;
    }
    row[field] =
      field === "enable" || field === "auto_update_earliest"
        ? Boolean(nextValue)
        : String(nextValue ?? "");
  });
  renderAccountRows(platform);
  return { updated: indexes.length, field };
}

function collectAccountRows(platform) {
  const key = accountRowsKey(platform);
  return state.accountRows[key].map((item) => ({
    mark: String(item.mark || "").trim(),
    url: String(item.url || "").trim(),
    tab: String(item.tab || "post").trim() || "post",
    earliest: String(item.earliest || "").trim(),
    latest: String(item.latest || "").trim(),
    enable: Boolean(item.enable),
    auto_update_earliest: Boolean(item.auto_update_earliest),
  }));
}

function collectDeletedRows(platform) {
  const key = accountRowsKey(platform);
  return state.deletedRows[key].map((item) => ({
    mark: String(item.mark || "").trim(),
    url: String(item.url || "").trim(),
    tab: String(item.tab || "post").trim() || "post",
    earliest: String(item.earliest || "").trim(),
    latest: String(item.latest || "").trim(),
    enable: false,
    auto_update_earliest: Boolean(item.auto_update_earliest),
    deleted_at: String(item.deleted_at || "").trim(),
    reason: String(item.reason || "").trim(),
  }));
}

function setAccountsIoStatus(text) {
  if (!refs.accountsIoStatus) {
    return;
  }
  refs.accountsIoStatus.textContent = text;
}

function toggleAccountsSettings(forceCollapsed = null) {
  const block = refs.accountsSettingsBlock;
  if (!block) {
    return;
  }
  const nextCollapsed =
    typeof forceCollapsed === "boolean"
      ? forceCollapsed
      : !block.classList.contains("collapsed");
  block.classList.toggle("collapsed", nextCollapsed);
  if (refs.accountsToggleBtn) {
    refs.accountsToggleBtn.textContent = nextCollapsed ? "展开配置" : "收起配置";
  }
  try {
    localStorage.setItem(
      ACCOUNTS_COLLAPSE_STORAGE_KEY,
      nextCollapsed ? "1" : "0",
    );
  } catch {}
}

function accountExportPayload() {
  return {
    version: 1,
    generated_at: new Date().toISOString(),
    accounts_urls: collectAccountRows("douyin"),
    accounts_urls_tiktok: collectAccountRows("tiktok"),
    deleted_accounts: collectDeletedRows("douyin"),
    deleted_accounts_tiktok: collectDeletedRows("tiktok"),
  };
}

function exportAccountsJson() {
  const payload = accountExportPayload();
  const now = new Date();
  const pad = (value) => String(value).padStart(2, "0");
  const suffix = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}_${pad(
    now.getHours(),
  )}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
  const filename = `accounts_urls_${suffix}.json`;
  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: "application/json;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  setAccountsIoStatus(
    `已导出 JSON：抖音 ${payload.accounts_urls.length} 条，TikTok ${payload.accounts_urls_tiktok.length} 条，删除区 ${
      payload.deleted_accounts.length + payload.deleted_accounts_tiktok.length
    } 条`,
  );
}

function parseImportedAccountPayload(parsed) {
  if (Array.isArray(parsed)) {
    return {
      accounts_urls: parsed,
      accounts_urls_tiktok: [],
      deleted_accounts: [],
      deleted_accounts_tiktok: [],
    };
  }
  if (!parsed || typeof parsed !== "object") {
    throw new Error("JSON 根节点必须为对象或数组");
  }
  const accountsDouyin =
    parsed.accounts_urls ??
    parsed.douyin ??
    parsed.douyin_accounts ??
    parsed.douyin_accounts_urls ??
    [];
  const accountsTikTok =
    parsed.accounts_urls_tiktok ??
    parsed.tiktok ??
    parsed.tiktok_accounts ??
    parsed.tiktok_accounts_urls ??
    [];
  if (!Array.isArray(accountsDouyin) || !Array.isArray(accountsTikTok)) {
    throw new Error("accounts_urls / accounts_urls_tiktok 必须是数组");
  }
  return {
    accounts_urls: accountsDouyin,
    accounts_urls_tiktok: accountsTikTok,
    deleted_accounts: parsed.deleted_accounts ?? [],
    deleted_accounts_tiktok: parsed.deleted_accounts_tiktok ?? [],
  };
}

async function importAccountsJsonFile(file) {
  if (!file) {
    return;
  }
  setAccountsIoStatus(`正在导入：${file.name}`);
  try {
    const text = await file.text();
    const parsed = JSON.parse(text);
    const extracted = parseImportedAccountPayload(parsed);
    setAccountRows("douyin", extracted.accounts_urls);
    setAccountRows("tiktok", extracted.accounts_urls_tiktok);
    setDeletedRows("douyin", extracted.deleted_accounts);
    setDeletedRows("tiktok", extracted.deleted_accounts_tiktok);
    setAccountsIoStatus(
      `导入成功：抖音 ${collectAccountRows("douyin").length} 条，TikTok ${collectAccountRows("tiktok").length} 条，删除区 ${
        collectDeletedRows("douyin").length + collectDeletedRows("tiktok").length
      } 条（记得点“保存配置”）`,
    );
    setApiStatus("就绪", "ok");
  } catch (error) {
    setAccountsIoStatus(`导入失败: ${error.message}`);
    setApiStatus(`异常: ${error.message}`, "error");
  }
}

function mapSettingsToForm(settings) {
  state.settingsData = settings && typeof settings === "object" ? settings : {};
  const fields = [
    "root",
    "folder_name",
    "profile_avatar_folder",
    "earliest_update_days",
    "request_delay",
    "storage_format",
    "proxy",
    "proxy_tiktok",
    "run_command",
  ];
  for (const name of fields) {
    const element = refs.settingsForm.elements.namedItem(name);
    if (!element) {
      continue;
    }
    element.value = settings?.[name] ?? "";
  }

  const boolFields = [
    "download",
    "folder_mode",
    "music",
    "dynamic_cover",
    "static_cover",
    "auto_backfill_mark",
    "tiktok_bridge_fallback_enabled",
  ];
  for (const name of boolFields) {
    const element = refs.settingsForm.elements.namedItem(name);
    if (!element) {
      continue;
    }
    element.checked = Boolean(settings?.[name]);
  }

  setAccountRows("douyin", settings?.accounts_urls || []);
  setAccountRows("tiktok", settings?.accounts_urls_tiktok || []);
  setDeletedRows("douyin", settings?.deleted_accounts || []);
  setDeletedRows("tiktok", settings?.deleted_accounts_tiktok || []);
  syncQuickAuthEditors(settings);
}

function collectSettingsPayload() {
  const formData = new FormData(refs.settingsForm);
  const rawDays = Number(formData.get("earliest_update_days"));
  const earliestUpdateDays = Number.isFinite(rawDays) ? Math.max(0, Math.trunc(rawDays)) : 0;
  const rawRequestDelay = Number(formData.get("request_delay"));
  const requestDelay = Number.isFinite(rawRequestDelay) ? Math.max(0, rawRequestDelay) : 6;
  const payload = {
    root: String(formData.get("root") || "").trim(),
    folder_name: String(formData.get("folder_name") || "").trim(),
    profile_avatar_folder: String(formData.get("profile_avatar_folder") || "").trim(),
    earliest_update_days: earliestUpdateDays,
    request_delay: requestDelay,
    storage_format: String(formData.get("storage_format") || "").trim(),
    proxy: String(formData.get("proxy") || "").trim(),
    proxy_tiktok: String(formData.get("proxy_tiktok") || "").trim(),
    run_command: String(formData.get("run_command") || "").trim(),
    download: refs.settingsForm.elements.namedItem("download").checked,
    folder_mode: refs.settingsForm.elements.namedItem("folder_mode").checked,
    music: refs.settingsForm.elements.namedItem("music").checked,
    dynamic_cover: refs.settingsForm.elements.namedItem("dynamic_cover").checked,
    static_cover: refs.settingsForm.elements.namedItem("static_cover").checked,
    auto_backfill_mark: refs.settingsForm.elements.namedItem("auto_backfill_mark").checked,
    tiktok_bridge_fallback_enabled: refs.settingsForm.elements.namedItem(
      "tiktok_bridge_fallback_enabled",
    ).checked,
    accounts_urls: collectAccountRows("douyin"),
    accounts_urls_tiktok: collectAccountRows("tiktok"),
    deleted_accounts: collectDeletedRows("douyin"),
    deleted_accounts_tiktok: collectDeletedRows("tiktok"),
    ui_schedules: state.settingsData?.ui_schedules || [],
  };
  return payload;
}

async function loadSettings() {
  refs.settingsStatus.textContent = "正在加载配置…";
  try {
    const settings = await fetchJson("/settings", {
      method: "GET",
      headers: headerOptions(false),
    });
    mapSettingsToForm(settings);
    refs.settingsStatus.textContent = "配置已加载";
    setApiStatus("就绪", "ok");
  } catch (error) {
    refs.settingsStatus.textContent = `加载失败: ${error.message}`;
    setApiStatus(`异常: ${error.message}`, "error");
  }
}

async function saveSettings() {
  refs.settingsStatus.textContent = "正在保存配置…";
  try {
    const payload = collectSettingsPayload();
    const settings = await fetchJson("/settings", {
      method: "POST",
      headers: headerOptions(true),
      body: JSON.stringify(payload),
    });
    mapSettingsToForm(settings);
    refs.settingsStatus.textContent = "保存成功";
    setApiStatus("就绪", "ok");
  } catch (error) {
    refs.settingsStatus.textContent = `保存失败: ${error.message}`;
    setApiStatus(`异常: ${error.message}`, "error");
  }
}

function accountStatusRef(platform) {
  return platform === "tiktok" ? refs.accountsTikTokStatus : refs.accountsDouyinStatus;
}

function accountVerifyIdentityRef(platform) {
  return platform === "tiktok" ? refs.accountsTikTokIdentity : refs.accountsDouyinIdentity;
}

function accountVerifyIdentityHelpRef(platform) {
  return platform === "tiktok"
    ? refs.accountsTikTokIdentityHelp
    : refs.accountsDouyinIdentityHelp;
}

function syncAccountVerifyIdentityHelp(platform) {
  const select = accountVerifyIdentityRef(platform);
  const help = accountVerifyIdentityHelpRef(platform);
  const platformLabel = workflowPlatformLabel(platform);
  if (!select || !help) {
    return;
  }
  delete help.dataset.state;
  const identityId = select.value || "";
  const identity = collectorIdentityById(identityId);
  if (!identityId) {
    help.textContent = `自动路由会按 ${platformLabel} 身份池策略逐个检测账号。`;
    return;
  }
  if (!collectorIdentityIsRoutable(identity)) {
    help.textContent = "当前选中的身份已不可路由，请改用自动路由或选择其他身份。";
    help.dataset.state = "warning";
    return;
  }
  help.textContent = `本次账号有效性检测固定使用“${identity.name}”。`;
}

function setAccountStatus(platform, text) {
  const element = accountStatusRef(platform);
  if (element) {
    element.textContent = text;
  }
}

async function persistAccountTables(reason = "accounts_batch_edit") {
  const payload = {
    accounts_urls: collectAccountRows("douyin"),
    accounts_urls_tiktok: collectAccountRows("tiktok"),
    deleted_accounts: collectDeletedRows("douyin"),
    deleted_accounts_tiktok: collectDeletedRows("tiktok"),
    backup: true,
    reason,
  };
  const result = await fetchJson("/ui/api/accounts", {
    method: "PUT",
    headers: headerOptions(true),
    body: JSON.stringify(payload),
  });
  setAccountRows("douyin", result.accounts_urls || payload.accounts_urls);
  setAccountRows("tiktok", result.accounts_urls_tiktok || payload.accounts_urls_tiktok);
  setDeletedRows("douyin", result.deleted_accounts || payload.deleted_accounts);
  setDeletedRows("tiktok", result.deleted_accounts_tiktok || payload.deleted_accounts_tiktok);
  return result;
}

function closeDeletedAccountsDialog({ restoreFocus = true } = {}) {
  if (refs.deletedAccountsDialog?.open) {
    refs.deletedAccountsDialog.close();
  }
  const focusTarget = state.deletedPurge.restoreFocus;
  state.deletedPurge = {
    platform: "",
    mode: "",
    restoreFocus: null,
  };
  if (restoreFocus && focusTarget instanceof HTMLElement && focusTarget.isConnected) {
    focusTarget.focus();
  }
}

function openDeletedAccountsDialog(platform, mode, trigger) {
  const key = accountRowsKey(platform);
  const count =
    mode === "selected"
      ? selectedIndexes(platform, "deleted").length
      : state.deletedRows[key].length;
  if (!count) {
    setAccountStatus(
      platform,
      mode === "selected" ? "请先勾选需要永久移除的记录" : "回收站已经为空",
    );
    return;
  }
  const platformLabel = platform === "tiktok" ? "TikTok" : "抖音";
  state.deletedPurge = {
    platform,
    mode,
    restoreFocus: trigger instanceof HTMLElement ? trigger : null,
  };
  refs.deletedAccountsDialogTitle.textContent =
    mode === "selected" ? `永久移除所选 ${platformLabel} 记录` : `清空 ${platformLabel} 回收站`;
  refs.deletedAccountsDialogSummary.textContent = `将永久移除 ${count.toLocaleString(
    "zh-CN",
  )} 条 Deleted Accounts 记录`;
  refs.deletedAccountsDialogStatus.textContent =
    "只清理配置记录；已下载媒体、账户目录和作品记录不会被删除。";
  refs.deletedAccountsDialogConfirmBtn.disabled = false;
  refs.deletedAccountsDialog.showModal();
  refreshIcons(refs.deletedAccountsDialog);
  refs.deletedAccountsDialogConfirmBtn.focus();
}

async function confirmDeletedAccountsPurge() {
  const { platform, mode } = state.deletedPurge;
  if (!platform || !mode) {
    return;
  }
  const key = accountRowsKey(platform);
  const previous = state.deletedRows[key].map((item) => ({ ...item }));
  const indexes =
    mode === "selected"
      ? selectedIndexes(platform, "deleted").sort((a, b) => b - a)
      : state.deletedRows[key].map((_, index) => index).sort((a, b) => b - a);
  if (!indexes.length) {
    refs.deletedAccountsDialogStatus.textContent = "没有可移除的记录";
    return;
  }
  refs.deletedAccountsDialogStatus.textContent = "正在备份配置并清理回收站…";
  refs.deletedAccountsDialogConfirmBtn.disabled = true;
  try {
    indexes.forEach((index) => state.deletedRows[key].splice(index, 1));
    const result = await persistAccountTables(
      mode === "selected" ? "account_deleted_purge_selected" : "account_deleted_purge_all",
    );
    closeDeletedAccountsDialog({ restoreFocus: false });
    setAccountStatus(
      platform,
      `已永久移除 ${indexes.length} 条回收记录；配置备份: ${result.backup_path || "-"}`,
    );
    setApiStatus("就绪", "ok");
  } catch (error) {
    state.deletedRows[key] = previous;
    renderDeletedRows(platform);
    refs.deletedAccountsDialogStatus.textContent = `清理失败: ${error.message}`;
    refs.deletedAccountsDialogConfirmBtn.disabled = false;
    setApiStatus(`异常: ${error.message}`, "error");
  }
}

async function verifyAccounts(platform) {
  const identitySelect = accountVerifyIdentityRef(platform);
  if (!selectedCollectorIdentityIsRunnable(identitySelect)) {
    setAccountStatus(platform, "当前选中的身份已不可路由，请改用自动路由或选择其他身份");
    identitySelect.focus();
    return;
  }
  setAccountStatus(platform, "正在检测账号有效性…");
  try {
    await persistAccountTables("pre_verify_sync");
    const payload = {
      platform,
      use_settings: true,
      move_deleted: true,
      identity_id: identitySelect.value || "",
    };
    const result = await fetchJson("/ui/api/accounts/verify", {
      method: "POST",
      headers: headerOptions(true),
      body: JSON.stringify(payload),
    });
    if (platform === "tiktok") {
      setAccountRows("tiktok", result.accounts || []);
      setDeletedRows("tiktok", result.deleted_accounts || []);
    } else {
      setAccountRows("douyin", result.accounts || []);
      setDeletedRows("douyin", result.deleted_accounts || []);
    }
    setAccountStatus(
      platform,
      `检测完成：${result.checked} 条，存在 ${result.exists}，失效 ${result.missing}，转移 ${result.moved_to_deleted}`,
    );
    setApiStatus("就绪", "ok");
  } catch (error) {
    setAccountStatus(platform, `检测失败: ${error.message}`);
    setApiStatus(`异常: ${error.message}`, "error");
  }
}

const REDACTED_SENTINEL = "[REDACTED]";
const RAW_ACCOUNT_KEYS = new Set([
  "accounts_urls",
  "accounts_urls_tiktok",
  "deleted_accounts",
  "deleted_accounts_tiktok",
]);
const RAW_AUTH_KEYS = new Set([
  "cookie",
  "cookie_tiktok",
  "proxy",
  "proxy_tiktok",
  "browser_info",
  "browser_info_tiktok",
]);

function filterRawSettingsScope(settings, scope = "core") {
  const source = cloneSettingsObject(settings);
  if (scope === "full") {
    return source;
  }
  if (scope === "auth") {
    return Object.fromEntries(
      Object.entries(source).filter(([key]) => RAW_AUTH_KEYS.has(key)),
    );
  }
  if (scope === "automation") {
    return Object.fromEntries(
      Object.entries(source).filter(([key]) => {
        const normalized = key.toLowerCase();
        return (
          normalized.includes("schedule") ||
          normalized.includes("monitor") ||
          normalized.includes("collect") ||
          normalized.includes("backfill")
        );
      }),
    );
  }
  return Object.fromEntries(
    Object.entries(source).filter(([key]) => !RAW_ACCOUNT_KEYS.has(key)),
  );
}

function updateRawEditorMeta() {
  const text = String(refs.settingsRawEditor?.value || "");
  const lines = text ? text.split("\n").length : 0;
  let validation = "JSON 有效";
  let stateName = "success";
  try {
    const parsed = JSON.parse(text || "{}");
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new Error("根节点必须是对象");
    }
  } catch (error) {
    validation = `JSON 无效：${error.message}`;
    stateName = "error";
  }
  const scopeLabel = refs.settingsRawScope?.selectedOptions?.[0]?.textContent || "当前范围";
  refs.settingsRawMeta.textContent = `${scopeLabel} · ${lines} 行 · ${text.length.toLocaleString(
    "zh-CN",
  )} 字符 · ${validation}`;
  refs.settingsRawMeta.dataset.state = stateName;
}

function renderRawSettingsSource() {
  const scope = refs.settingsRawScope?.value || "core";
  const filtered = filterRawSettingsScope(state.rawSettingsSource, scope);
  refs.settingsRawEditor.value = JSON.stringify(filtered, null, 2);
  updateRawEditorMeta();
}

async function loadRawSettings() {
  let includeSecrets = Boolean(refs.settingsRawIncludeSecrets?.checked);
  if (
    includeSecrets &&
    !window.confirm(
      "敏感值会以明文显示在浏览器中。请确认当前屏幕和设备环境安全，是否继续？",
    )
  ) {
    includeSecrets = false;
    refs.settingsRawIncludeSecrets.checked = false;
  }
  refs.settingsRawStatus.textContent = includeSecrets
    ? "正在安全读取完整 settings.json…"
    : "正在读取 settings.json（敏感值隐藏）…";
  try {
    const query = new URLSearchParams({
      include_secrets: String(includeSecrets),
    });
    const payload = await fetchJson(`/ui/api/settings/raw?${query.toString()}`, {
      method: "GET",
      headers: headerOptions(false),
    });
    state.rawSettingsSecretsIncluded = Boolean(payload?.secrets_included);
    try {
      const parsed = JSON.parse(String(payload?.text || "{}"));
      state.rawSettingsSource = cloneSettingsObject(parsed);
      syncQuickAuthEditors(parsed);
      renderRawSettingsSource();
    } catch (error) {
      state.rawSettingsSource = {};
      refs.settingsRawEditor.value = String(payload?.text || "");
      syncQuickAuthEditors(state.settingsData);
      updateRawEditorMeta();
      throw new Error(`配置解析失败: ${error.message}`);
    }
    refs.settingsRawStatus.textContent = `${
      state.rawSettingsSecretsIncluded ? "已加载完整原文（含敏感值）" : "已加载安全原文（敏感值隐藏）"
    } · ${payload?.updated_at || ""}`;
    setApiStatus("就绪", "ok");
  } catch (error) {
    refs.settingsRawStatus.textContent = `读取失败: ${error.message}`;
    setApiStatus(`异常: ${error.message}`, "error");
  }
}

function stringifySettingValue(value) {
  if (typeof value === "string") {
    return value;
  }
  if (value && typeof value === "object") {
    return JSON.stringify(value, null, 2);
  }
  return "";
}

function cloneSettingsObject(value) {
  if (!value || typeof value !== "object") {
    return {};
  }
  return JSON.parse(JSON.stringify(value));
}

function syncQuickAuthEditors(settings = state.settingsData) {
  const next = settings && typeof settings === "object" ? settings : {};
  const syncSecretField = (element, value) => {
    const normalized = stringifySettingValue(value);
    const hidden = normalized === REDACTED_SENTINEL || normalized.includes(REDACTED_SENTINEL);
    element.value = hidden ? "" : normalized;
    element.dataset.secretConfigured = String(hidden || Boolean(normalized));
    element.placeholder = hidden ? "已配置（敏感值隐藏；留空将保留）" : element.dataset.defaultPlaceholder || "";
  };
  for (const element of [
    refs.settingsAuthCookieDouyin,
    refs.settingsAuthCookieTikTok,
    refs.settingsAuthTikTokDeviceId,
    refs.settingsAuthTikTokUserAgent,
  ]) {
    if (!element.dataset.defaultPlaceholder) {
      element.dataset.defaultPlaceholder = element.placeholder || "";
    }
  }
  syncSecretField(refs.settingsAuthCookieDouyin, next.cookie);
  syncSecretField(refs.settingsAuthCookieTikTok, next.cookie_tiktok);
  syncSecretField(refs.settingsAuthTikTokDeviceId, next?.browser_info_tiktok?.device_id);
  syncSecretField(refs.settingsAuthTikTokUserAgent, next?.browser_info_tiktok?.["User-Agent"]);
  refs.settingsAuthStatus.textContent = state.rawSettingsSecretsIncluded
    ? "已载入当前登录信息；敏感值正在明文显示"
    : "已配置的敏感值保持隐藏；留空保存不会覆盖";
}

function resolveSettingsEditorBase() {
  const rawText = String(refs.settingsRawEditor.value || "").trim();
  if (rawText) {
    const parsed = JSON.parse(rawText);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed;
    }
  }
  return cloneSettingsObject(state.settingsData);
}

function applyQuickAuthEditorsToSettings(base) {
  const next = cloneSettingsObject(base);
  const cookieDouyin = refs.settingsAuthCookieDouyin.value.trim();
  const cookieTikTok = refs.settingsAuthCookieTikTok.value.trim();
  if (cookieDouyin) {
    next.cookie = cookieDouyin;
  }
  if (cookieTikTok) {
    next.cookie_tiktok = cookieTikTok;
  }
  const browserInfoTikTok =
    next.browser_info_tiktok && typeof next.browser_info_tiktok === "object"
      ? cloneSettingsObject(next.browser_info_tiktok)
      : {};
  const deviceId = refs.settingsAuthTikTokDeviceId.value.trim();
  const userAgent = refs.settingsAuthTikTokUserAgent.value.trim();
  if (deviceId) {
    browserInfoTikTok.device_id = deviceId;
  }
  if (userAgent) {
    browserInfoTikTok["User-Agent"] = userAgent;
  }
  if (Object.keys(browserInfoTikTok).length) {
    next.browser_info_tiktok = browserInfoTikTok;
  }
  return next;
}

function applyQuickAuthEditorsToRaw() {
  refs.settingsAuthStatus.textContent = "正在写入原文编辑器…";
  try {
    const next = applyQuickAuthEditorsToSettings(resolveSettingsEditorBase());
    refs.settingsRawEditor.value = JSON.stringify(next, null, 2);
    updateRawEditorMeta();
    refs.settingsAuthStatus.textContent = "已写入原文编辑器，可继续检查后保存";
    refs.settingsRawStatus.textContent = "快捷登录信息已同步到原文编辑器";
  } catch (error) {
    refs.settingsAuthStatus.textContent = `写入失败: ${error.message}`;
  }
}

async function saveQuickAuthSettings() {
  refs.settingsAuthStatus.textContent = "正在保存登录信息…";
  try {
    const next = applyQuickAuthEditorsToSettings(resolveSettingsEditorBase());
    refs.settingsRawEditor.value = JSON.stringify(next, null, 2);
    updateRawEditorMeta();
    const payload = await fetchJson("/ui/api/settings/raw", {
      method: "PUT",
      headers: headerOptions(true),
      body: JSON.stringify({
        text: refs.settingsRawEditor.value,
      }),
    });
    refs.settingsAuthStatus.textContent = payload?.message || "登录信息保存成功";
    refs.settingsRawStatus.textContent = payload?.message || "登录信息保存成功";
    if (payload?.settings) {
      mapSettingsToForm(payload.settings);
    } else {
      await loadSettings();
    }
    setApiStatus("就绪", "ok");
  } catch (error) {
    refs.settingsAuthStatus.textContent = `保存失败: ${error.message}`;
    setApiStatus(`异常: ${error.message}`, "error");
  }
}

function formatRawSettings() {
  try {
    const parsed = JSON.parse(refs.settingsRawEditor.value || "{}");
    refs.settingsRawEditor.value = JSON.stringify(parsed, null, 2);
    updateRawEditorMeta();
    refs.settingsRawStatus.textContent = "JSON 格式化完成";
  } catch (error) {
    refs.settingsRawStatus.textContent = `格式化失败: ${error.message}`;
  }
}

async function saveRawSettings() {
  refs.settingsRawStatus.textContent = "正在保存 settings.json 原文…";
  try {
    const text = refs.settingsRawEditor.value || "{}";
    const payload = await fetchJson("/ui/api/settings/raw", {
      method: "PUT",
      headers: headerOptions(true),
      body: JSON.stringify({ text }),
    });
    refs.settingsRawStatus.textContent = payload?.message || "保存成功";
    if (payload?.settings) {
      mapSettingsToForm(payload.settings);
    } else {
      await loadSettings();
    }
    state.rawSettingsSource = cloneSettingsObject({
      ...state.rawSettingsSource,
      ...JSON.parse(text),
    });
    updateRawEditorMeta();
    setApiStatus("就绪", "ok");
  } catch (error) {
    refs.settingsRawStatus.textContent = `保存失败: ${error.message}`;
    setApiStatus(`异常: ${error.message}`, "error");
  }
}

function searchRawSettings() {
  const query = String(refs.settingsRawSearch?.value || "");
  if (!query) {
    refs.settingsRawSearch?.focus();
    return;
  }
  const text = refs.settingsRawEditor.value || "";
  const startAt = Number(refs.settingsRawEditor.dataset.searchIndex || 0);
  let index = text.toLowerCase().indexOf(query.toLowerCase(), startAt);
  if (index < 0 && startAt > 0) {
    index = text.toLowerCase().indexOf(query.toLowerCase());
  }
  if (index < 0) {
    refs.settingsRawStatus.textContent = `未找到：${query}`;
    return;
  }
  refs.settingsRawEditor.focus();
  refs.settingsRawEditor.setSelectionRange(index, index + query.length);
  refs.settingsRawEditor.dataset.searchIndex = String(index + query.length);
  const line = text.slice(0, index).split("\n").length;
  const lineHeight = Number.parseFloat(getComputedStyle(refs.settingsRawEditor).lineHeight) || 20;
  refs.settingsRawEditor.scrollTop = Math.max(0, (line - 3) * lineHeight);
  refs.settingsRawStatus.textContent = `已定位到第 ${line} 行`;
}

function toggleRawEditorWrap() {
  const wrapped = refs.settingsRawEditor.wrap === "soft";
  refs.settingsRawEditor.wrap = wrapped ? "off" : "soft";
  refs.settingsRawWrapBtn.setAttribute("aria-pressed", String(!wrapped));
  refs.settingsRawWrapBtn.textContent = wrapped ? "自动换行" : "取消换行";
}

function normalizeEntries(payload) {
  if (!payload) {
    return { entries: [], currentPath: "", parentPath: "", total: 0 };
  }
  if (Array.isArray(payload)) {
    return {
      entries: payload,
      currentPath: state.currentPath,
      parentPath: parentPath(state.currentPath),
      total: payload.length,
    };
  }
  return {
    entries: payload.entries || payload.items || payload.data || [],
    currentPath: payload.current_path ?? payload.path ?? state.currentPath,
    parentPath: payload.parent ?? parentPath(payload.current_path ?? payload.path ?? state.currentPath),
    total:
      payload.total ??
      payload.count ??
      (payload.entries || payload.items || payload.data || []).length,
    page: Number(payload.page || 1),
    pageSize: Number(payload.page_size || state.filePageSize),
    pages: Number(payload.pages || 1),
  };
}

function isDirectoryEntry(entry) {
  return Boolean(entry?.is_dir || entry?.kind === "dir");
}

function iconForEntry(entry) {
  if (isDirectoryEntry(entry)) {
    return "folder";
  }
  if (entry.kind === "image") {
    return "file-image";
  }
  if (entry.kind === "video") {
    return "file-video";
  }
  if (entry.kind === "audio") {
    return "file-audio";
  }
  if (entry.kind === "text") {
    return "file-text";
  }
  return "file";
}

function kindLabel(entry) {
  const labels = {
    dir: "文件夹",
    image: "图片",
    video: "视频",
    audio: "音频",
    text: "文本",
    file: "文件",
  };
  const kind = isDirectoryEntry(entry) ? "dir" : entry?.kind || "file";
  return labels[kind] || "文件";
}

function formatFileSize(value) {
  const size = Number(value);
  if (!Number.isFinite(size) || size < 0) {
    return "—";
  }
  if (size < 1024) {
    return `${size} B`;
  }
  const units = ["KB", "MB", "GB", "TB"];
  let normalized = size / 1024;
  let unit = units[0];
  for (const nextUnit of units.slice(1)) {
    if (normalized < 1024) {
      break;
    }
    normalized /= 1024;
    unit = nextUnit;
  }
  return `${normalized >= 10 ? normalized.toFixed(1) : normalized.toFixed(2)} ${unit}`;
}

function formatFileDate(value) {
  if (!value) {
    return "—";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return String(value);
  }
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
}

function fileAccessUrl(path) {
  return `/ui/api/file?scope=${encodeURIComponent(state.currentScope)}&path=${encodeURIComponent(
    path || "",
  )}`;
}

function fileLightboxEntries() {
  return filteredFileEntries().filter(
    (entry) =>
      !isDirectoryEntry(entry) &&
      (entry.kind === "image" || entry.kind === "video"),
  );
}

function stopFileLightboxMedia() {
  const video = refs.fileLightboxStage?.querySelector("video");
  if (video instanceof HTMLVideoElement) {
    video.pause();
  }
}

function renderFileLightbox() {
  const entries = fileLightboxEntries();
  const entry = entries[state.fileLightboxIndex];
  if (!entry || !refs.fileLightboxStage) {
    closeFileLightbox();
    return;
  }

  stopFileLightboxMedia();
  refs.fileLightboxStage.innerHTML = "";
  refs.fileLightboxTitle.textContent = entry.name || entry.path || "媒体预览";
  refs.fileLightboxMeta.textContent = [
    kindLabel(entry),
    formatFileSize(entry.size),
    formatFileDate(entry.modified_at),
  ].join(" · ");
  refs.fileLightboxPosition.textContent = `${state.fileLightboxIndex + 1} / ${entries.length}`;
  refs.fileLightboxOpenLink.href = fileAccessUrl(entry.path);
  refs.fileLightboxOpenLink.removeAttribute("aria-disabled");
  refs.fileLightboxPrevBtn.disabled = state.fileLightboxIndex <= 0;
  refs.fileLightboxNextBtn.disabled = state.fileLightboxIndex >= entries.length - 1;

  const fileUrl = fileAccessUrl(entry.path);
  if (entry.kind === "image") {
    const image = document.createElement("img");
    image.src = fileUrl;
    image.alt = entry.name || "放大图片";
    image.decoding = "async";
    refs.fileLightboxStage.appendChild(image);
  } else {
    const video = document.createElement("video");
    video.src = fileUrl;
    video.controls = true;
    video.preload = "metadata";
    video.playsInline = true;
    video.setAttribute("aria-label", entry.name || "放大视频");
    refs.fileLightboxStage.appendChild(video);
  }
}

function openFileLightbox(entry, restoreFocus = document.activeElement) {
  if (!entry || !["image", "video"].includes(entry.kind)) {
    return;
  }
  const entries = fileLightboxEntries();
  const index = entries.findIndex((item) => item.path === entry.path);
  if (index < 0) {
    return;
  }
  state.fileLightboxIndex = index;
  state.fileLightboxRestoreFocus =
    restoreFocus instanceof HTMLElement ? restoreFocus : null;
  renderFileLightbox();
  if (!refs.fileLightbox.open) {
    refs.fileLightbox.showModal();
  }
  refs.fileLightboxCloseBtn.focus();
}

function closeFileLightbox({ restoreFocus = true } = {}) {
  stopFileLightboxMedia();
  if (refs.fileLightbox?.open) {
    refs.fileLightbox.close();
  }
  const focusTarget = state.fileLightboxRestoreFocus;
  state.fileLightboxIndex = -1;
  state.fileLightboxRestoreFocus = null;
  if (restoreFocus && focusTarget?.isConnected) {
    focusTarget.focus();
  }
}

function moveFileLightbox(direction) {
  const entries = fileLightboxEntries();
  const nextIndex = Math.max(
    0,
    Math.min(entries.length - 1, state.fileLightboxIndex + direction),
  );
  if (nextIndex === state.fileLightboxIndex) {
    return;
  }
  state.fileLightboxIndex = nextIndex;
  renderFileLightbox();
}

function updateFileMasonryLayout() {
  state.fileMasonryFrame = 0;
  if (!refs.filesList || !refs.filesList.classList.contains("file-masonry")) {
    return;
  }
  const listStyle = window.getComputedStyle(refs.filesList);
  if (listStyle.display !== "grid") {
    return;
  }
  const rowHeight = Number.parseFloat(listStyle.gridAutoRows) || 8;
  const rowGap = Number.parseFloat(listStyle.rowGap) || 10;
  const cards = Array.from(refs.filesList.querySelectorAll(".file-card"));
  for (const card of cards) {
    card.style.gridRowEnd = "auto";
  }
  const heights = cards.map((card) => card.getBoundingClientRect().height);
  cards.forEach((card, index) => {
    const span = Math.max(
      1,
      Math.ceil((heights[index] + rowGap) / (rowHeight + rowGap)),
    );
    card.style.gridRowEnd = `span ${span}`;
  });
}

function scheduleFileMasonryLayout() {
  if (state.fileMasonryFrame) {
    window.cancelAnimationFrame(state.fileMasonryFrame);
  }
  state.fileMasonryFrame = window.requestAnimationFrame(updateFileMasonryLayout);
}

function observeFileMasonryCards() {
  state.fileMasonryObserver?.disconnect();
  state.fileMasonryObserver = null;
  const cards = refs.filesList?.querySelectorAll(".file-card") || [];
  if ("ResizeObserver" in window) {
    state.fileMasonryObserver = new ResizeObserver(() => {
      scheduleFileMasonryLayout();
    });
    cards.forEach((card) => state.fileMasonryObserver.observe(card));
  }
  scheduleFileMasonryLayout();
}

function resetFilePreview(title = "选择一个文件", description = "图片、视频、音频和文本会在这里预览") {
  state.filePreviewRequestId += 1;
  refs.filePreview.innerHTML = "";
  const empty = document.createElement("div");
  empty.className = "file-preview-empty";
  const heading = document.createElement("strong");
  heading.textContent = title;
  const copy = document.createElement("span");
  copy.textContent = description;
  empty.appendChild(heading);
  empty.appendChild(copy);
  refs.filePreview.appendChild(empty);
}

function renderCurrentDirectoryOverview() {
  const folderLabel = state.currentPath ? state.currentPath.split("/").filter(Boolean).at(-1) : (
    state.currentScope === "download" ? "下载目录" : "项目目录"
  );
  const filteredCount = filteredFileEntries().length;
  resetFilePreview(
    folderLabel || "根目录",
    state.fileSearch.trim()
      ? `搜索到 ${state.fileTotal} 个项目，当前显示 ${filteredCount} 个`
      : `当前目录共有 ${state.fileTotal} 个项目；点击文件夹直接进入`,
  );
}

function appendPreviewHeader(entry) {
  const header = document.createElement("div");
  header.className = "file-preview-header";

  const copy = document.createElement("div");
  copy.className = "file-preview-title";
  const title = document.createElement("h3");
  title.textContent = entry.name || entry.path || "(未命名)";
  const meta = document.createElement("div");
  meta.className = "file-preview-meta";
  for (const text of [
    kindLabel(entry),
    isDirectoryEntry(entry) ? null : formatFileSize(entry.size),
    formatFileDate(entry.modified_at),
  ].filter(Boolean)) {
    const item = document.createElement("span");
    item.textContent = text;
    meta.appendChild(item);
  }
  copy.appendChild(title);
  copy.appendChild(meta);

  const actions = document.createElement("div");
  actions.className = "file-preview-actions";
  header.appendChild(copy);
  header.appendChild(actions);
  refs.filePreview.appendChild(header);
  return actions;
}

function renderFilePreview(entry) {
  const requestId = ++state.filePreviewRequestId;
  refs.filePreview.innerHTML = "";
  const actions = appendPreviewHeader(entry);

  if (isDirectoryEntry(entry)) {
    const openButton = document.createElement("button");
    openButton.className = "btn primary";
    openButton.type = "button";
    openButton.textContent = "打开文件夹";
    openButton.addEventListener("click", () => {
      navigateToFilePath(entry.path || "", { focusAfterLoad: true });
    });
    actions.appendChild(openButton);

    const folderSummary = document.createElement("div");
    folderSummary.className = "file-preview-empty file-preview-folder";
    const heading = document.createElement("strong");
    heading.textContent = "文件夹已选择";
    const copy = document.createElement("span");
    copy.textContent = "双击左侧文件夹、按 Enter，或点击“打开文件夹”进入。";
    folderSummary.appendChild(heading);
    folderSummary.appendChild(copy);
    refs.filePreview.appendChild(folderSummary);
    return;
  }

  const fileUrl = fileAccessUrl(entry.path);
  const openLink = document.createElement("a");
  openLink.className = "btn ghost";
  openLink.href = fileUrl;
  openLink.textContent = "新标签打开";
  openLink.target = "_blank";
  openLink.rel = "noreferrer";
  actions.appendChild(openLink);

  if (entry.kind === "image" || entry.kind === "video") {
    const expandButton = document.createElement("button");
    expandButton.className = "btn primary";
    expandButton.type = "button";
    expandButton.innerHTML =
      '<i data-lucide="maximize-2" aria-hidden="true"></i><span>放大预览</span>';
    expandButton.addEventListener("click", () => {
      openFileLightbox(entry, expandButton);
    });
    actions.appendChild(expandButton);
    refreshIcons(expandButton);
  }

  if (entry.kind === "image") {
    const image = document.createElement("img");
    image.src = fileUrl;
    image.alt = entry.name;
    image.loading = "lazy";
    refs.filePreview.appendChild(image);
    return;
  }

  if (entry.kind === "video") {
    const video = document.createElement("video");
    video.src = fileUrl;
    video.controls = true;
    video.preload = "metadata";
    video.playsInline = true;
    refs.filePreview.appendChild(video);
    return;
  }

  if (entry.kind === "audio") {
    const audio = document.createElement("audio");
    audio.src = fileUrl;
    audio.controls = true;
    audio.preload = "metadata";
    refs.filePreview.appendChild(audio);
    return;
  }

  if (entry.kind === "text") {
    fetch(fileUrl, {
      headers: headerOptions(false),
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        return response.text();
      })
      .then((text) => {
        if (requestId !== state.filePreviewRequestId) {
          return;
        }
        const pre = document.createElement("pre");
        pre.textContent = text.slice(0, 12000);
        refs.filePreview.appendChild(pre);
      })
      .catch((error) => {
        if (requestId !== state.filePreviewRequestId) {
          return;
        }
        const tip = document.createElement("div");
        tip.className = "empty-tip";
        tip.textContent = `文本预览失败: ${error.message}`;
        refs.filePreview.appendChild(tip);
      });
    return;
  }

  const tip = document.createElement("div");
  tip.className = "file-preview-empty";
  const heading = document.createElement("strong");
  heading.textContent = "此格式没有内嵌预览";
  const copy = document.createElement("span");
  copy.textContent = "使用右上角“新标签打开”查看或下载文件。";
  tip.appendChild(heading);
  tip.appendChild(copy);
  refs.filePreview.appendChild(tip);
}

function filteredFileEntries() {
  return state.fileEntries || [];
}

function renderFiles() {
  const entries = filteredFileEntries();
  state.fileMasonryObserver?.disconnect();
  state.fileMasonryObserver = null;
  refs.filesList.innerHTML = "";
  const selectedIsVisible = entries.some((entry) => entry.path === state.selectedFilePath);
  if (!selectedIsVisible) {
    state.selectedFilePath = "";
    renderCurrentDirectoryOverview();
  }
  if (!entries.length) {
    const tip = state.fileSearch.trim() ? "无匹配文件" : "目录为空";
    const empty = document.createElement("div");
    empty.className = "file-list-empty";
    empty.setAttribute("role", "status");
    const heading = document.createElement("strong");
    heading.textContent = tip;
    const copy = document.createElement("span");
    copy.textContent = state.fileSearch.trim()
      ? "尝试缩短关键词，或清除筛选。"
      : "这个目录目前没有可显示的文件。";
    empty.appendChild(heading);
    empty.appendChild(copy);
    refs.filesList.appendChild(empty);
    if (state.focusFilesAfterLoad) {
      state.focusFilesAfterLoad = false;
      refs.filesList.focus();
    }
    return;
  }

  const fragment = document.createDocumentFragment();
  for (const [entryIndex, entry] of entries.entries()) {
    const card = document.createElement("article");
    card.className = `file-card file-card-${isDirectoryEntry(entry) ? "folder" : entry.kind || "file"}`;
    card.dataset.path = entry.path || "";
    card.setAttribute("role", "listitem");
    card.setAttribute("aria-selected", "false");
    card.setAttribute(
      "aria-label",
      `${kindLabel(entry)} ${entry.name || entry.path || "(未命名)"}`,
    );
    card.tabIndex = entryIndex === 0 ? 0 : -1;
    card.title = isDirectoryEntry(entry)
      ? "打开文件夹"
      : ["image", "video"].includes(entry.kind)
        ? "放大预览"
        : "展开预览";
    if (entry.kind === "image" || entry.kind === "video") {
      card.setAttribute("aria-haspopup", "dialog");
    }

    const media = document.createElement("div");
    media.className = "file-card-media";
    if (entry.kind === "image") {
      const image = document.createElement("img");
      image.src = fileAccessUrl(entry.path);
      image.alt = "";
      image.loading = "lazy";
      image.decoding = "async";
      image.addEventListener("load", scheduleFileMasonryLayout, { once: true });
      media.appendChild(image);
    } else if (entry.kind === "video") {
      const video = document.createElement("video");
      video.src = fileAccessUrl(entry.path);
      video.muted = true;
      video.preload = "metadata";
      video.playsInline = true;
      video.setAttribute("aria-hidden", "true");
      video.addEventListener("loadedmetadata", scheduleFileMasonryLayout, {
        once: true,
      });
      media.appendChild(video);
      const play = document.createElement("span");
      play.className = "file-card-play";
      play.innerHTML = '<i data-lucide="play"></i>';
      media.appendChild(play);
    } else {
      const icon = document.createElement("span");
      icon.className = "file-card-icon";
      icon.innerHTML = `<i data-lucide="${iconForEntry(entry)}"></i>`;
      media.appendChild(icon);
    }

    const details = document.createElement("div");
    details.className = "file-card-details";
    const name = document.createElement("strong");
    name.className = "file-card-name";
    name.textContent = entry.name || entry.path || "(未命名)";
    const meta = document.createElement("span");
    meta.className = "file-card-meta";
    meta.textContent = [
      kindLabel(entry),
      isDirectoryEntry(entry) ? "点击进入" : formatFileSize(entry.size),
      formatFileDate(entry.modified_at),
    ].join(" · ");
    details.appendChild(name);
    details.appendChild(meta);
    card.appendChild(media);
    card.appendChild(details);

    const selectCard = () => {
      for (const candidate of refs.filesList.querySelectorAll(".file-card")) {
        candidate.classList.remove("active");
        candidate.setAttribute("aria-selected", "false");
        candidate.tabIndex = candidate === card ? 0 : -1;
      }
      card.classList.add("active");
      card.setAttribute("aria-selected", "true");
      state.selectedFilePath = entry.path || "";
      updateFilesAccountContext();
      renderFilePreview(entry);
    };

    const activateCard = (focusAfterLoad = false) => {
      if (isDirectoryEntry(entry)) {
        navigateToFilePath(entry.path || "", { focusAfterLoad });
        return;
      }
      selectCard();
      if (entry.kind === "image" || entry.kind === "video") {
        openFileLightbox(entry, card);
      }
    };

    card.addEventListener("click", () => activateCard(false));
    card.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        activateCard(true);
        return;
      }
      if (event.key === " ") {
        event.preventDefault();
        activateCard(false);
        return;
      }
      if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
        return;
      }
      event.preventDefault();
      const cards = Array.from(refs.filesList.querySelectorAll(".file-card"));
      const index = cards.indexOf(card);
      let nextIndex = index;
      if (event.key === "ArrowDown") {
        nextIndex = Math.min(cards.length - 1, index + 1);
      } else if (event.key === "ArrowUp") {
        nextIndex = Math.max(0, index - 1);
      } else if (event.key === "Home") {
        nextIndex = 0;
      } else if (event.key === "End") {
        nextIndex = cards.length - 1;
      }
      const nextCard = cards[nextIndex];
      if (nextCard) {
        card.tabIndex = -1;
        nextCard.tabIndex = 0;
        nextCard.focus();
      }
    });

    fragment.appendChild(card);
  }
  refs.filesList.appendChild(fragment);
  refreshIcons(refs.filesList);
  observeFileMasonryCards();
  if (state.focusFilesAfterLoad) {
    state.focusFilesAfterLoad = false;
    refs.filesList.querySelector(".file-card")?.focus();
  }
}

function renderFileBreadcrumb() {
  if (!refs.filesBreadcrumb) {
    return;
  }
  refs.filesBreadcrumb.innerHTML = "";
  const rootLabel = state.currentScope === "download" ? "下载目录" : "项目目录";
  const segments = state.currentPath.split("/").filter(Boolean);
  const crumbs = [{ label: rootLabel, path: "" }];
  let accumulatedPath = "";
  for (const segment of segments) {
    accumulatedPath = accumulatedPath ? `${accumulatedPath}/${segment}` : segment;
    crumbs.push({ label: segment, path: accumulatedPath });
  }

  const fragment = document.createDocumentFragment();
  crumbs.forEach((crumb, index) => {
    if (index > 0) {
      const separator = document.createElement("span");
      separator.className = "file-breadcrumb-separator";
      separator.textContent = "/";
      separator.setAttribute("aria-hidden", "true");
      fragment.appendChild(separator);
    }
    const isCurrent = index === crumbs.length - 1;
    if (isCurrent) {
      const current = document.createElement("span");
      current.className = "file-breadcrumb-current";
      current.textContent = crumb.label;
      current.setAttribute("aria-current", "page");
      fragment.appendChild(current);
      return;
    }
    const button = document.createElement("button");
    button.className = "file-breadcrumb-button";
    button.type = "button";
    button.textContent = crumb.label;
    button.addEventListener("click", () => navigateToFilePath(crumb.path));
    fragment.appendChild(button);
  });
  refs.filesBreadcrumb.appendChild(fragment);
  refs.filesHomeBtn.disabled = !state.currentPath;
  refs.filesUpBtn.disabled = !state.currentPath;
}

function navigateToFilePath(path, { focusAfterLoad = false, keepSearch = false } = {}) {
  state.currentPath = String(path || "").replaceAll("\\", "/").replace(/^\/+|\/+$/g, "");
  state.currentParentPath = parentPath(state.currentPath);
  state.selectedFilePath = "";
  state.filePage = 1;
  state.focusFilesAfterLoad = focusAfterLoad;
  refs.filesPath.value = state.currentPath;
  if (!keepSearch) {
    state.fileSearch = "";
    refs.filesSearch.value = "";
  }
  updateFilesAccountContext();
  renderFileBreadcrumb();
  return loadFiles();
}

function updateFilesAccountContext() {
  const context = state.fileAccountContext || {};
  const hasAccount = Boolean(context.url);
  const selected = state.fileEntries.find((item) => item.path === state.selectedFilePath);
  const fileLabel = selected?.name || selected?.path || "";
  const selectedHint = fileLabel ? ` · 已选文件: ${fileLabel}` : " · 未选择文件";
  if (refs.filesAccountTools) {
    refs.filesAccountTools.hidden = !hasAccount;
  }
  if (refs.filesAccountContext) {
    refs.filesAccountContext.textContent = hasAccount
      ? `账户上下文：${context.mark || "(未设置 mark)"} · ${context.url}${selectedHint}`
      : "账户上下文：未从看板选择账户";
  }
  const mediaSelected = Boolean(
    hasAccount &&
      selected &&
      !selected.is_dir &&
      (selected.kind === "image" || selected.kind === "video"),
  );
  const imageSelected = Boolean(
    hasAccount &&
      selected &&
      !selected.is_dir &&
      selected.kind === "image",
  );
  if (refs.filesPinProfileBtn) {
    refs.filesPinProfileBtn.disabled = !mediaSelected || state.currentScope !== "download";
  }
  if (refs.filesGenerateAvatarBtn) {
    refs.filesGenerateAvatarBtn.disabled = !mediaSelected;
  }
  if (refs.filesPinAvatarBtn) {
    refs.filesPinAvatarBtn.disabled = !imageSelected;
  }
}

function openBoardFolderInFiles(card) {
  const folderPath = card?.dataset?.folderPath || "";
  const url = card?.dataset?.url || "";
  if (!folderPath || !url) {
    setBoardStatus("当前卡片无目录或 URL，无法跳转文件浏览");
    return;
  }
  state.fileAccountContext = {
    platform: card.dataset.platform || state.accountBoard.platform,
    url,
    mark: card.dataset.mark || "",
  };
  state.currentScope = "download";
  refs.filesScope.value = "download";
  switchTab("files");
  navigateToFilePath(folderPath);
}

function collectBoardCards() {
  return Array.from(refs.boardGrid?.querySelectorAll(".profile-card") || []);
}

function setBoardAvatarBatchBusy(busy) {
  state.boardAvatarBatchRunning = Boolean(busy);
  if (refs.boardAvatarPageBtn) {
    refs.boardAvatarPageBtn.disabled = state.boardAvatarBatchRunning;
  }
  if (refs.boardAvatarAllBtn) {
    refs.boardAvatarAllBtn.disabled = state.boardAvatarBatchRunning;
  }
}

async function generateBoardAvatarCurrentPage() {
  const urls = collectBoardCards()
    .map((card) => card.dataset.url || "")
    .filter(Boolean);
  if (!urls.length) {
    setBoardStatus("当前页没有可处理的账号卡片");
    return;
  }
  await enqueueBoardAvatarBatch(urls, "当前页");
}

async function generateBoardAvatarAllUnpinned() {
  await enqueueBoardAvatarBatch([], "全部账户");
}

async function enqueueBoardAvatarBatch(urls = [], scopeLabel = "全部账户") {
  if (state.boardAvatarBatchRunning) {
    setBoardStatus("头像任务正在加入队列，请稍候");
    return;
  }
  setBoardAvatarBatchBusy(true);
  const platform = state.accountBoard.platform || "douyin";
  try {
    setBoardStatus(`正在创建${scopeLabel}头像任务…`);
    const payload = await fetchJson("/ui/api/accounts/board/avatar/batch", {
      method: "POST",
      headers: headerOptions(true),
      body: JSON.stringify({
        platform,
        urls,
        skip_existing: true,
        max_candidates: 12,
      }),
    });
    const taskId = payload?.task?.task_id || "";
    if (taskId) {
      state.selectedTaskId = taskId;
    }
    setBoardStatus(
      `${scopeLabel}头像任务已入队${taskId ? `（${taskId}）` : ""}：优先图片，无图片时抽取视频帧；可在任务中心暂停或继续`,
    );
    setApiStatus("就绪", "ok");
    await loadTaskList();
  } catch (error) {
    setBoardStatus(`创建头像任务失败: ${error.message}`);
    setApiStatus(`异常: ${error.message}`, "error");
  } finally {
    setBoardAvatarBatchBusy(false);
  }
}

async function pinFromFileBrowser() {
  const context = state.fileAccountContext || {};
  const selected = state.fileEntries.find((item) => item.path === state.selectedFilePath);
  if (!context.url) {
    setBoardStatus("请先从账户看板进入文件浏览");
    return;
  }
  if (!selected || selected.is_dir || (selected.kind !== "image" && selected.kind !== "video")) {
    setBoardStatus("请选择图片或视频文件后再执行 Profile Pin");
    return;
  }
  try {
    await fetchJson("/ui/api/accounts/board/pin", {
      method: "POST",
      headers: headerOptions(true),
      body: JSON.stringify({
        platform: context.platform || "douyin",
        url: context.url,
        path: selected.path,
      }),
    });
    setBoardStatus("已将当前文件设为该账号 Profile Pin");
    setApiStatus("就绪", "ok");
  } catch (error) {
    setBoardStatus(`Profile Pin 失败: ${error.message}`);
    setApiStatus(`异常: ${error.message}`, "error");
  }
}

async function generateAvatarFromFileBrowser() {
  const context = state.fileAccountContext || {};
  const selected = state.fileEntries.find((item) => item.path === state.selectedFilePath);
  if (!context.url) {
    setBoardStatus("请先从账户看板进入文件浏览");
    return;
  }
  if (!selected || selected.is_dir || (selected.kind !== "image" && selected.kind !== "video")) {
    setBoardStatus("请选择图片或视频文件后再执行头像生成");
    return;
  }
  setBoardStatus("正在基于当前文件生成人脸头像…");
  try {
    const payload = await fetchJson("/ui/api/accounts/board/avatar/generate", {
      method: "POST",
      headers: headerOptions(true),
      body: JSON.stringify({
        platform: context.platform || "douyin",
        url: context.url,
        scope: state.currentScope,
        path: selected.path,
      }),
    });
    const faces = payload?.details?.faces_detected || 0;
    setBoardStatus(`头像生成成功（识别 ${faces} 张人脸）`);
    setApiStatus("就绪", "ok");
  } catch (error) {
    setBoardStatus(`头像生成失败: ${error.message}`);
    setApiStatus(`异常: ${error.message}`, "error");
  }
}

async function pinAvatarFromFileBrowser() {
  const context = state.fileAccountContext || {};
  const selected = state.fileEntries.find((item) => item.path === state.selectedFilePath);
  if (!context.url) {
    setBoardStatus("请先从账户看板进入文件浏览");
    return;
  }
  if (!selected || selected.is_dir || selected.kind !== "image") {
    setBoardStatus("手动设头像仅支持图片文件");
    return;
  }
  try {
    await fetchJson("/ui/api/accounts/board/avatar/pin", {
      method: "POST",
      headers: headerOptions(true),
      body: JSON.stringify({
        platform: context.platform || "douyin",
        url: context.url,
        scope: state.currentScope,
        path: selected.path,
      }),
    });
    setBoardStatus("已将当前图片手动设为账号头像");
    setApiStatus("就绪", "ok");
  } catch (error) {
    setBoardStatus(`手动设头像失败: ${error.message}`);
    setApiStatus(`异常: ${error.message}`, "error");
  }
}

async function loadFileStats() {
  if (!refs.filesStats) {
    return;
  }
  refs.filesStats.textContent = "正在统计目录信息…";
  try {
    const query = new URLSearchParams({
      scope: state.currentScope,
      path: state.currentPath || "",
    });
    const payload = await fetchJson(`/ui/api/files/stats?${query.toString()}`, {
      method: "GET",
      headers: headerOptions(false),
    });
    refs.filesStats.textContent = `目录统计：文件 ${payload.files} · 图片 ${payload.images} · 视频 ${payload.videos} · 文件夹 ${payload.folders} · 占用 ${payload.size_human}`;
  } catch (error) {
    refs.filesStats.textContent = `统计失败: ${error.message}`;
  }
}

async function loadFiles() {
  refs.filesMeta.textContent = "正在加载目录…";
  resetFilePreview("正在加载目录", "请稍候…");
  renderFileBreadcrumb();
  try {
    const query = new URLSearchParams({
      scope: state.currentScope,
      path: state.currentPath || "",
      page: String(state.filePage),
      page_size: String(state.filePageSize),
      search: state.fileSearch.trim(),
    });
    const payload = await fetchJson(`/ui/api/files?${query.toString()}`, {
      method: "GET",
      headers: headerOptions(false),
    });
    const normalized = normalizeEntries(payload);
    state.fileEntries = normalized.entries || [];
    state.currentPath = normalized.currentPath || state.currentPath || "";
    state.currentParentPath = normalized.parentPath || parentPath(state.currentPath);
    state.filePage = normalized.page || 1;
    state.filePageSize = normalized.pageSize || state.filePageSize;
    state.filePages = normalized.pages || 1;
    state.fileTotal = normalized.total || 0;
    state.selectedFilePath = "";
    refs.filesPath.value = state.currentPath;
    renderFileBreadcrumb();
    renderFiles();
    updateFilesAccountContext();
    const start = state.fileTotal ? (state.filePage - 1) * state.filePageSize + 1 : 0;
    const end = state.fileTotal
      ? Math.min(state.fileTotal, start + state.fileEntries.length - 1)
      : 0;
    refs.filesMeta.textContent = state.fileSearch.trim()
      ? `“${state.fileSearch.trim()}” · ${start}–${end} / ${state.fileTotal} 项`
      : `${start}–${end} / ${state.fileTotal} 个项目`;
    refs.filesPageMeta.textContent = `第 ${state.filePage} / ${state.filePages} 页`;
    refs.filesPrevBtn.disabled = state.filePage <= 1;
    refs.filesNextBtn.disabled = state.filePage >= state.filePages;
    refs.filesPageSize.value = String(state.filePageSize);
    if (refs.filesStats.textContent.includes("统计信息待加载")) {
      refs.filesStats.textContent = "目录统计按需加载，避免扫描大型下载目录";
    }
    setApiStatus("就绪", "ok");
  } catch (error) {
    state.fileEntries = [];
    state.selectedFilePath = "";
    refs.filesList.innerHTML = "";
    refs.filesMeta.textContent = `加载失败: ${error.message}`;
    refs.filesPageMeta.textContent = "第 1 / 1 页";
    refs.filesPrevBtn.disabled = true;
    refs.filesNextBtn.disabled = true;
    resetFilePreview("无法加载此目录", "检查路径或访问 Token 后重试。");
    renderFileBreadcrumb();
    if (refs.filesStats) {
      refs.filesStats.textContent = "统计信息待加载…";
    }
    updateFilesAccountContext();
    setApiStatus(`异常: ${error.message}`, "error");
  }
}

function parentPath(path) {
  if (!path) {
    return "";
  }
  const items = path.split("/").filter(Boolean);
  items.pop();
  return items.join("/");
}

function boardAssetUrl(path, scope = "download") {
  return `/ui/api/file?scope=${encodeURIComponent(scope)}&path=${encodeURIComponent(path || "")}`;
}

function boardColumnsCap() {
  const compactMode = state.accountBoard.viewMode === "avatar";
  const viewportWidth = window.innerWidth || 1280;
  const boardWidth =
    refs.boardGrid?.clientWidth ||
    document.getElementById("panel-profiles")?.clientWidth ||
    viewportWidth;
  const gap = compactMode ? 8 : 10;
  const minimumCardWidth = compactMode ? 156 : 248;
  const widthCap = Math.max(
    1,
    Math.floor((boardWidth + gap) / (minimumCardWidth + gap)),
  );
  if (viewportWidth <= 460) {
    return compactMode ? Math.min(2, widthCap) : 1;
  }
  if (viewportWidth <= 700) {
    return compactMode ? Math.min(3, widthCap) : Math.min(2, widthCap);
  }
  return Math.min(compactMode ? 10 : 6, widthCap);
}

function applyBoardColumns(persist = true) {
  const cap = boardColumnsCap();
  const inputColumns = Number(state.accountBoard.columns || 4);
  const next = Math.max(1, Math.min(inputColumns, cap));
  state.accountBoard.columns = next;
  if (refs.boardDensity) {
    refs.boardDensity.max = String(cap);
    refs.boardDensity.value = String(next);
  }
  if (refs.boardDensityLabel) {
    refs.boardDensityLabel.textContent = `${next} 列`;
  }
  if (refs.boardGrid) {
    refs.boardGrid.style.setProperty("--board-columns", String(next));
    refs.boardGrid.classList.toggle("profile-board-compact", state.accountBoard.viewMode === "avatar");
    refs.boardGrid.classList.toggle(
      "profile-board-ultra",
      state.accountBoard.viewMode === "avatar" && next >= 8,
    );
  }
  if (persist) {
    try {
      localStorage.setItem(BOARD_COLUMNS_STORAGE_KEY, String(next));
    } catch {}
  }
}

function updateBoardMeta() {
  const filtered = state.accountBoard.total;
  const all = state.accountBoard.unfilteredTotal;
  const countText =
    filtered === all ? `共 ${filtered} 账号` : `筛选 ${filtered} / 全部 ${all} 账号`;
  refs.boardMeta.textContent = `第 ${state.accountBoard.page} / ${state.accountBoard.pages} 页 · ${countText}`;
}

function setBoardStatus(text) {
  refs.boardStatus.textContent = text;
}

function formatBoardDate(value) {
  const text = String(value || "").trim();
  if (!text) {
    return "暂无记录";
  }
  const date = new Date(text);
  if (Number.isNaN(date.getTime())) {
    return text.replace("T", " ").slice(0, 19);
  }
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

function selectedBoardPreview(card) {
  if (!card) {
    return {
      path: "",
      kind: "",
      scope: "download",
      pinned: false,
    };
  }
  const mediaPreview = {
    path: card.dataset.mediaPath || "",
    kind: card.dataset.mediaKind || "",
    scope: "download",
    pinned: card.dataset.pinned === "1",
  };
  const hasMedia = Boolean(mediaPreview.path && mediaPreview.kind);
  const avatarPreview = {
    path: card.dataset.avatarPath || "",
    kind: "image",
    scope: card.dataset.avatarScope || "project",
    pinned: true,
  };
  const isPinnedProfile = card.dataset.pinned === "1";
  const hasAvatar = Boolean(avatarPreview.path);
  const forcedMode = String(card.dataset.previewMode || "").toLowerCase();
  if (forcedMode === "media" && hasMedia) {
    return mediaPreview;
  }
  if (forcedMode === "avatar" && hasAvatar) {
    return avatarPreview;
  }
  if (state.accountBoard.viewMode === "avatar" && hasAvatar) {
    return avatarPreview;
  }
  if (isPinnedProfile && hasMedia) {
    return mediaPreview;
  }
  if (hasMedia) {
    return mediaPreview;
  }
  if (hasAvatar) {
    return {
      ...avatarPreview,
    };
  }
  return mediaPreview;
}

function renderBoardCardPreview(card) {
  const mediaWrap = card.querySelector(".profile-media-wrap");
  const pinBtn = card.querySelector('[data-action="board-pin-media"]');
  const refreshBtn = card.querySelector('[data-action="board-refresh-media"]');
  const refreshVideoBtn = card.querySelector('[data-action="board-refresh-video"]');
  const pinBadge = card.querySelector(".profile-pin-badge");
  const avatarBadge = card.querySelector(".profile-avatar-badge");
  const displayBadge = card.querySelector(".profile-display-badge");
  const avatarBtn = card.querySelector('[data-action="board-generate-avatar"]');
  const preview = selectedBoardPreview(card);

  if (pinBadge) {
    pinBadge.textContent = "已固定";
    pinBadge.hidden = card.dataset.pinned !== "1";
    pinBadge.classList.toggle("ok", card.dataset.pinned === "1");
  }
  if (avatarBadge) {
    avatarBadge.textContent = card.dataset.avatarPath ? "头像" : "待头像";
    avatarBadge.classList.toggle("ok", Boolean(card.dataset.avatarPath));
    avatarBadge.classList.toggle("warn", !card.dataset.avatarPath);
  }
  if (displayBadge) {
    const isPinnedProfile = card.dataset.pinned === "1";
    const compactMode = state.accountBoard.viewMode === "avatar";
    displayBadge.hidden = false;
    if (compactMode && !preview.path) {
      displayBadge.textContent = "无预览";
      displayBadge.classList.add("warn");
      displayBadge.classList.remove("ok");
    } else if (compactMode && isPinnedProfile) {
      displayBadge.textContent = "媒体固定";
      displayBadge.classList.add("ok");
      displayBadge.classList.remove("warn");
    } else if (compactMode) {
      displayBadge.hidden = true;
      displayBadge.classList.remove("ok", "warn");
    } else if (preview.path && preview.scope === "project") {
      displayBadge.textContent = "展示头像";
      displayBadge.classList.add("ok");
      displayBadge.classList.remove("warn");
    } else if (isPinnedProfile && card.dataset.mediaPath) {
      displayBadge.textContent = "固定媒体";
      displayBadge.classList.add("ok");
      displayBadge.classList.remove("warn");
    } else if (preview.path) {
      displayBadge.textContent = "媒体";
      displayBadge.classList.remove("ok", "warn");
    } else {
      displayBadge.textContent = "无预览";
      displayBadge.classList.add("warn");
      displayBadge.classList.remove("ok");
    }
  }
  if (pinBtn) {
    const label = pinBtn.querySelector("span");
    if (label) {
      label.textContent =
        card.dataset.pinned === "1" ? "媒体已固定" : "固定当前媒体";
    }
    pinBtn.disabled = !card.dataset.mediaPath || card.dataset.pinned === "1";
  }
  if (refreshBtn) {
    refreshBtn.disabled = !card.dataset.folderPath;
  }
  if (refreshVideoBtn) {
    refreshVideoBtn.disabled = !card.dataset.folderPath;
  }
  if (avatarBtn) {
    avatarBtn.disabled = !card.dataset.mediaPath;
  }
  if (!mediaWrap) {
    return;
  }
  mediaWrap.innerHTML = "";
  if (!preview.path || !preview.kind) {
    const empty = document.createElement("div");
    empty.className = "profile-empty";
    empty.textContent = card.dataset.folderPath
      ? "目录存在，但未找到可预览媒体"
      : "未匹配到账户目录";
    mediaWrap.appendChild(empty);
    return;
  }
  const src = boardAssetUrl(preview.path, preview.scope || "download");
  if (preview.kind === "image") {
    const image = document.createElement("img");
    image.src = src;
    image.alt = card.dataset.mark || "profile";
    image.loading = "lazy";
    mediaWrap.appendChild(image);
    return;
  }
  if (preview.kind === "video") {
    const video = document.createElement("video");
    video.src = src;
    video.controls = true;
    video.preload = "metadata";
    video.muted = true;
    video.playsInline = true;
    mediaWrap.appendChild(video);
    return;
  }
  const empty = document.createElement("div");
  empty.className = "profile-empty";
  empty.textContent = "媒体类型暂不支持预览";
  mediaWrap.appendChild(empty);
}

function setBoardCardMedia(card, mediaPath, mediaKind, pinned = false) {
  card.dataset.mediaPath = mediaPath || "";
  card.dataset.mediaKind = mediaKind || "";
  card.dataset.pinned = pinned ? "1" : "0";
  renderBoardCardPreview(card);
}

function renderAccountBoard(items) {
  refs.boardGrid.innerHTML = "";
  if (!Array.isArray(items) || !items.length) {
    refs.boardGrid.innerHTML = '<div class="empty-tip">当前页没有可展示账号</div>';
    return;
  }
  const fragment = document.createDocumentFragment();
  for (const item of items) {
    const card = document.createElement("article");
    card.className = "profile-card";
    card.dataset.platform = item.platform || state.accountBoard.platform;
    card.dataset.url = item.url || "";
    card.dataset.mark = item.mark || "";
    card.dataset.folderPath = item.folder_path || "";
    card.dataset.mediaPath = item.media_path || "";
    card.dataset.mediaKind = item.media_kind || "";
    card.dataset.pinned = item.pinned ? "1" : "0";
    card.dataset.avatarPath = item.avatar_path || "";
    card.dataset.avatarScope = item.avatar_scope || "";
    card.dataset.latestWorkAt = item.latest_work_at || "";
    card.dataset.lastCheckedAt = item.last_checked_at || "";
    card.dataset.lastStatus = item.last_status || "never";
    card.dataset.previewMode = "";

    const mediaWrap = document.createElement("div");
    mediaWrap.className = "profile-media-wrap";

    const body = document.createElement("div");
    body.className = "profile-body";

    const titleRow = document.createElement("div");
    titleRow.className = "profile-title";

    const name = document.createElement("div");
    name.className = "profile-name";
    name.textContent = item.mark || "未设置 mark";
    name.title = item.mark || item.url || "未设置 mark";

    const badges = document.createElement("div");
    badges.className = "profile-state-row";
    const enableBadge = document.createElement("span");
    enableBadge.className = `badge ${item.enable ? "ok" : "warn"}`;
    enableBadge.textContent = item.enable ? "启用" : "停用";
    const avatarBadge = document.createElement("span");
    avatarBadge.className = `badge profile-avatar-badge ${item.avatar_path ? "ok" : "warn"}`;
    avatarBadge.textContent = item.avatar_path ? "头像" : "待头像";
    const displayBadge = document.createElement("span");
    displayBadge.className = "badge profile-display-badge";
    displayBadge.textContent = item.pinned
      ? "固定媒体"
      : item.avatar_path
        ? "展示头像"
        : item.media_path
          ? "媒体"
          : "无预览";
    badges.appendChild(enableBadge);
    badges.appendChild(avatarBadge);
    badges.appendChild(displayBadge);

    titleRow.appendChild(name);

    const url = document.createElement("div");
    url.className = "profile-url";
    url.textContent = item.url || "-";

    const folder = document.createElement("div");
    folder.className = "profile-folder";
    folder.textContent = item.folder_path
      ? `目录: ${item.folder_path}`
      : "目录: (未匹配)";

    const activity = document.createElement("div");
    activity.className = "profile-activity";
    activity.dataset.state = item.last_status || "never";
    if (item.last_error) {
      activity.title = item.last_error;
    }
    const latestLine = document.createElement("span");
    latestLine.className = "profile-latest-line";
    const latestLabel = document.createElement("span");
    latestLabel.className = "profile-activity-label";
    latestLabel.textContent = "最新";
    const latestValue = document.createElement("strong");
    latestValue.className = "profile-latest-full";
    latestValue.textContent = formatBoardDate(item.latest_work_at);
    const latestShortValue = document.createElement("strong");
    latestShortValue.className = "profile-latest-short";
    latestShortValue.textContent = item.latest_work_at
      ? formatBoardDate(item.latest_work_at).slice(0, 10)
      : "暂无记录";
    latestLine.appendChild(latestLabel);
    latestLine.appendChild(latestValue);
    latestLine.appendChild(latestShortValue);
    if (item.latest_work_source === "filename") {
      const source = document.createElement("span");
      source.className = "profile-latest-source";
      source.textContent = "文件索引";
      latestLine.appendChild(source);
    }
    const checkedLine = document.createElement("span");
    checkedLine.className = "profile-check-line";
    const statusLabel =
      item.last_status === "success"
        ? `最近爬取成功 · 处理 ${Number(item.last_item_count || 0)} 项`
        : item.last_status === "failed"
          ? "最近爬取失败"
          : "尚无任务记录";
    checkedLine.textContent = item.last_checked_at
      ? `${statusLabel} · ${formatBoardDate(item.last_checked_at)}`
      : statusLabel;
    activity.appendChild(latestLine);
    activity.appendChild(checkedLine);

    const actions = document.createElement("div");
    actions.className = "profile-actions";
    actions.innerHTML = `
      <button class="btn ghost profile-action-primary" type="button" data-action="board-open-files">
        <i data-lucide="folder-open" aria-hidden="true"></i><span>文件</span>
      </button>
      <button class="btn ghost profile-action-primary" type="button" data-action="board-refresh-media">
        <i data-lucide="refresh-cw" aria-hidden="true"></i><span>更新</span>
      </button>
      <details class="profile-actions-menu">
        <summary class="btn ghost profile-more-btn" role="button" aria-haspopup="menu" aria-label="更多账户操作" title="更多账户操作">
          <i data-lucide="ellipsis" aria-hidden="true"></i>
        </summary>
        <div class="profile-actions-popover" role="menu">
          <button class="profile-menu-item" type="button" role="menuitem" data-action="board-open-account">
            <i data-lucide="external-link" aria-hidden="true"></i><span>打开主页</span>
          </button>
          <button class="profile-menu-item" type="button" role="menuitem" data-action="board-refresh-video">
            <i data-lucide="video" aria-hidden="true"></i><span>仅刷新视频</span>
          </button>
          <button class="profile-menu-item" type="button" role="menuitem" data-action="board-generate-avatar">
            <i data-lucide="image-plus" aria-hidden="true"></i><span>处理头像</span>
          </button>
          <button class="profile-menu-item" type="button" role="menuitem" data-action="board-pin-media">
            <i data-lucide="pin" aria-hidden="true"></i><span>固定当前媒体</span>
          </button>
        </div>
      </details>
    `;

    body.appendChild(titleRow);
    body.appendChild(badges);
    body.appendChild(url);
    body.appendChild(folder);
    body.appendChild(activity);
    body.appendChild(actions);

    card.appendChild(mediaWrap);
    card.appendChild(body);
    setBoardCardMedia(card, item.media_path || "", item.media_kind || "", Boolean(item.pinned));
    fragment.appendChild(card);
  }
  refs.boardGrid.appendChild(fragment);
  refreshIcons(refs.boardGrid);
}

async function loadAccountBoard(resetPage = false) {
  if (!refs.boardPlatform || !refs.boardPageSize) {
    return;
  }
  if (resetPage) {
    state.accountBoard.page = 1;
  }
  state.accountBoard.platform = refs.boardPlatform.value || "douyin";
  state.accountBoard.pageSize = Number(refs.boardPageSize.value || "24");
  state.accountBoard.search = refs.boardSearch?.value.trim() || "";
  state.accountBoard.status = refs.boardStatusFilter?.value || "all";
  state.accountBoard.sort = refs.boardSort?.value || "configured";
  setBoardStatus("正在加载账户媒体看板…");
  try {
    const query = new URLSearchParams({
      platform: state.accountBoard.platform,
      page: String(state.accountBoard.page),
      page_size: String(state.accountBoard.pageSize),
      search: state.accountBoard.search,
      status: state.accountBoard.status,
      sort: state.accountBoard.sort,
    });
    const payload = await fetchJson(`/ui/api/accounts/board?${query.toString()}`, {
      method: "GET",
      headers: headerOptions(false),
    });
    state.accountBoard.page = Number(payload.page || 1);
    state.accountBoard.pageSize = Number(payload.page_size || state.accountBoard.pageSize);
    state.accountBoard.pages = Number(payload.pages || 1);
    state.accountBoard.total = Number(payload.total || 0);
    state.accountBoard.unfilteredTotal = Number(
      payload.unfiltered_total ?? state.accountBoard.total,
    );
    refs.boardPrevBtn.disabled = state.accountBoard.page <= 1;
    refs.boardNextBtn.disabled = state.accountBoard.page >= state.accountBoard.pages;
    updateBoardMeta();
    renderAccountBoard(payload.items || []);
    setBoardStatus(
      `已加载 ${state.accountBoard.platform} · 第 ${state.accountBoard.page}/${state.accountBoard.pages} 页`,
    );
    state.accountBoardDirty = false;
    setApiStatus("就绪", "ok");
  } catch (error) {
    refs.boardGrid.innerHTML = "";
    setBoardStatus(`加载失败: ${error.message}`);
    setApiStatus(`异常: ${error.message}`, "error");
  }
}

async function refreshBoardCard(card, preferKind = "auto") {
  const platform = card.dataset.platform || state.accountBoard.platform;
  const url = card.dataset.url || "";
  if (!url) {
    setBoardStatus("当前卡片缺少账号 URL，无法刷新");
    return;
  }
  setBoardStatus("正在刷新卡片媒体…");
  try {
    const payload = await fetchJson("/ui/api/accounts/board/random", {
      method: "POST",
      headers: headerOptions(true),
      body: JSON.stringify({
        platform,
        url,
        current_path: card.dataset.mediaPath || "",
        prefer_kind: preferKind,
      }),
    });
    card.dataset.previewMode = "media";
    setBoardCardMedia(
      card,
      payload.media_path || "",
      payload.media_kind || "",
      false,
    );
    const usedKind = String(payload.media_kind || "").trim();
    const preferText =
      preferKind === "video"
        ? "视频优先"
        : preferKind === "image"
          ? "图片优先"
          : "自动";
    setBoardStatus(`已刷新卡片媒体（${preferText}，当前: ${usedKind || "无"}）`);
    setApiStatus("就绪", "ok");
  } catch (error) {
    setBoardStatus(`刷新失败: ${error.message}`);
    setApiStatus(`异常: ${error.message}`, "error");
  }
}

async function pinBoardCard(card) {
  const platform = card.dataset.platform || state.accountBoard.platform;
  const url = card.dataset.url || "";
  const path = card.dataset.mediaPath || "";
  if (!url || !path) {
    setBoardStatus("当前卡片无可 Pin 的媒体");
    return;
  }
  try {
    await fetchJson("/ui/api/accounts/board/pin", {
      method: "POST",
      headers: headerOptions(true),
      body: JSON.stringify({
        platform,
        url,
        path,
      }),
    });
    setBoardCardMedia(card, path, card.dataset.mediaKind || "", true);
    setBoardStatus("已固定该账号 Profile 媒体");
    setApiStatus("就绪", "ok");
  } catch (error) {
    setBoardStatus(`固定失败: ${error.message}`);
    setApiStatus(`异常: ${error.message}`, "error");
  }
}

async function pinCurrentBoardPage() {
  const cards = Array.from(refs.boardGrid.querySelectorAll(".profile-card"));
  const items = cards
    .map((card) => ({
      url: card.dataset.url || "",
      path: card.dataset.mediaPath || "",
    }))
    .filter((item) => item.url && item.path);
  if (!items.length) {
    setBoardStatus("当前页没有可批量 Pin 的媒体");
    return;
  }
  try {
    const result = await fetchJson("/ui/api/accounts/board/pin-all", {
      method: "POST",
      headers: headerOptions(true),
      body: JSON.stringify({
        platform: state.accountBoard.platform,
        items,
      }),
    });
    for (const card of cards) {
      if (!card.dataset.mediaPath) {
        continue;
      }
      setBoardCardMedia(card, card.dataset.mediaPath, card.dataset.mediaKind || "", true);
    }
    setBoardStatus(`批量固定完成：${result.updated || 0} / ${result.requested || items.length}`);
    setApiStatus("就绪", "ok");
  } catch (error) {
    setBoardStatus(`批量固定失败: ${error.message}`);
    setApiStatus(`异常: ${error.message}`, "error");
  }
}

async function resolveShareLink() {
  const platform = refs.sharePlatform.value;
  const text = refs.shareInput.value.trim();
  if (!text) {
    refs.shareStatus.textContent = "请输入分享文本";
    return;
  }
  refs.shareStatus.textContent = "解析中…";
  refs.shareResult.textContent = "";
  refs.shareResult.removeAttribute("href");
  try {
    const payload = await fetchJson(`/${platform}/share`, {
      method: "POST",
      headers: headerOptions(true),
      body: JSON.stringify({ text }),
    });
    const url = payload?.url || "";
    refs.shareStatus.textContent = payload?.message || "解析完成";
    if (url) {
      refs.shareResult.textContent = url;
      refs.shareResult.href = url;
    }
    setApiStatus("就绪", "ok");
  } catch (error) {
    refs.shareStatus.textContent = `解析失败: ${error.message}`;
    setApiStatus(`异常: ${error.message}`, "error");
  }
}

async function copyShareResult() {
  const text = refs.shareResult.textContent?.trim();
  if (!text) {
    refs.shareStatus.textContent = "暂无可复制结果";
    return;
  }
  try {
    await navigator.clipboard.writeText(text);
    refs.shareStatus.textContent = "结果已复制";
  } catch (error) {
    refs.shareStatus.textContent = `复制失败: ${error.message}`;
  }
}

function getTaskTemplate(endpoint) {
  const template = TASK_TEMPLATES[endpoint] || {
    cookie: "",
    proxy: "",
    source: false,
  };
  return JSON.stringify(template, null, 2);
}

function taskEndpointPlatform(endpoint = refs.taskEndpoint.value) {
  return String(endpoint || "").startsWith("/tiktok/") ||
    String(endpoint || "").startsWith("/workflow/tiktok/")
    ? "tiktok"
    : "douyin";
}

function applyTaskIdentityToPayload(payload) {
  const nextPayload = { ...payload };
  const identityId = refs.taskIdentity.value || "";
  nextPayload.identity_id = identityId;
  if (identityId) {
    nextPayload.cookie = "";
    nextPayload.proxy = "";
  }
  return nextPayload;
}

function syncTaskIdentityControls() {
  const identityId = refs.taskIdentity.value || "";
  const identity = collectorIdentityById(identityId);
  refs.taskPayload.dataset.identityControlled = identityId ? "true" : "false";
  delete refs.taskIdentityHelp.dataset.state;
  if (!identityId) {
    refs.taskIdentityHelp.textContent = `自动路由使用 ${workflowPlatformLabel(
      taskEndpointPlatform(),
    )} 身份池策略；Payload 中的空 identity_id 会保留自动选择。`;
    return;
  }
  if (!collectorIdentityIsRoutable(identity)) {
    refs.taskIdentityHelp.textContent = "当前身份已不可路由；仅保留用于识别，请重新选择。";
    refs.taskIdentityHelp.dataset.state = "warning";
    return;
  }
  let hasLegacyOverride = false;
  try {
    const payload = parseTaskPayload(refs.taskPayload.value);
    hasLegacyOverride = Boolean(String(payload.cookie || "").trim() || String(payload.proxy || "").trim());
  } catch {}
  refs.taskIdentityHelp.textContent = hasLegacyOverride
    ? `已选择“${identity.name}”；提交时会清空 Payload 中的 cookie / proxy，改用身份凭据。`
    : `已选择“${identity.name}”；本次任务固定使用该身份，cookie / proxy 已由身份托管。`;
  if (hasLegacyOverride) {
    refs.taskIdentityHelp.dataset.state = "warning";
  }
}

function rewriteTaskPayloadForIdentity() {
  const payload = parseTaskPayload(refs.taskPayload.value);
  const normalized = applyTaskIdentityToPayload(payload);
  refs.taskPayload.value = JSON.stringify(normalized, null, 2);
  syncTaskIdentityControls();
  return normalized;
}

function syncTaskIdentitySelector() {
  populateCollectorIdentitySelect(
    refs.taskIdentity,
    taskEndpointPlatform(),
    "自动路由",
    { preserveUnavailable: true },
  );
  syncTaskIdentityControls();
}

function loadTaskTemplate() {
  refs.taskPayload.value = getTaskTemplate(refs.taskEndpoint.value);
  rewriteTaskPayloadForIdentity();
  refs.taskLabStatus.textContent = "已加载模板，可直接修改后执行";
  delete refs.taskLabStatus.dataset.state;
}

function summarizeTaskResponse(payload) {
  const parts = [];
  if (payload?.message) {
    parts.push(`message: ${payload.message}`);
  }
  if (Array.isArray(payload?.data)) {
    parts.push(`data items: ${payload.data.length}`);
  } else if (payload?.data && typeof payload.data === "object") {
    parts.push(`data fields: ${Object.keys(payload.data).length}`);
  } else if (payload?.url) {
    parts.push("url ready");
  }
  if (payload?.time) {
    parts.push(`time: ${payload.time}`);
  }
  return parts.join(" · ");
}

function parseTaskPayload(text) {
  if (!text.trim()) {
    return {};
  }
  let payload = {};
  try {
    payload = JSON.parse(text);
  } catch (error) {
    throw new Error(`Payload JSON 解析失败: ${error.message}`);
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error("Payload 必须是 JSON 对象");
  }
  return payload;
}

async function enqueueTaskRequest(endpoint, payload) {
  const result = await fetchJson("/ui/api/tasks", {
    method: "POST",
    headers: headerOptions(true),
    body: JSON.stringify({
      endpoint,
      payload,
    }),
  });
  return result?.task;
}

async function runTaskRequest() {
  const endpoint = refs.taskEndpoint.value;
  if (!selectedCollectorIdentityIsRunnable(refs.taskIdentity)) {
    refs.taskLabStatus.textContent = "当前选中的身份已不可路由，请改用自动路由或选择其他身份";
    refs.taskLabStatus.dataset.state = "error";
    refs.taskIdentity.focus();
    return;
  }
  refs.taskLabStatus.textContent = "任务入队中…";
  delete refs.taskLabStatus.dataset.state;
  try {
    const payload = rewriteTaskPayloadForIdentity();
    const task = await enqueueTaskRequest(endpoint, payload);
    state.selectedTaskId = task?.task_id || "";
    refs.taskLabStatus.textContent = `任务已入队：${state.selectedTaskId || endpoint}`;
    refs.taskLabStatus.dataset.state = "success";
    if (task) {
      renderTaskResult(task);
    }
    await loadTaskList();
    setApiStatus("就绪", "ok");
  } catch (error) {
    refs.taskLabStatus.textContent = `执行失败：${error.message}`;
    refs.taskLabStatus.dataset.state = "error";
    setApiStatus(`异常: ${error.message}`, "error");
  }
}

function collectorIdentityId(item) {
  return String(item?.identity_id ?? item?.id ?? "").trim();
}

function normalizeCollectorIdentity(item) {
  const identity = item && typeof item === "object" ? item : {};
  const platform = String(identity.platform || "douyin").toLowerCase() === "tiktok"
    ? "tiktok"
    : "douyin";
  const status = String(identity.status || identity.validation_status || "unknown").toLowerCase();
  return {
    identity_id: collectorIdentityId(identity),
    name: String(identity.name || identity.label || collectorIdentityId(identity) || "未命名身份"),
    platform,
    enabled: parseBooleanValue(identity.enabled, true),
    weight: Math.max(1, Number(identity.weight || 1)),
    request_delay: Math.max(0, Number(identity.request_delay ?? 6)),
    max_concurrency: Math.max(1, Number(identity.max_concurrency || 1)),
    status,
    credential_configured: parseBooleanValue(
      identity.credential_configured,
      parseBooleanValue(identity.cookie_configured, false),
    ),
    cookie_configured: parseBooleanValue(
      identity.cookie_configured,
      false,
    ),
    proxy_configured: parseBooleanValue(identity.proxy_configured, false),
    user_agent_configured: parseBooleanValue(identity.user_agent_configured, false),
    device_id_configured: parseBooleanValue(identity.device_id_configured, false),
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

function isFutureTimestamp(value) {
  if (!value) {
    return false;
  }
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) && timestamp > Date.now();
}

function collectorIdentityState(identity) {
  if (!identity.enabled) {
    return "disabled";
  }
  if (isFutureTimestamp(identity.cooldown_until) || identity.status === "cooldown") {
    return "cooldown";
  }
  if (!identity.cookie_configured) {
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
    ["cooldown", "unconfigured", "error", "unknown"].includes(collectorIdentityState(item)),
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
          <p>先为抖音或 TikTok 创建一个登录身份，再配置自动路由。</p>
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
        ${collectorCredentialChip("Cookie", identity.cookie_configured || identity.credential_configured)}
        ${collectorCredentialChip("代理", identity.proxy_configured)}
        ${tiktokChips}
      </div>
      <div class="collector-identity-timeline">
        <span>上次验证 ${escapeHtml(collectorTimeLabel(identity.last_validated_at))}</span>
        ${cooldown}
      </div>
      ${issue}
      <div class="collector-identity-actions">
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
  return `${identity.name} · ${collectorStateLabel(collectorIdentityState(identity))}`;
}

function collectorIdentityIsRoutable(identity) {
  if (!identity?.enabled || !identity.cookie_configured) {
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
  refs.collectorTikTokCredentialFields.hidden = !isTikTok;
  refs.collectorIdentityDeviceId.disabled = !isTikTok;
  refs.collectorIdentityUserAgent.disabled = !isTikTok;
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

function renderCollectorAssignments(platform = refs.collectorAssignmentPlatform.value) {
  if (refs.collectorAssignmentPlatform.value !== platform) {
    return;
  }
  const items = state.collectorAssignments[platform] || [];
  refs.collectorAssignmentList.innerHTML = "";
  refs.collectorAssignmentList.setAttribute("aria-busy", "false");
  refs.collectorBindingCount.textContent = String(items.length);
  if (!items.length) {
    refs.collectorAssignmentList.innerHTML = `
      <div class="empty-tip collector-binding-empty">
        该平台还没有账号绑定；未绑定账号会按平台策略自动选择身份。
      </div>
    `;
    refs.collectorBindingListStatus.textContent = "暂无账号绑定";
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
  refs.collectorBindingListStatus.textContent = `${collectorPlatformLabel(platform)} · ${items.length} 个账号绑定`;
}

async function loadCollectorAssignments(platform = refs.collectorAssignmentPlatform.value) {
  if (state.collectorAssignmentsLoading[platform]) {
    return;
  }
  state.collectorAssignmentsLoading[platform] = true;
  if (refs.collectorAssignmentPlatform.value === platform) {
    if (state.collectorAssignmentsLoaded[platform]) {
      renderCollectorAssignments(platform);
    }
    refs.collectorAssignmentList.setAttribute("aria-busy", "true");
    refs.collectorBindingListStatus.textContent = `正在加载${collectorPlatformLabel(platform)}账号绑定…`;
    if (!state.collectorAssignmentsLoaded[platform]) {
      refs.collectorBindingCount.textContent = "…";
      refs.collectorAssignmentList.innerHTML = '<div class="loading-state">正在读取账号绑定…</div>';
    }
  }
  try {
    const payload = await fetchJson(
      `/ui/api/collector-assignments?platform=${encodeURIComponent(platform)}&target_type=account`,
      {
        method: "GET",
        headers: headerOptions(false),
      },
    );
    state.collectorAssignments[platform] = collectorAssignmentsFromPayload(payload)
      .map((item) => normalizeCollectorAssignment(item, platform))
      .filter((item) => item.target_key && item.identity_id && item.target_type === "account");
    state.collectorAssignmentsLoaded[platform] = true;
    renderCollectorAssignments(platform);
  } catch (error) {
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
    state.collectorAssignmentsLoading[platform] = false;
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

function workflowAccountEndpoint(platform) {
  return platform === "tiktok"
    ? "/workflow/tiktok/account_batch"
    : "/workflow/douyin/account_batch";
}

function workflowDetailEndpoint(platform) {
  return platform === "tiktok"
    ? "/workflow/tiktok/detail_links"
    : "/workflow/douyin/detail_links";
}

function syncIdentityOverrideControls(identitySelect, cookieInput, proxyInput, help, contextLabel) {
  const identityId = identitySelect.value;
  const selectedIdentity = collectorIdentityById(identityId);
  const usesIdentity = Boolean(identityId);
  if (usesIdentity) {
    cookieInput.value = "";
    proxyInput.value = "";
  }
  cookieInput.disabled = usesIdentity;
  proxyInput.disabled = usesIdentity;
  cookieInput.setAttribute("aria-disabled", String(usesIdentity));
  proxyInput.setAttribute("aria-disabled", String(usesIdentity));
  if (!help) {
    return;
  }
  delete help.dataset.state;
  if (usesIdentity) {
    help.textContent = selectedIdentity
      ? `已选择“${selectedIdentity.name}”；${contextLabel}使用该身份保存的 Cookie 与代理，兼容覆盖已停用。`
      : `已选择指定身份；${contextLabel}使用身份凭据，兼容覆盖已停用。`;
    return;
  }
  if (cookieInput.value.trim() || proxyInput.value.trim()) {
    help.textContent = `已填写兼容覆盖；${contextLabel}将绕过身份池，直接使用这些临时 Cookie / 代理。`;
    help.dataset.state = "warning";
    return;
  }
  help.textContent = `${contextLabel}使用当前平台的已保存路由策略；不填写兼容覆盖时才会进入身份池。`;
}

function syncWorkflowAccountIdentityOverrides() {
  syncIdentityOverrideControls(
    refs.workflowAccountIdentity,
    refs.workflowAccountCookie,
    refs.workflowAccountProxy,
    refs.workflowAccountIdentityHelp,
    "本次批量任务",
  );
}

function syncScheduleIdentityOverrides() {
  syncIdentityOverrideControls(
    refs.scheduleIdentity,
    refs.scheduleCookie,
    refs.scheduleProxy,
    refs.scheduleIdentityHelp,
    "该定时任务",
  );
  refs.scheduleIdentityHelp.textContent = `${
    refs.scheduleIdentityHelp.textContent || ""
  } 身份异常策略只针对已配置或已路由身份；普通无 Cookie 采集不会触发暂停。`;
}

function syncWorkflowDetailIdentityOverrides() {
  syncIdentityOverrideControls(
    refs.workflowDetailIdentity,
    refs.workflowDetailCookie,
    refs.workflowDetailProxy,
    refs.workflowDetailIdentityHelp,
    "本次链接下载任务",
  );
}

function syncMonitorIdentityOverrides() {
  syncIdentityOverrideControls(
    refs.monitorIdentity,
    refs.monitorCookie,
    refs.monitorProxy,
    refs.monitorIdentityHelp,
    "该收藏夹监控",
  );
}

function selectedCollectorIdentityIsRunnable(select) {
  const identityId = select.value;
  return !identityId || collectorIdentityIsRoutable(collectorIdentityById(identityId));
}

async function runWorkflowAccountTask() {
  const platform = refs.workflowAccountPlatform.value;
  const source = refs.workflowAccountSource.value;
  if (!selectedCollectorIdentityIsRunnable(refs.workflowAccountIdentity)) {
    setCollectorStatus(
      refs.workflowAccountStatus,
      "当前选中的身份已不可路由，请改用自动路由或选择其他身份",
      "error",
    );
    refs.workflowAccountIdentity.focus();
    return;
  }
  setCollectorStatus(refs.workflowAccountStatus, "正在创建账号批量任务…");
  refs.workflowAccountSummary.textContent = "";
  try {
    const useSettings = source === "settings";
    const identityId = refs.workflowAccountIdentity.value || "";
    const payload = {
      use_settings: useSettings,
      items: useSettings
        ? []
        : collectAccountRows(platform === "tiktok" ? "tiktok" : "douyin"),
      cookie: identityId ? "" : refs.workflowAccountCookie.value.trim(),
      proxy: identityId ? "" : refs.workflowAccountProxy.value.trim(),
      identity_id: identityId,
    };
    const endpoint = workflowAccountEndpoint(platform);
    const task = await enqueueTaskRequest(endpoint, payload);
    state.selectedTaskId = task?.task_id || "";
    setCollectorStatus(refs.workflowAccountStatus, `任务已入队: ${task?.task_id || endpoint}`, "success");
    refs.workflowAccountSummary.textContent = `${task?.status || "pending"} · ${
      task?.endpoint || endpoint
    }`;
    if (task) {
      renderTaskResult(task);
    }
    await loadTaskList();
    setApiStatus("就绪", "ok");
  } catch (error) {
    setCollectorStatus(refs.workflowAccountStatus, `创建失败: ${error.message}`, "error");
    setApiStatus(`异常: ${error.message}`, "error");
  }
}

function parseWorkflowLinks(text) {
  return String(text || "")
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function detectWorkflowLinkPlatform(value) {
  const text = String(value || "");
  const hasTikTok = /(?:^|[\s/:.])(?:vm\.|vt\.|www\.)?tiktok\.com(?:[\s/?#:]|$)/i.test(text);
  const hasDouyin = /(?:^|[\s/:.])(?:(?:v|www)\.)?douyin\.com(?:[\s/?#:]|$)|iesdouyin\.com/i.test(text);
  if (hasTikTok && hasDouyin) {
    return "mixed";
  }
  if (hasTikTok) {
    return "tiktok";
  }
  if (hasDouyin) {
    return "douyin";
  }
  return "";
}

function resolveWorkflowDetailPlatform(links) {
  const selected = refs.workflowDetailPlatform.value;
  if (selected === "douyin" || selected === "tiktok") {
    return { platform: selected, error: "" };
  }
  const detected = new Set();
  for (const link of links) {
    const platform = detectWorkflowLinkPlatform(link);
    if (platform === "mixed") {
      detected.add("douyin");
      detected.add("tiktok");
    } else if (platform) {
      detected.add(platform);
    }
  }
  if (detected.size > 1) {
    return {
      platform: "",
      error: "检测到抖音和 TikTok 链接，请按平台分两批提交",
    };
  }
  if (detected.size === 0) {
    return {
      platform: "",
      error: "暂时无法识别平台，请手动选择抖音或 TikTok",
    };
  }
  return { platform: Array.from(detected)[0], error: "" };
}

function workflowPlatformLabel(platform) {
  return platform === "tiktok" ? "TikTok" : "抖音";
}

function setWorkflowDetailStatus(text, kind = "") {
  refs.workflowDetailStatus.textContent = text;
  if (kind) {
    refs.workflowDetailStatus.dataset.state = kind;
  } else {
    delete refs.workflowDetailStatus.dataset.state;
  }
}

function syncWorkflowDetailIdentitySelector() {
  const links = parseWorkflowLinks(refs.workflowDetailLinks.value);
  const resolution = resolveWorkflowDetailPlatform(links);
  const platform = resolution.error ? "" : resolution.platform;
  populateCollectorIdentitySelect(
    refs.workflowDetailIdentity,
    platform,
    platform ? "自动路由" : "自动路由（识别平台后可选）",
    { preserveUnavailable: true },
  );
  syncWorkflowDetailIdentityOverrides();
}

function syncWorkflowDetailInputState() {
  const links = parseWorkflowLinks(refs.workflowDetailLinks.value);
  syncWorkflowDetailIdentitySelector();
  if (refs.workflowDetailStatus.dataset.state) {
    setWorkflowDetailStatus(links.length ? "等待提交" : "等待输入");
    refs.workflowDetailSummary.textContent = "";
  }
  if (!links.length) {
    refs.workflowDetailCount.textContent = "等待输入链接";
    return;
  }
  const resolution = resolveWorkflowDetailPlatform(links);
  if (resolution.error) {
    refs.workflowDetailCount.textContent = `${links.length} 条 · ${resolution.error}`;
    return;
  }
  const mode = refs.workflowDetailPlatform.value === "auto" ? "已识别" : "已指定";
  refs.workflowDetailCount.textContent = `${links.length} 条 · ${mode} ${workflowPlatformLabel(
    resolution.platform,
  )}`;
}

async function runWorkflowDetailTask() {
  const links = parseWorkflowLinks(refs.workflowDetailLinks.value);
  if (!links.length) {
    setWorkflowDetailStatus("请至少输入一条链接", "error");
    refs.workflowDetailSummary.textContent = "";
    return;
  }
  const resolution = resolveWorkflowDetailPlatform(links);
  if (resolution.error) {
    setWorkflowDetailStatus(resolution.error, "error");
    refs.workflowDetailSummary.textContent = "";
    return;
  }
  const platform = resolution.platform;
  if (!selectedCollectorIdentityIsRunnable(refs.workflowDetailIdentity)) {
    setWorkflowDetailStatus(
      "当前选中的身份已不可路由，请改用自动路由或选择其他身份",
      "error",
    );
    refs.workflowDetailIdentity.focus();
    return;
  }
  setWorkflowDetailStatus("正在创建链接下载任务…");
  refs.workflowDetailSummary.textContent = "";
  try {
    const endpoint = workflowDetailEndpoint(platform);
    const identityId = refs.workflowDetailIdentity.value || "";
    const payload = {
      links,
      identity_id: identityId,
      cookie: identityId ? "" : refs.workflowDetailCookie.value.trim(),
      proxy: identityId ? "" : refs.workflowDetailProxy.value.trim(),
    };
    const task = await enqueueTaskRequest(endpoint, payload);
    state.selectedTaskId = task?.task_id || "";
    setWorkflowDetailStatus(`任务已入队: ${task?.task_id || endpoint}`, "success");
    refs.workflowDetailSummary.textContent = `${workflowPlatformLabel(platform)} · ${
      task?.status || "pending"
    } · ${
      task?.endpoint || endpoint
    } · ${links.length} 条链接`;
    if (task) {
      renderTaskResult(task);
    }
    await loadTaskList();
    setApiStatus("就绪", "ok");
  } catch (error) {
    setWorkflowDetailStatus(`创建失败: ${error.message}`, "error");
    setApiStatus(`异常: ${error.message}`, "error");
  }
}

function schedulePayloadFromForm() {
  const platform = refs.schedulePlatform.value;
  const useSettings = refs.scheduleSource.value === "settings";
  const identityId = refs.scheduleIdentity.value || "";
  return {
    name: refs.scheduleName.value.trim(),
    platform,
    use_settings: useSettings,
    items: useSettings
      ? []
      : collectAccountRows(platform === "tiktok" ? "tiktok" : "douyin"),
    hour: Number(refs.scheduleHour.value || 0),
    minute: Number(refs.scheduleMinute.value || 0),
    identity_id: identityId,
    cookie: identityId ? "" : refs.scheduleCookie.value.trim(),
    proxy: identityId ? "" : refs.scheduleProxy.value.trim(),
    uptime_kuma_url: refs.scheduleUptimeKumaUrl?.value.trim(),
    bark_url: refs.scheduleBarkUrl?.value.trim(),
    overlap_policy: refs.scheduleOverlapPolicy?.value || "wait",
    identity_failure_action: refs.scheduleIdentityFailureAction?.value || "continue",
    identity_failure_threshold: Math.max(
      1,
      Math.min(Number(refs.scheduleIdentityFailureThreshold?.value || 3), 20),
    ),
    notify_on_identity_failure: Boolean(refs.scheduleNotifyIdentityFailure?.checked),
    enabled: true,
  };
}

function collectorIdentityReferenceLabel(identityId) {
  if (!identityId) {
    return "自动路由";
  }
  const identity = collectorIdentityById(identityId);
  if (!identity) {
    return `${identityId}（身份已不存在）`;
  }
  return collectorIdentityIsRoutable(identity)
    ? `${identity.name} · ${identity.identity_id}`
    : `${identity.name} · ${identity.identity_id}（当前不可路由）`;
}

function renderScheduleList(items) {
  if (!refs.scheduleList) {
    return;
  }
  refs.scheduleList.innerHTML = "";
  if (!Array.isArray(items) || !items.length) {
    refs.scheduleList.innerHTML =
      '<div class="task-row"><div class="task-main"><span class="task-endpoint">暂无定时任务</span></div></div>';
    return;
  }
  const fragment = document.createDocumentFragment();
  items.forEach((item) => {
    const isEnabled = parseBooleanValue(item.enabled, false);
    const scheduleId = String(item.schedule_id || "");
    const hour = Number.isFinite(Number(item.hour)) ? Number(item.hour) : 0;
    const minute = Number.isFinite(Number(item.minute)) ? Number(item.minute) : 0;
    const overlapLabels = {
      wait: "等待上次完成",
      skip: "重叠时跳过",
      allow: "允许并行",
    };
    const overlapLabel = overlapLabels[item.overlap_policy] || overlapLabels.wait;
    const identityFailureLabel =
      item.identity_failure_action === "pause"
        ? `身份连续失败 ${Number(item.identity_failure_threshold || 3)} 次时暂停`
        : "身份异常时继续";
    const row = document.createElement("div");
    row.className = "task-row";
    row.innerHTML = `
      <span class="task-status ${isEnabled ? "success" : "canceled"}">${
      isEnabled ? "enabled" : "disabled"
    }</span>
      <div class="task-main">
        <span class="task-id">${escapeHtml(scheduleId || "-")}</span>
        <span class="task-endpoint">${escapeHtml(item.name || "-")} · ${escapeHtml(
      item.platform || "-",
    )}</span>
        <span class="task-time">每日 ${String(hour).padStart(2, "0")}:${String(
      minute,
    ).padStart(2, "0")} · ${escapeHtml(overlapLabel)} · ${escapeHtml(
      identityFailureLabel,
    )} · 身份 ${escapeHtml(
      collectorIdentityReferenceLabel(item.identity_id),
    )} · 最近任务 ${escapeHtml(item.last_task_id || "-")} · 下次 ${escapeHtml(
      item.next_run_at || "-",
    )}</span>
      </div>
      <div class="task-actions">
        <button class="btn ghost" type="button" data-action="run">立即执行</button>
        <button class="btn ghost" type="button" data-action="toggle">${
          isEnabled ? "停用" : "启用"
        }</button>
        <button class="btn ghost danger" type="button" data-action="delete">删除</button>
      </div>
    `;
    row.querySelector('[data-action="run"]')?.addEventListener("click", () => {
      runScheduleNow(scheduleId);
    });
    row.querySelector('[data-action="toggle"]')?.addEventListener("click", () => {
      toggleSchedule(scheduleId, !isEnabled);
    });
    row.querySelector('[data-action="delete"]')?.addEventListener("click", () => {
      deleteSchedule(scheduleId);
    });
    fragment.appendChild(row);
  });
  refs.scheduleList.appendChild(fragment);
}

async function loadSchedules() {
  try {
    const payload = await fetchJson("/ui/api/schedules", {
      method: "GET",
      headers: headerOptions(false),
    });
    state.settingsData.ui_schedules = payload.items || [];
    renderScheduleList(payload.items || []);
  } catch (error) {
    refs.scheduleStatus.textContent = `加载定时任务失败: ${error.message}`;
  }
}

async function createSchedule() {
  if (!selectedCollectorIdentityIsRunnable(refs.scheduleIdentity)) {
    setCollectorStatus(
      refs.scheduleStatus,
      "当前选中的身份已不可路由，请改用自动路由或选择其他身份",
      "error",
    );
    refs.scheduleIdentity.focus();
    return;
  }
  setCollectorStatus(refs.scheduleStatus, "正在创建定时任务…");
  try {
    const payload = schedulePayloadFromForm();
    await fetchJson("/ui/api/schedules", {
      method: "POST",
      headers: headerOptions(true),
      body: JSON.stringify(payload),
    });
    setCollectorStatus(refs.scheduleStatus, "定时任务创建成功", "success");
    await loadSchedules();
    setApiStatus("就绪", "ok");
  } catch (error) {
    setCollectorStatus(refs.scheduleStatus, `创建失败: ${error.message}`, "error");
    setApiStatus(`异常: ${error.message}`, "error");
  }
}

async function toggleSchedule(scheduleId, enabled) {
  try {
    await fetchJson(`/ui/api/schedules/${encodeURIComponent(scheduleId)}/toggle`, {
      method: "POST",
      headers: headerOptions(true),
      body: JSON.stringify({ enabled }),
    });
    await loadSchedules();
    refs.scheduleStatus.textContent = "定时任务状态已更新";
  } catch (error) {
    refs.scheduleStatus.textContent = `更新失败: ${error.message}`;
  }
}

async function runScheduleNow(scheduleId) {
  try {
    const result = await fetchJson(`/ui/api/schedules/${encodeURIComponent(scheduleId)}/run`, {
      method: "POST",
      headers: headerOptions(false),
    });
    if (result.overlap_action === "enqueue") {
      refs.scheduleStatus.textContent = `已触发执行: ${result.task?.task_id || scheduleId}`;
    } else if (result.overlap_action === "skip") {
      refs.scheduleStatus.textContent = `已有任务 ${result.task?.task_id || "-"}，本次已跳过`;
    } else {
      refs.scheduleStatus.textContent = `已有任务 ${
        result.task?.task_id || "-"
      }，未创建重复任务`;
    }
    if (result?.task) {
      renderTaskResult(result.task);
      await loadTaskList();
    }
  } catch (error) {
    refs.scheduleStatus.textContent = `触发失败: ${error.message}`;
  }
}

async function deleteSchedule(scheduleId) {
  try {
    await fetchJson(`/ui/api/schedules/${encodeURIComponent(scheduleId)}`, {
      method: "DELETE",
      headers: headerOptions(false),
    });
    refs.scheduleStatus.textContent = "定时任务已删除";
    await loadSchedules();
  } catch (error) {
    refs.scheduleStatus.textContent = `删除失败: ${error.message}`;
  }
}

function collectMonitorPayloadFromForm() {
  const identityId = refs.monitorIdentity.value || "";
  return {
    name: refs.monitorName.value.trim(),
    collect_id: refs.monitorCollectId.value.trim(),
    interval_minutes: Number(refs.monitorInterval.value || 30),
    limit: Number(refs.monitorLimit.value || 10),
    default_tab: refs.monitorDefaultTab.value || "post",
    default_earliest: refs.monitorDefaultEarliest.value.trim(),
    default_latest: refs.monitorDefaultLatest.value.trim(),
    bark_url: refs.monitorBarkUrl.value.trim(),
    identity_id: identityId,
    cookie: identityId ? "" : refs.monitorCookie.value.trim(),
    proxy: identityId ? "" : refs.monitorProxy.value.trim(),
    enabled: refs.monitorEnabled.checked,
    account_enable: refs.monitorAccountEnable.checked,
    immediate_crawl: refs.monitorImmediateCrawl.checked,
    default_auto_update_earliest: refs.monitorAutoUpdateEarliest.checked,
  };
}

function renderCollectMonitorList(items) {
  if (!refs.monitorList) {
    return;
  }
  refs.monitorList.innerHTML = "";
  if (!Array.isArray(items) || !items.length) {
    refs.monitorList.innerHTML =
      '<div class="task-row"><div class="task-main"><span class="task-endpoint">暂无收藏夹监控</span></div></div>';
    return;
  }
  const fragment = document.createDocumentFragment();
  items.forEach((item) => {
    const lastResult = item?.last_result && typeof item.last_result === "object" ? item.last_result : {};
    const isEnabled = parseBooleanValue(item.enabled, false);
    const scheduleId = String(item.schedule_id || "");
    const statusTag = isEnabled ? "enabled" : "disabled";
    const row = document.createElement("div");
    row.className = "task-row";
    row.innerHTML = `
      <span class="task-status ${isEnabled ? "success" : "canceled"}">${statusTag}</span>
      <div class="task-main">
        <span class="task-id">${escapeHtml(scheduleId || "-")}</span>
        <span class="task-endpoint">${escapeHtml(item.name || "-")} · collect_id=${escapeHtml(
      item.collect_id || "-",
    )}</span>
        <span class="task-time">
          间隔 ${escapeHtml(item.interval_minutes || "-")} 分钟 · limit ${escapeHtml(
      item.limit || "-",
    )} · 下次 ${escapeHtml(item.next_run_at || "-")}
        </span>
        <span class="task-time">
          上次 ${escapeHtml(item.last_run_at || "-")} · 新增 ${escapeHtml(
      lastResult.added_accounts || 0,
    )} · 去重 ${escapeHtml(lastResult.duplicate_accounts || 0)}
        </span>
        <span class="task-time">身份 ${escapeHtml(
          collectorIdentityReferenceLabel(item.identity_id),
        )}</span>
      </div>
      <div class="task-actions">
        <button class="btn ghost" type="button" data-action="run">立即执行</button>
        <button class="btn ghost" type="button" data-action="toggle">${isEnabled ? "停用" : "启用"}</button>
        <button class="btn ghost danger" type="button" data-action="delete">删除</button>
      </div>
    `;
    row.querySelector('[data-action="run"]')?.addEventListener("click", () => {
      runCollectMonitorNow(scheduleId);
    });
    row.querySelector('[data-action="toggle"]')?.addEventListener("click", () => {
      toggleCollectMonitor(scheduleId, !isEnabled);
    });
    row.querySelector('[data-action="delete"]')?.addEventListener("click", () => {
      deleteCollectMonitor(scheduleId);
    });
    fragment.appendChild(row);
  });
  refs.monitorList.appendChild(fragment);
}

async function loadCollectMonitors() {
  try {
    const payload = await fetchJson("/ui/api/collect-monitors", {
      method: "GET",
      headers: headerOptions(false),
    });
    state.collectMonitorItems = payload.items || [];
    renderCollectMonitorList(state.collectMonitorItems);
  } catch (error) {
    refs.monitorStatus.textContent = `加载监控失败: ${error.message}`;
  }
}

async function createCollectMonitor() {
  if (!selectedCollectorIdentityIsRunnable(refs.monitorIdentity)) {
    refs.monitorStatus.textContent = "当前选中的身份已不可路由，请改用自动路由或选择其他身份";
    refs.monitorIdentity.focus();
    return;
  }
  refs.monitorStatus.textContent = "正在创建收藏夹监控…";
  try {
    const payload = collectMonitorPayloadFromForm();
    await fetchJson("/ui/api/collect-monitors", {
      method: "POST",
      headers: headerOptions(true),
      body: JSON.stringify(payload),
    });
    refs.monitorStatus.textContent = "收藏夹监控创建成功";
    await loadCollectMonitors();
    setApiStatus("就绪", "ok");
  } catch (error) {
    refs.monitorStatus.textContent = `创建失败: ${error.message}`;
    setApiStatus(`异常: ${error.message}`, "error");
  }
}

async function toggleCollectMonitor(scheduleId, enabled) {
  try {
    await fetchJson(`/ui/api/collect-monitors/${encodeURIComponent(scheduleId)}/toggle`, {
      method: "POST",
      headers: headerOptions(true),
      body: JSON.stringify({ enabled }),
    });
    refs.monitorStatus.textContent = "监控状态已更新";
    await loadCollectMonitors();
  } catch (error) {
    refs.monitorStatus.textContent = `更新失败: ${error.message}`;
  }
}

async function runCollectMonitorNow(scheduleId) {
  try {
    const payload = await fetchJson(`/ui/api/collect-monitors/${encodeURIComponent(scheduleId)}/run`, {
      method: "POST",
      headers: headerOptions(false),
    });
    const result = payload?.result || {};
    if (result.ok) {
      refs.monitorStatus.textContent = `执行完成: 新增 ${result.added_accounts || 0} · 去重 ${result.duplicate_accounts || 0}`;
    } else {
      refs.monitorStatus.textContent = `执行失败: ${result.error || "unknown"}`;
    }
    await loadCollectMonitors();
    if (payload?.result?.immediate_result) {
      refs.workflowAccountSummary.textContent = `监控触发下载: ${payload.result.immediate_result.message || "-"}`;
    }
  } catch (error) {
    refs.monitorStatus.textContent = `触发失败: ${error.message}`;
  }
}

async function deleteCollectMonitor(scheduleId) {
  try {
    await fetchJson(`/ui/api/collect-monitors/${encodeURIComponent(scheduleId)}`, {
      method: "DELETE",
      headers: headerOptions(false),
    });
    refs.monitorStatus.textContent = "监控已删除";
    await loadCollectMonitors();
  } catch (error) {
    refs.monitorStatus.textContent = `删除失败: ${error.message}`;
  }
}

function formatWorkflowAccountSummary(task) {
  const endpoint = String(task?.endpoint || "");
  if (!endpoint.endsWith("/account_batch")) {
    return "";
  }
  const result = task?.result;
  const data = result && typeof result === "object" ? result.data : null;
  if (!data || typeof data !== "object") {
    return `${task?.status || "-"} · ${endpoint}`;
  }
  const parts = [task?.status || "-"];
  const numericFields = [
    ["total", "total"],
    ["queued", "queued"],
    ["success", "success"],
    ["failed", "failed"],
    ["skipped", "skipped"],
  ];
  for (const [key, label] of numericFields) {
    const value = Number(data[key]);
    if (Number.isFinite(value) && value >= 0) {
      parts.push(`${label} ${value}`);
    }
  }
  const markBackfilled = Number(data.mark_backfilled);
  if (Number.isFinite(markBackfilled) && markBackfilled > 0) {
    parts.push(`mark回填 ${markBackfilled}`);
  }
  const earliestUpdated = Number(data.earliest_updated);
  if (Number.isFinite(earliestUpdated) && earliestUpdated > 0) {
    parts.push(`earliest更新 ${earliestUpdated}`);
  }
  return parts.join(" · ");
}

const TASK_STATUS_LABELS = {
  pending: "排队中",
  running: "执行中",
  pausing: "暂停中",
  paused: "已暂停",
  canceling: "取消中",
  canceled: "已取消",
  success: "成功",
  failed: "失败",
};

function taskStatusLabel(status) {
  const normalized = String(status || "");
  return TASK_STATUS_LABELS[normalized] || normalized || "未知";
}

function normalizeTaskProgress(task) {
  const progress = task?.progress && typeof task.progress === "object" ? task.progress : {};
  const total = Math.max(0, Number(progress.total || 0));
  const current = Math.max(0, Math.min(total || Number.MAX_SAFE_INTEGER, Number(progress.current || 0)));
  const percent = total
    ? Math.max(0, Math.min(100, Number(progress.percent ?? Math.round((current * 100) / total))))
    : 0;
  return {
    current,
    total,
    percent,
    success: Math.max(0, Number(progress.success || 0)),
    failed: Math.max(0, Number(progress.failed || 0)),
    skipped: Math.max(0, Number(progress.skipped || 0)),
    label: String(progress.label || ""),
  };
}

function renderTaskProgress(task) {
  const progress = normalizeTaskProgress(task);
  const visible = progress.total > 0;
  refs.taskProgressBlock.hidden = !visible;
  if (!visible) {
    return;
  }
  refs.taskProgress.value = progress.percent;
  refs.taskProgress.textContent = `${progress.percent}%`;
  refs.taskProgressLabel.textContent = progress.label || taskStatusLabel(task.status);
  refs.taskProgressValue.textContent = `${progress.current} / ${progress.total}`;
  refs.taskProgressMeta.textContent = `成功 ${progress.success} · 失败 ${progress.failed} · 跳过 ${progress.skipped} · ${progress.percent}%`;
}

const TASK_ACCOUNT_STATUS_LABELS = {
  pending: "等待",
  running: "执行中",
  success: "成功",
  failed: "失败",
  skipped: "跳过",
};

function renderTaskAccountSummary(task) {
  const isAccountBatch = String(task?.endpoint || "").endsWith("/account_batch");
  refs.taskAccountCheckpoints.hidden = !isAccountBatch;
  if (!isAccountBatch) {
    refs.taskAccountList.innerHTML = "";
    return;
  }
  const summary =
    task?.account_summary && typeof task.account_summary === "object"
      ? task.account_summary
      : {};
  const total = Number(summary.total || 0);
  refs.taskAccountSummary.textContent = total
    ? `共 ${total} · 成功 ${Number(summary.success || 0)} · 失败 ${Number(
        summary.failed || 0,
      )} · 等待 ${Number(summary.pending || 0)}`
    : "任务开始后生成账号快照";
}

function renderTaskAccounts(payload) {
  const items = Array.isArray(payload?.items) ? payload.items : [];
  refs.taskAccountList.innerHTML = "";
  if (!items.length) {
    refs.taskAccountList.innerHTML =
      '<div class="empty-state">当前任务还没有账号检查点。</div>';
    return;
  }
  const fragment = document.createDocumentFragment();
  for (const account of items) {
    const row = document.createElement("div");
    const status = String(account.status || "pending");
    const item = account.item && typeof account.item === "object" ? account.item : {};
    row.className = "task-account-row";
    row.innerHTML = `
      <span class="task-status ${escapeHtml(status)}">${escapeHtml(
        TASK_ACCOUNT_STATUS_LABELS[status] || status,
      )}</span>
      <span class="task-account-position">#${Number(account.position || 0)}</span>
      <span class="task-account-name">${escapeHtml(item.mark || item.url || "未命名账号")}</span>
      <span class="task-account-reason">${escapeHtml(
        account.reason || account.identity_id || "",
      )}</span>
    `;
    fragment.appendChild(row);
  }
  refs.taskAccountList.appendChild(fragment);
}

async function loadTaskAccounts(taskId = state.selectedTaskId) {
  if (!taskId || state.taskAccountsLoading) {
    return;
  }
  state.taskAccountsLoading = true;
  refs.taskAccountList.setAttribute("aria-busy", "true");
  refs.taskAccountList.innerHTML = '<div class="loading-state">正在加载账号检查点…</div>';
  try {
    const payload = await fetchJson(
      `/ui/api/tasks/${encodeURIComponent(taskId)}/accounts?limit=100`,
      {
        method: "GET",
        headers: headerOptions(false),
      },
    );
    if (state.selectedTaskId !== taskId) {
      return;
    }
    renderTaskAccounts(payload);
    const summary = payload?.summary || {};
    refs.taskAccountSummary.textContent = `共 ${Number(
      summary.total || 0,
    )} · 成功 ${Number(summary.success || 0)} · 失败 ${Number(
      summary.failed || 0,
    )} · 等待 ${Number(summary.pending || 0)}`;
  } catch (error) {
    refs.taskAccountList.innerHTML = `<div class="error-state">检查点加载失败：${escapeHtml(
      error.message,
    )}</div>`;
  } finally {
    state.taskAccountsLoading = false;
    refs.taskAccountList.setAttribute("aria-busy", "false");
  }
}

function syncSelectedTaskRow() {
  refs.taskQueueList.querySelectorAll(".task-row[data-task-id]").forEach((row) => {
    const selected = row.dataset.taskId === state.selectedTaskId;
    row.classList.toggle("active", selected);
    const mainButton = row.querySelector(".task-main-button");
    if (mainButton) {
      mainButton.setAttribute("aria-current", selected ? "true" : "false");
    }
  });
}

function renderTaskResult(task) {
  if (!task) {
    return;
  }
  state.selectedTaskId = task.task_id || "";
  const status = String(task.status || "");
  refs.taskSummary.textContent = `${task.task_id || "-"} · ${taskStatusLabel(status)} · ${
    task.endpoint || "-"
  }`;
  refs.taskStatus.textContent =
    task.message || task.error || `任务状态：${taskStatusLabel(status)}`;
  renderTaskProgress(task);
  renderTaskAccountSummary(task);
  if (["failed", "canceled"].includes(status)) {
    refs.taskStatus.dataset.state = "error";
  } else if (status === "success") {
    refs.taskStatus.dataset.state = "success";
  } else {
    delete refs.taskStatus.dataset.state;
  }
  syncSelectedTaskRow();
  const workflowSummary = formatWorkflowAccountSummary(task);
  if (workflowSummary && refs.workflowAccountSummary) {
    refs.workflowAccountSummary.textContent = workflowSummary;
  }
  if (workflowSummary && refs.workflowAccountStatus && task.message) {
    refs.workflowAccountStatus.textContent = task.message;
  }
  if (typeof task.result !== "undefined" && task.result !== null) {
    refs.taskResult.textContent = JSON.stringify(task.result, null, 2);
    return;
  }
  if (task.error) {
    refs.taskResult.textContent = JSON.stringify(
      {
        error: task.error,
      },
      null,
      2,
    );
    return;
  }
  refs.taskResult.textContent = "暂无结果";
}

async function taskControl(taskId, action) {
  try {
    const result = await fetchJson(`/ui/api/tasks/${encodeURIComponent(taskId)}/${action}`, {
      method: "POST",
      headers: headerOptions(false),
    });
    if (result?.task) {
      renderTaskResult(result.task);
    }
    await loadTaskList();
    setApiStatus("就绪", "ok");
  } catch (error) {
    const actionLabel =
      {
        pause: "暂停",
        resume: "继续",
        cancel: "取消",
        retry: "重试",
        "retry-failed": "仅重试失败账号",
      }[action] || "操作";
    refs.taskStatus.textContent = `${actionLabel}失败：${error.message}`;
    refs.taskStatus.dataset.state = "error";
    setApiStatus(`异常: ${error.message}`, "error");
  }
}

function renderTaskList(items) {
  const previousScrollTop = refs.taskQueueList.scrollTop;
  const activeElement = document.activeElement;
  const focusedRow = activeElement?.closest?.(".task-row[data-task-id]");
  const focusedTaskId = focusedRow?.dataset.taskId || "";
  const focusedTaskAction = activeElement?.dataset?.taskAction || "";
  refs.taskQueueList.innerHTML = "";
  if (!Array.isArray(items) || !items.length) {
    const emptyState = document.createElement("div");
    emptyState.className = "empty-state";
    emptyState.textContent = "还没有任务。粘贴作品链接后，任务会显示在这里。";
    refs.taskQueueList.appendChild(emptyState);
    return;
  }
  const fragment = document.createDocumentFragment();
  for (const task of items) {
    const taskStatus = String(task.status || "");
    const taskStatusClass = taskStatus.replace(/[^a-z0-9_-]/gi, "");
    const row = document.createElement("div");
    row.className = "task-row";
    row.dataset.taskId = task.task_id || "";
    row.classList.toggle("active", row.dataset.taskId === state.selectedTaskId);

    const status = document.createElement("span");
    status.className = `task-status ${taskStatusClass}`;
    status.textContent = taskStatusLabel(taskStatus);

    const main = document.createElement("button");
    main.type = "button";
    main.className = "task-main task-main-button";
    main.dataset.taskAction = "main";
    main.setAttribute(
      "aria-label",
      `查看任务 ${task.endpoint || "未知端点"}，状态${taskStatusLabel(taskStatus)}`,
    );
    main.setAttribute(
      "aria-current",
      row.dataset.taskId === state.selectedTaskId ? "true" : "false",
    );
    main.innerHTML = `
      <span class="task-id">${escapeHtml(task.task_id || "-")}</span>
      <span class="task-endpoint">${escapeHtml(task.endpoint || "-")}</span>
      <span class="task-time">${escapeHtml(task.updated_at || task.created_at || "")}</span>
    `;
    const progress = normalizeTaskProgress(task);
    if (progress.total > 0) {
      const progressRow = document.createElement("span");
      progressRow.className = "task-row-progress";
      progressRow.innerHTML = `
        <span class="task-row-progress-track" aria-hidden="true">
          <span style="width: ${progress.percent}%"></span>
        </span>
        <span>${progress.current}/${progress.total}</span>
      `;
      main.appendChild(progressRow);
    }
    main.addEventListener("click", () => {
      renderTaskResult(task);
    });

    const actions = document.createElement("div");
    actions.className = "task-actions";

    const viewBtn = document.createElement("button");
    viewBtn.type = "button";
    viewBtn.className = "btn ghost";
    viewBtn.dataset.taskAction = "view";
    viewBtn.textContent = "查看";
    viewBtn.addEventListener("click", () => {
      renderTaskResult(task);
    });
    actions.appendChild(viewBtn);

    if (taskStatus === "running" && task.pause_supported) {
      const pauseBtn = document.createElement("button");
      pauseBtn.type = "button";
      pauseBtn.className = "btn ghost";
      pauseBtn.dataset.taskAction = "pause";
      pauseBtn.textContent = "暂停";
      pauseBtn.title = "当前账号完成后安全暂停";
      pauseBtn.addEventListener("click", () => {
        withBusyButton(pauseBtn, "暂停中", () => taskControl(task.task_id, "pause"));
      });
      actions.appendChild(pauseBtn);
    }

    if (["pausing", "paused"].includes(taskStatus)) {
      const resumeBtn = document.createElement("button");
      resumeBtn.type = "button";
      resumeBtn.className = "btn ghost";
      resumeBtn.dataset.taskAction = "resume";
      resumeBtn.textContent = "继续";
      resumeBtn.addEventListener("click", () => {
        withBusyButton(resumeBtn, "继续中", () => taskControl(task.task_id, "resume"));
      });
      actions.appendChild(resumeBtn);
    }

    if (["pending", "running", "pausing", "paused"].includes(taskStatus)) {
      const cancelBtn = document.createElement("button");
      cancelBtn.type = "button";
      cancelBtn.className = "btn ghost";
      cancelBtn.dataset.taskAction = "cancel";
      cancelBtn.textContent = "取消";
      cancelBtn.addEventListener("click", () => {
        withBusyButton(cancelBtn, "取消中", () => taskControl(task.task_id, "cancel"));
      });
      actions.appendChild(cancelBtn);
    } else if (taskStatus === "canceling") {
      const cancelingBtn = document.createElement("button");
      cancelingBtn.type = "button";
      cancelingBtn.className = "btn ghost";
      cancelingBtn.dataset.taskAction = "cancel";
      cancelingBtn.textContent = "取消中";
      cancelingBtn.disabled = true;
      actions.appendChild(cancelingBtn);
    } else if (["failed", "canceled"].includes(taskStatus)) {
      const retryBtn = document.createElement("button");
      retryBtn.type = "button";
      retryBtn.className = "btn ghost";
      retryBtn.dataset.taskAction = "retry";
      retryBtn.textContent = "全部重试";
      retryBtn.addEventListener("click", () => {
        withBusyButton(retryBtn, "重试中", () => taskControl(task.task_id, "retry"));
      });
      actions.appendChild(retryBtn);
    }
    const failedCheckpoints = Number(task?.account_summary?.failed || 0);
    if (
      failedCheckpoints > 0 &&
      ["success", "failed", "canceled"].includes(taskStatus)
    ) {
      const retryFailedBtn = document.createElement("button");
      retryFailedBtn.type = "button";
      retryFailedBtn.className = "btn ghost";
      retryFailedBtn.dataset.taskAction = "retry-failed";
      retryFailedBtn.textContent = `重试失败项 (${failedCheckpoints})`;
      retryFailedBtn.addEventListener("click", () => {
        withBusyButton(retryFailedBtn, "创建中", () =>
          taskControl(task.task_id, "retry-failed"),
        );
      });
      actions.appendChild(retryFailedBtn);
    }

    row.appendChild(status);
    row.appendChild(main);
    row.appendChild(actions);
    fragment.appendChild(row);
  }
  refs.taskQueueList.appendChild(fragment);
  refs.taskQueueList.scrollTop = previousScrollTop;
  if (focusedTaskId) {
    const nextFocusedRow = Array.from(
      refs.taskQueueList.querySelectorAll(".task-row[data-task-id]"),
    ).find((row) => row.dataset.taskId === focusedTaskId);
    const matchingAction = Array.from(
      nextFocusedRow?.querySelectorAll("[data-task-action]") || [],
    ).find(
      (element) =>
        element.dataset.taskAction === focusedTaskAction && !element.disabled,
    );
    const focusTarget = matchingAction || nextFocusedRow?.querySelector(".task-main-button");
    focusTarget?.focus({ preventScroll: true });
  }
}

function renderTaskListError(message) {
  refs.taskQueueList.innerHTML = "";
  const errorState = document.createElement("div");
  errorState.className = "error-state";
  const errorText = document.createElement("span");
  errorText.textContent = `任务加载失败：${message}`;
  const retryBtn = document.createElement("button");
  retryBtn.type = "button";
  retryBtn.className = "btn ghost";
  retryBtn.textContent = "重试";
  retryBtn.addEventListener("click", () => {
    withBusyButton(retryBtn, "重试中", loadTaskList);
  });
  errorState.appendChild(errorText);
  errorState.appendChild(retryBtn);
  refs.taskQueueList.appendChild(errorState);
}

async function loadTaskList() {
  if (state.taskListLoading) {
    return;
  }
  state.taskListLoading = true;
  refs.taskQueueList.setAttribute("aria-busy", "true");
  try {
    const payload = await fetchJson("/ui/api/tasks?limit=120", {
      method: "GET",
      headers: headerOptions(false),
    });
    const items = payload?.items || [];
    renderTaskList(items);
    const counts = items.reduce(
      (summary, task) => {
        const status = String(task.status || "");
        if (["pending", "running", "pausing", "canceling"].includes(status)) {
          summary.active += 1;
        } else if (status === "paused") {
          summary.paused += 1;
        } else if (status === "success") {
          summary.success += 1;
        } else if (["failed", "canceled"].includes(status)) {
          summary.failed += 1;
        }
        return summary;
      },
      { active: 0, paused: 0, success: 0, failed: 0 },
    );
    refs.taskQueueMeta.textContent = `任务: ${payload?.count ?? items.length} · 进行中 ${
      counts.active
    } · 已暂停 ${counts.paused} · 成功 ${counts.success} · 失败/取消 ${counts.failed}`;
    if (state.selectedTaskId) {
      const selected = items.find((item) => item.task_id === state.selectedTaskId);
      if (selected) {
        renderTaskResult(selected);
      }
    }
  } catch (error) {
    refs.taskQueueMeta.textContent = "任务: 0 · 队列暂时无法加载";
    renderTaskListError(error.message);
    setApiStatus(`异常: ${error.message}`, "error");
  } finally {
    state.taskListLoading = false;
    refs.taskQueueList.setAttribute("aria-busy", "false");
  }
}

async function copyTaskResult() {
  const text = refs.taskResult.textContent?.trim();
  if (!text) {
    refs.taskStatus.textContent = "暂无可复制内容";
    return;
  }
  try {
    await navigator.clipboard.writeText(text);
    refs.taskStatus.textContent = "结果已复制";
  } catch (error) {
    refs.taskStatus.textContent = `复制失败: ${error.message}`;
  }
}

function bindEvents() {
  refs.sidebarToggleBtn?.addEventListener("click", () => {
    const collapsed = !document.querySelector(".app-shell")?.classList.contains("sidebar-collapsed");
    applySidebarCollapsed(collapsed);
    window.requestAnimationFrame(() => applyBoardColumns(false));
  });

  refs.tabButtons.forEach((button, index) => {
    button.addEventListener("click", () => {
      switchTab(button.dataset.tabTarget || "workbench");
    });
    button.addEventListener("keydown", (event) => {
      if (!["ArrowDown", "ArrowRight", "ArrowUp", "ArrowLeft", "Home", "End"].includes(event.key)) {
        return;
      }
      event.preventDefault();
      let nextIndex = index;
      if (["ArrowDown", "ArrowRight"].includes(event.key)) {
        nextIndex = (index + 1) % refs.tabButtons.length;
      } else if (["ArrowUp", "ArrowLeft"].includes(event.key)) {
        nextIndex = (index - 1 + refs.tabButtons.length) % refs.tabButtons.length;
      } else if (event.key === "Home") {
        nextIndex = 0;
      } else if (event.key === "End") {
        nextIndex = refs.tabButtons.length - 1;
      }
      const nextButton = refs.tabButtons[nextIndex];
      switchTab(nextButton.dataset.tabTarget || "workbench");
      nextButton.focus();
    });
  });

  refs.applyTokenBtn.addEventListener("click", () => {
    withBusyButton(refs.applyTokenBtn, "应用中", async () => {
      const nextToken = refs.tokenInput.value.trim();
      state.token = nextToken;
      try {
        if (nextToken) {
          await establishWebUiSession();
        } else {
          await clearWebUiSession();
        }
      } catch (error) {
        setApiStatus(`令牌验证失败: ${error.message}`, "error");
        return;
      }
      const persisted = persistToken(nextToken);
      setApiStatus(
        nextToken
          ? persisted
            ? "令牌已验证并保存"
            : "令牌已验证（浏览器未允许保存）"
          : "令牌与浏览器会话已清除",
        "ok",
      );
      await Promise.allSettled([
        loadSettings(),
        loadRawSettings(),
        loadFiles(),
        loadTaskList(),
        loadSchedules(),
        loadCollectMonitors(),
        loadCollectorIdentities(),
        loadCollectorPolicy(refs.collectorPolicyPlatform.value),
        loadCollectorAssignments(refs.collectorAssignmentPlatform.value),
      ]);
      connectLogSocket();
    });
  });

  refs.logsAutoscroll.addEventListener("change", (event) => {
    state.autoScroll = Boolean(event.target.checked);
  });

  refs.logsDebugToggle.addEventListener("change", (event) => {
    state.showDebugLogs = Boolean(event.target.checked);
    try {
      localStorage.setItem(
        LOG_DEBUG_STORAGE_KEY,
        state.showDebugLogs ? "1" : "0",
      );
    } catch {}
    rerenderLogs();
  });

  refs.logsClearBtn.addEventListener("click", () => {
    clearLogs();
  });

  refs.settingsReloadBtn.addEventListener("click", () => {
    withBusyButton(refs.settingsReloadBtn, "加载中", loadSettings);
  });

  refs.settingsSaveBtn.addEventListener("click", () => {
    withBusyButton(refs.settingsSaveBtn, "保存中", saveSettings);
  });

  refs.settingsRawLoadBtn.addEventListener("click", () => {
    withBusyButton(refs.settingsRawLoadBtn, "加载中", loadRawSettings);
  });

  refs.settingsRawFormatBtn.addEventListener("click", () => {
    formatRawSettings();
  });

  refs.settingsRawSaveBtn.addEventListener("click", () => {
    withBusyButton(refs.settingsRawSaveBtn, "保存中", saveRawSettings);
  });

  refs.settingsRawScope.addEventListener("change", () => {
    renderRawSettingsSource();
    refs.settingsRawStatus.textContent = "已切换编辑范围；未显示的字段保存时保持不变";
  });

  refs.settingsRawIncludeSecrets.addEventListener("change", () => {
    withBusyButton(refs.settingsRawLoadBtn, "加载中", loadRawSettings);
  });

  refs.settingsRawSearchBtn.addEventListener("click", searchRawSettings);
  refs.settingsRawSearch.addEventListener("input", () => {
    refs.settingsRawEditor.dataset.searchIndex = "0";
  });
  refs.settingsRawSearch.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      searchRawSettings();
    }
  });
  refs.settingsRawEditor.addEventListener("input", updateRawEditorMeta);
  refs.settingsRawWrapBtn.addEventListener("click", toggleRawEditorWrap);

  refs.settingsAuthLoadBtn.addEventListener("click", () => {
    syncQuickAuthEditors(
      Object.keys(state.rawSettingsSource).length ? state.rawSettingsSource : state.settingsData,
    );
  });

  refs.settingsAuthApplyBtn.addEventListener("click", () => {
    applyQuickAuthEditorsToRaw();
  });

  refs.settingsAuthSaveBtn.addEventListener("click", () => {
    withBusyButton(refs.settingsAuthSaveBtn, "保存中", saveQuickAuthSettings);
  });

  refs.accountsDouyinAddBtn.addEventListener("click", () => {
    addAccountRow("douyin");
  });

  refs.accountsTiktokAddBtn.addEventListener("click", () => {
    addAccountRow("tiktok");
  });

  refs.accountsToggleBtn.addEventListener("click", () => {
    toggleAccountsSettings();
  });

  refs.accountsExportJsonBtn.addEventListener("click", () => {
    exportAccountsJson();
  });

  refs.accountsImportJsonBtn.addEventListener("click", () => {
    refs.accountsImportJsonFile.value = "";
    refs.accountsImportJsonFile.click();
  });

  refs.accountsImportJsonFile.addEventListener("change", (event) => {
    const file = event.target.files?.[0];
    importAccountsJsonFile(file);
  });

  const bindAccountBodies = (body, section = "active") => {
    body.addEventListener("input", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLInputElement)) {
        return;
      }
      const row = target.closest("tr");
      if (!row) {
        return;
      }
      const platform = row.dataset.platform || "douyin";
      const index = Number(row.dataset.index || "0");
      const field = target.dataset.field || "";
      if (!field) {
        return;
      }
      const checkedFields = new Set(["enable", "auto_update_earliest", "selected"]);
      updateAccountRow(
        platform,
        index,
        field,
        checkedFields.has(field) ? target.checked : target.value,
        section,
      );
      if (field === "selected") {
        renderAccountPager(platform, section);
      }
    });

    body.addEventListener("change", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLInputElement)) {
        return;
      }
      const row = target.closest("tr");
      if (!row) {
        return;
      }
      const platform = row.dataset.platform || "douyin";
      const field = target.dataset.field || "";
      if (section === "active" && field === "url") {
        renderAccountRows(platform);
      }
    });

    body.addEventListener("click", async (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }
      if (
        target instanceof HTMLInputElement &&
        target.dataset.field === "selected"
      ) {
        const row = target.closest("tr");
        if (!row) {
          return;
        }
        const platform = row.dataset.platform || "douyin";
        const index = Number(row.dataset.index || "-1");
        if (!Number.isInteger(index) || index < 0) {
          return;
        }
        if (event.shiftKey) {
          const anchor = getSelectionAnchor(platform, section);
          if (Number.isInteger(anchor)) {
            applySelectionRange(platform, section, anchor, index, target.checked);
          }
        }
        setSelectionAnchor(platform, section, index);
        return;
      }
      const actionTarget = target.closest("[data-action]");
      const action = actionTarget?.dataset.action;
      if (!action) {
        return;
      }
      const row = actionTarget.closest("tr");
      if (!row) {
        return;
      }
      const platform = row.dataset.platform || "douyin";
      const index = Number(row.dataset.index || "0");
      if (action === "open-row") {
        const rows =
          section === "deleted"
            ? state.deletedRows[accountRowsKey(platform)]
            : state.accountRows[accountRowsKey(platform)];
        openUrls([rows[index]?.url || ""]);
        return;
      }
      if (action === "remove-row" && section === "active") {
        removeAccountRow(platform, index);
        const result = await persistAccountTables("account_remove_row");
        setAccountStatus(platform, `已删除并备份: ${result.backup_path || "-"}`);
        return;
      }
      if (action === "restore-row" && section === "deleted") {
        restoreDeletedRow(platform, index);
        const result = await persistAccountTables("account_restore_row");
        setAccountStatus(platform, `已撤销并备份: ${result.backup_path || "-"}`);
      }
    });
  };

  bindAccountBodies(refs.accountsDouyinBody, "active");
  bindAccountBodies(refs.accountsTiktokBody, "active");
  bindAccountBodies(refs.deletedDouyinBody, "deleted");
  bindAccountBodies(refs.deletedTikTokBody, "deleted");

  const bindSearch = (input, platform) => {
    input.addEventListener("input", () => {
      accountPaginationState(platform, "active").page = 1;
      accountPaginationState(platform, "deleted").page = 1;
      renderAccountRows(platform);
      renderDeletedRows(platform);
    });
  };
  bindSearch(refs.accountsDouyinSearch, "douyin");
  bindSearch(refs.accountsTikTokSearch, "tiktok");

  refs.accountsDouyinFormatBtn.addEventListener("click", () => {
    withBusyButton(refs.accountsDouyinFormatBtn, "规则化中", async () => {
      formatAccountUrls("douyin");
      const result = await persistAccountTables("account_format_url");
      setAccountStatus("douyin", `URL 已规则化并备份: ${result.backup_path || "-"}`);
    });
  });
  refs.accountsTikTokFormatBtn.addEventListener("click", () => {
    withBusyButton(refs.accountsTikTokFormatBtn, "规则化中", async () => {
      formatAccountUrls("tiktok");
      const result = await persistAccountTables("account_format_url");
      setAccountStatus("tiktok", `URL 已规则化并备份: ${result.backup_path || "-"}`);
    });
  });

  refs.accountsDouyinCheckBtn.addEventListener("click", () =>
    withBusyButton(refs.accountsDouyinCheckBtn, "检测中", () => verifyAccounts("douyin")),
  );
  refs.accountsTikTokCheckBtn.addEventListener("click", () =>
    withBusyButton(refs.accountsTikTokCheckBtn, "检测中", () => verifyAccounts("tiktok")),
  );
  refs.accountsDouyinIdentity.addEventListener("change", () => {
    syncAccountVerifyIdentityHelp("douyin");
  });
  refs.accountsTikTokIdentity.addEventListener("change", () => {
    syncAccountVerifyIdentityHelp("tiktok");
  });

  refs.accountsDouyinSelectAllBtn.addEventListener("click", () =>
    selectAllRows("douyin", "active", true),
  );
  refs.accountsDouyinClearSelectBtn.addEventListener("click", () =>
    selectAllRows("douyin", "active", false),
  );
  refs.accountsTikTokSelectAllBtn.addEventListener("click", () =>
    selectAllRows("tiktok", "active", true),
  );
  refs.accountsTikTokClearSelectBtn.addEventListener("click", () =>
    selectAllRows("tiktok", "active", false),
  );

  refs.deletedDouyinSelectAllBtn.addEventListener("click", () =>
    selectAllRows("douyin", "deleted", true),
  );
  refs.deletedDouyinClearSelectBtn.addEventListener("click", () =>
    selectAllRows("douyin", "deleted", false),
  );
  refs.deletedTikTokSelectAllBtn.addEventListener("click", () =>
    selectAllRows("tiktok", "deleted", true),
  );
  refs.deletedTikTokClearSelectBtn.addEventListener("click", () =>
    selectAllRows("tiktok", "deleted", false),
  );

  refs.accountsDouyinOpenSelectedBtn.addEventListener("click", () => {
    const key = accountRowsKey("douyin");
    openUrls(
      selectedIndexes("douyin", "active").map((index) => state.accountRows[key][index]?.url || ""),
    );
  });
  refs.accountsTikTokOpenSelectedBtn.addEventListener("click", () => {
    const key = accountRowsKey("tiktok");
    openUrls(
      selectedIndexes("tiktok", "active").map((index) => state.accountRows[key][index]?.url || ""),
    );
  });

  refs.deletedDouyinOpenSelectedBtn.addEventListener("click", () => {
    const key = accountRowsKey("douyin");
    openUrls(
      selectedIndexes("douyin", "deleted").map(
        (index) => state.deletedRows[key][index]?.url || "",
      ),
    );
  });
  refs.deletedTikTokOpenSelectedBtn.addEventListener("click", () => {
    const key = accountRowsKey("tiktok");
    openUrls(
      selectedIndexes("tiktok", "deleted").map(
        (index) => state.deletedRows[key][index]?.url || "",
      ),
    );
  });

  refs.accountsDouyinBatchField.addEventListener("change", () => {
    syncBatchValuePlaceholder("douyin");
  });
  refs.accountsTikTokBatchField.addEventListener("change", () => {
    syncBatchValuePlaceholder("tiktok");
  });

  refs.accountsDouyinApplyBatchBtn.addEventListener("click", () => {
    withBusyButton(refs.accountsDouyinApplyBatchBtn, "替换中", async () => {
      const field = refs.accountsDouyinBatchField.value;
      const value = refs.accountsDouyinBatchValue.value;
      const resultState = applyBatchField("douyin", field, value);
      if (resultState.error) {
        setAccountStatus("douyin", resultState.error);
        return;
      }
      const result = await persistAccountTables("account_batch_replace");
      setAccountStatus(
        "douyin",
        `已批量替换 ${resultState.updated} 行 ${field}: ${result.backup_path || "-"}`,
      );
    });
  });
  refs.accountsTikTokApplyBatchBtn.addEventListener("click", () => {
    withBusyButton(refs.accountsTikTokApplyBatchBtn, "替换中", async () => {
      const field = refs.accountsTikTokBatchField.value;
      const value = refs.accountsTikTokBatchValue.value;
      const resultState = applyBatchField("tiktok", field, value);
      if (resultState.error) {
        setAccountStatus("tiktok", resultState.error);
        return;
      }
      const result = await persistAccountTables("account_batch_replace");
      setAccountStatus(
        "tiktok",
        `已批量替换 ${resultState.updated} 行 ${field}: ${result.backup_path || "-"}`,
      );
    });
  });

  refs.accountsDouyinDeleteSelectedBtn.addEventListener("click", () => {
    withBusyButton(refs.accountsDouyinDeleteSelectedBtn, "删除中", async () => {
      selectedIndexes("douyin", "active")
        .sort((a, b) => b - a)
        .forEach((index) => removeAccountRow("douyin", index, "批量删除"));
      const result = await persistAccountTables("account_batch_delete");
      setAccountStatus("douyin", `批量删除已保存: ${result.backup_path || "-"}`);
    });
  });
  refs.accountsTikTokDeleteSelectedBtn.addEventListener("click", () => {
    withBusyButton(refs.accountsTikTokDeleteSelectedBtn, "删除中", async () => {
      selectedIndexes("tiktok", "active")
        .sort((a, b) => b - a)
        .forEach((index) => removeAccountRow("tiktok", index, "批量删除"));
      const result = await persistAccountTables("account_batch_delete");
      setAccountStatus("tiktok", `批量删除已保存: ${result.backup_path || "-"}`);
    });
  });

  refs.deletedDouyinRestoreSelectedBtn.addEventListener("click", () => {
    withBusyButton(refs.deletedDouyinRestoreSelectedBtn, "撤销中", async () => {
      selectedIndexes("douyin", "deleted")
        .sort((a, b) => b - a)
        .forEach((index) => restoreDeletedRow("douyin", index));
      const result = await persistAccountTables("account_batch_restore");
      setAccountStatus("douyin", `批量撤销已保存: ${result.backup_path || "-"}`);
    });
  });
  refs.deletedTikTokRestoreSelectedBtn.addEventListener("click", () => {
    withBusyButton(refs.deletedTikTokRestoreSelectedBtn, "撤销中", async () => {
      selectedIndexes("tiktok", "deleted")
        .sort((a, b) => b - a)
        .forEach((index) => restoreDeletedRow("tiktok", index));
      const result = await persistAccountTables("account_batch_restore");
      setAccountStatus("tiktok", `批量撤销已保存: ${result.backup_path || "-"}`);
    });
  });

  refs.deletedDouyinPurgeSelectedBtn.addEventListener("click", (event) => {
    openDeletedAccountsDialog("douyin", "selected", event.currentTarget);
  });
  refs.deletedDouyinPurgeAllBtn.addEventListener("click", (event) => {
    openDeletedAccountsDialog("douyin", "all", event.currentTarget);
  });
  refs.deletedTikTokPurgeSelectedBtn.addEventListener("click", (event) => {
    openDeletedAccountsDialog("tiktok", "selected", event.currentTarget);
  });
  refs.deletedTikTokPurgeAllBtn.addEventListener("click", (event) => {
    openDeletedAccountsDialog("tiktok", "all", event.currentTarget);
  });
  refs.deletedAccountsDialogCloseBtn.addEventListener("click", () => {
    closeDeletedAccountsDialog();
  });
  refs.deletedAccountsDialogCancelBtn.addEventListener("click", () => {
    closeDeletedAccountsDialog();
  });
  refs.deletedAccountsDialogConfirmBtn.addEventListener("click", () => {
    confirmDeletedAccountsPurge();
  });
  refs.deletedAccountsDialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    closeDeletedAccountsDialog();
  });
  refs.deletedAccountsDialog.addEventListener("click", (event) => {
    if (event.target === refs.deletedAccountsDialog) {
      closeDeletedAccountsDialog();
    }
  });

  refs.boardPlatform.addEventListener("change", () => {
    state.accountBoard.platform = refs.boardPlatform.value || "douyin";
    state.accountBoard.page = 1;
    loadAccountBoard(true);
  });

  refs.boardSearch.addEventListener("input", () => {
    state.accountBoard.search = refs.boardSearch.value.trim();
    state.accountBoard.page = 1;
    window.clearTimeout(state.accountBoard.searchTimer);
    state.accountBoard.searchTimer = window.setTimeout(() => {
      loadAccountBoard(true);
    }, 260);
  });

  refs.boardSearchClearBtn.addEventListener("click", () => {
    window.clearTimeout(state.accountBoard.searchTimer);
    refs.boardSearch.value = "";
    state.accountBoard.search = "";
    state.accountBoard.page = 1;
    loadAccountBoard(true);
    refs.boardSearch.focus();
  });

  refs.boardStatusFilter.addEventListener("change", () => {
    state.accountBoard.status = refs.boardStatusFilter.value || "all";
    state.accountBoard.page = 1;
    loadAccountBoard(true);
  });

  refs.boardSort.addEventListener("change", () => {
    state.accountBoard.sort = refs.boardSort.value || "configured";
    state.accountBoard.page = 1;
    loadAccountBoard(true);
  });

  refs.boardRefreshKind.addEventListener("change", () => {
    state.accountBoard.refreshKind = refs.boardRefreshKind.value || "auto";
  });

  refs.boardViewMode.addEventListener("change", () => {
    state.accountBoard.viewMode = refs.boardViewMode.value || "avatar";
    try {
      localStorage.setItem(BOARD_VIEW_MODE_STORAGE_KEY, state.accountBoard.viewMode);
    } catch {}
    applyBoardColumns(true);
    for (const card of refs.boardGrid.querySelectorAll(".profile-card")) {
      renderBoardCardPreview(card);
    }
  });

  refs.boardDensity.addEventListener("input", () => {
    state.accountBoard.columns = Number(refs.boardDensity.value || "4");
    applyBoardColumns(true);
  });

  refs.boardPageSize.addEventListener("change", () => {
    state.accountBoard.pageSize = Number(refs.boardPageSize.value || "24");
    state.accountBoard.page = 1;
    loadAccountBoard(true);
  });

  refs.boardPrevBtn.addEventListener("click", () => {
    state.accountBoard.page = Math.max(1, state.accountBoard.page - 1);
    loadAccountBoard(false);
  });

  refs.boardNextBtn.addEventListener("click", () => {
    state.accountBoard.page = Math.min(state.accountBoard.pages, state.accountBoard.page + 1);
    loadAccountBoard(false);
  });

  refs.boardReloadBtn.addEventListener("click", () => {
    withBusyButton(refs.boardReloadBtn, "刷新中", () => loadAccountBoard(false));
  });

  refs.boardAvatarPageBtn.addEventListener("click", () => {
    generateBoardAvatarCurrentPage();
  });

  refs.boardAvatarAllBtn.addEventListener("click", () => {
    generateBoardAvatarAllUnpinned();
  });

  refs.boardPinAllBtn.addEventListener("click", () => {
    withBusyButton(refs.boardPinAllBtn, "Pin 中", pinCurrentBoardPage);
  });

  refs.boardGrid.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }
    const actionButton = target.closest("button[data-action]");
    if (!(actionButton instanceof HTMLButtonElement)) {
      return;
    }
    const card = actionButton.closest(".profile-card");
    if (!(card instanceof HTMLElement)) {
      return;
    }
    const action = actionButton.dataset.action || "";
    actionButton.closest(".profile-actions-menu")?.removeAttribute("open");
    if (action === "board-open-account") {
      openUrls([card.dataset.url || ""]);
      return;
    }
    if (action === "board-open-files") {
      openBoardFolderInFiles(card);
      return;
    }
    if (action === "board-refresh-media") {
      refreshBoardCard(card, state.accountBoard.refreshKind || "auto");
      return;
    }
    if (action === "board-refresh-video") {
      refreshBoardCard(card, "video");
      return;
    }
    if (action === "board-generate-avatar") {
      enqueueBoardAvatarBatch([card.dataset.url || ""], "单个账户");
      return;
    }
    if (action === "board-pin-media") {
      pinBoardCard(card);
    }
  });

  refs.boardGrid.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") {
      return;
    }
    const menu = event.target.closest(".profile-actions-menu[open]");
    if (!(menu instanceof HTMLDetailsElement)) {
      return;
    }
    event.preventDefault();
    menu.removeAttribute("open");
    menu.querySelector("summary")?.focus();
  });

  document.addEventListener("click", (event) => {
    for (const menu of refs.boardGrid.querySelectorAll(".profile-actions-menu[open]")) {
      if (!menu.contains(event.target)) {
        menu.removeAttribute("open");
      }
    }
  });

  refs.filesBackToBoardBtn.addEventListener("click", () => {
    switchTab("profiles");
  });

  refs.filesPinProfileBtn.addEventListener("click", () => {
    withBusyButton(refs.filesPinProfileBtn, "设置中", pinFromFileBrowser);
  });

  refs.filesGenerateAvatarBtn.addEventListener("click", () => {
    withBusyButton(refs.filesGenerateAvatarBtn, "生成中", generateAvatarFromFileBrowser);
  });

  refs.filesPinAvatarBtn.addEventListener("click", () => {
    withBusyButton(refs.filesPinAvatarBtn, "设置中", pinAvatarFromFileBrowser);
  });

  refs.filesScope.addEventListener("change", () => {
    state.currentScope = refs.filesScope.value;
    navigateToFilePath("");
  });

  refs.filesSearch.addEventListener("input", () => {
    state.fileSearch = refs.filesSearch.value || "";
    state.filePage = 1;
    window.clearTimeout(state.fileSearchTimer);
    state.fileSearchTimer = window.setTimeout(() => {
      loadFiles();
    }, 260);
  });

  refs.filesSearchClearBtn.addEventListener("click", () => {
    window.clearTimeout(state.fileSearchTimer);
    state.fileSearch = "";
    state.filePage = 1;
    refs.filesSearch.value = "";
    loadFiles();
    refs.filesSearch.focus();
  });

  refs.filesPageSize.addEventListener("change", () => {
    state.filePageSize = Number(refs.filesPageSize.value) || 24;
    state.filePage = 1;
    loadFiles();
  });

  refs.filesPrevBtn.addEventListener("click", () => {
    if (state.filePage <= 1) {
      return;
    }
    state.filePage -= 1;
    loadFiles();
  });

  refs.filesNextBtn.addEventListener("click", () => {
    if (state.filePage >= state.filePages) {
      return;
    }
    state.filePage += 1;
    loadFiles();
  });

  refs.filesOpenBtn.addEventListener("click", () => {
    withBusyButton(refs.filesOpenBtn, "打开中", async () => {
      await navigateToFilePath(refs.filesPath.value.trim());
    });
  });

  refs.filesPath.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") {
      return;
    }
    event.preventDefault();
    refs.filesOpenBtn.click();
  });

  refs.filesHomeBtn.addEventListener("click", () => {
    navigateToFilePath("");
  });

  refs.filesUpBtn.addEventListener("click", () => {
    navigateToFilePath(state.currentParentPath || parentPath(state.currentPath), {
      focusAfterLoad: true,
    });
  });

  refs.filesRefreshBtn.addEventListener("click", () => {
    withBusyButton(refs.filesRefreshBtn, "刷新中", loadFiles);
  });

  refs.filesStatsRefreshBtn.addEventListener("click", () => {
    withBusyButton(refs.filesStatsRefreshBtn, "统计中", loadFileStats);
  });

  refs.fileLightboxCloseBtn.addEventListener("click", () => {
    closeFileLightbox();
  });

  refs.fileLightboxPrevBtn.addEventListener("click", () => {
    moveFileLightbox(-1);
  });

  refs.fileLightboxNextBtn.addEventListener("click", () => {
    moveFileLightbox(1);
  });

  refs.fileLightbox.addEventListener("cancel", (event) => {
    event.preventDefault();
    closeFileLightbox();
  });

  refs.fileLightbox.addEventListener("click", (event) => {
    if (event.target === refs.fileLightbox) {
      closeFileLightbox();
    }
  });

  refs.fileLightbox.addEventListener("keydown", (event) => {
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      moveFileLightbox(-1);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      moveFileLightbox(1);
    }
  });

  refs.shareResolveBtn.addEventListener("click", () => {
    withBusyButton(refs.shareResolveBtn, "解析中", resolveShareLink);
  });

  refs.shareCopyBtn.addEventListener("click", () => {
    copyShareResult();
  });

  refs.workflowAccountRunBtn.addEventListener("click", () => {
    withBusyButton(refs.workflowAccountRunBtn, "入队中", runWorkflowAccountTask);
  });

  refs.workflowDetailForm.addEventListener("submit", (event) => {
    event.preventDefault();
    withBusyButton(refs.workflowDetailRunBtn, "入队中", runWorkflowDetailTask);
  });

  refs.workflowDetailLinks.addEventListener("input", syncWorkflowDetailInputState);
  refs.workflowDetailPlatform.addEventListener("change", syncWorkflowDetailInputState);
  refs.workflowDetailIdentity.addEventListener("change", syncWorkflowDetailIdentityOverrides);
  refs.workflowDetailCookie.addEventListener("input", syncWorkflowDetailIdentityOverrides);
  refs.workflowDetailProxy.addEventListener("input", syncWorkflowDetailIdentityOverrides);
  refs.workflowDetailLinks.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      refs.workflowDetailForm.requestSubmit();
    }
  });

  refs.scheduleCreateBtn.addEventListener("click", () => {
    withBusyButton(refs.scheduleCreateBtn, "创建中", createSchedule);
  });

  refs.scheduleRefreshBtn.addEventListener("click", () => {
    withBusyButton(refs.scheduleRefreshBtn, "刷新中", loadSchedules);
  });

  refs.monitorCreateBtn.addEventListener("click", () => {
    withBusyButton(refs.monitorCreateBtn, "创建中", createCollectMonitor);
  });

  refs.monitorRefreshBtn.addEventListener("click", () => {
    withBusyButton(refs.monitorRefreshBtn, "刷新中", loadCollectMonitors);
  });
  refs.monitorIdentity.addEventListener("change", syncMonitorIdentityOverrides);
  refs.monitorCookie.addEventListener("input", syncMonitorIdentityOverrides);
  refs.monitorProxy.addEventListener("input", syncMonitorIdentityOverrides);

  refs.collectorCreateBtn.addEventListener("click", (event) => {
    openCollectorIdentityDialog("", event.currentTarget);
  });

  refs.collectorRefreshBtn.addEventListener("click", () => {
    withBusyButton(refs.collectorRefreshBtn, "刷新中", async () => {
      await Promise.all([
        loadCollectorIdentities(),
        loadCollectorPolicy(refs.collectorPolicyPlatform.value),
        loadCollectorAssignments(refs.collectorAssignmentPlatform.value),
      ]);
    });
  });

  refs.collectorPlatformFilter.addEventListener("change", renderCollectorIdentities);
  refs.collectorStatusFilter.addEventListener("change", renderCollectorIdentities);

  refs.collectorIdentityList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-collector-action]");
    if (!(button instanceof HTMLButtonElement)) {
      return;
    }
    const action = button.dataset.collectorAction;
    if (action === "create") {
      openCollectorIdentityDialog("", button);
      return;
    }
    if (action === "clear-filter") {
      refs.collectorPlatformFilter.value = "all";
      refs.collectorStatusFilter.value = "all";
      renderCollectorIdentities();
      refs.collectorPlatformFilter.focus();
      return;
    }
    if (action === "retry") {
      withBusyButton(button, "重试中", loadCollectorIdentities);
      return;
    }
    const card = button.closest("[data-identity-id]");
    if (!card?.dataset.identityId) {
      return;
    }
    runCollectorIdentityAction(action, card.dataset.identityId, button);
  });

  refs.collectorIdentityForm.addEventListener("submit", (event) => {
    event.preventDefault();
    withBusyButton(refs.collectorDialogSaveBtn, "保存中", saveCollectorIdentity);
  });

  refs.collectorDialogCloseBtn.addEventListener("click", closeCollectorIdentityDialog);
  refs.collectorDialogCancelBtn.addEventListener("click", closeCollectorIdentityDialog);
  refs.collectorIdentityDialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    closeCollectorIdentityDialog();
  });
  refs.collectorIdentityDialog.addEventListener("click", (event) => {
    if (event.target === refs.collectorIdentityDialog) {
      closeCollectorIdentityDialog();
    }
  });
  refs.collectorIdentityPlatform.addEventListener("change", syncCollectorCredentialFields);

  refs.collectorPolicyPlatform.addEventListener("change", () => {
    loadCollectorPolicy(refs.collectorPolicyPlatform.value);
  });
  refs.collectorPolicyForm.addEventListener("submit", (event) => {
    event.preventDefault();
    withBusyButton(refs.collectorPolicySaveBtn, "保存中", saveCollectorPolicy);
  });

  refs.collectorAssignmentPlatform.addEventListener("change", () => {
    const platform = refs.collectorAssignmentPlatform.value;
    populateCollectorIdentitySelect(
      refs.collectorAssignmentIdentity,
      platform,
      "选择一个可路由身份",
      { preserveUnavailable: true },
    );
    refs.collectorPreviewResult.hidden = true;
    setCollectorStatus(refs.collectorAssignmentStatus, "等待填写账号主页 URL");
    setCollectorStatus(refs.collectorPreviewStatus, "预览只读，不会创建任务或修改绑定");
    Promise.allSettled([
      loadCollectorPolicy(platform),
      loadCollectorAssignments(platform),
    ]);
  });
  refs.collectorAssignmentForm.addEventListener("submit", (event) => {
    event.preventDefault();
    withBusyButton(refs.collectorAssignmentSaveBtn, "保存中", saveCollectorAssignment);
  });
  refs.collectorAssignmentUnbindBtn.addEventListener("click", () => {
    withBusyButton(refs.collectorAssignmentUnbindBtn, "解绑中", () =>
      removeCollectorAssignment(
        refs.collectorAssignmentPlatform.value,
        refs.collectorAssignmentKey.value,
      ),
    );
  });
  refs.collectorAssignmentList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-collector-binding-action]");
    if (!(button instanceof HTMLButtonElement)) {
      return;
    }
    const action = button.dataset.collectorBindingAction;
    const platform = refs.collectorAssignmentPlatform.value;
    if (action === "retry") {
      withBusyButton(button, "重试中", () => loadCollectorAssignments(platform));
      return;
    }
    const row = button.closest("[data-target-key]");
    const targetKey = row?.dataset.targetKey || "";
    const assignment = (state.collectorAssignments[platform] || []).find(
      (item) => item.target_key === targetKey,
    );
    if (!assignment) {
      return;
    }
    if (action === "load") {
      loadCollectorAssignmentIntoForm(assignment);
      return;
    }
    if (action === "unbind") {
      withBusyButton(button, "解绑中", () =>
        removeCollectorAssignment(platform, assignment.target_key),
      );
    }
  });
  refs.collectorPreviewBtn.addEventListener("click", () => {
    withBusyButton(refs.collectorPreviewBtn, "计算中", previewCollectorRouting);
  });

  refs.workflowAccountPlatform.addEventListener("change", () => {
    populateCollectorIdentitySelect(
      refs.workflowAccountIdentity,
      refs.workflowAccountPlatform.value,
      "自动路由",
      { preserveUnavailable: true },
    );
    syncWorkflowAccountIdentityOverrides();
  });
  refs.workflowAccountIdentity.addEventListener("change", syncWorkflowAccountIdentityOverrides);
  refs.workflowAccountCookie.addEventListener("input", syncWorkflowAccountIdentityOverrides);
  refs.workflowAccountProxy.addEventListener("input", syncWorkflowAccountIdentityOverrides);
  refs.schedulePlatform.addEventListener("change", () => {
    populateCollectorIdentitySelect(
      refs.scheduleIdentity,
      refs.schedulePlatform.value,
      "自动路由",
      { preserveUnavailable: true },
    );
    syncScheduleIdentityOverrides();
  });
  refs.scheduleIdentity.addEventListener("change", syncScheduleIdentityOverrides);
  refs.scheduleCookie.addEventListener("input", syncScheduleIdentityOverrides);
  refs.scheduleProxy.addEventListener("input", syncScheduleIdentityOverrides);

  refs.taskEndpoint.addEventListener("change", () => {
    syncTaskIdentitySelector();
    loadTaskTemplate();
  });

  refs.taskIdentity.addEventListener("change", () => {
    try {
      rewriteTaskPayloadForIdentity();
    } catch (error) {
      syncTaskIdentityControls();
      refs.taskIdentityHelp.textContent = `Payload JSON 无法更新：${error.message}`;
      refs.taskIdentityHelp.dataset.state = "warning";
    }
  });

  refs.taskPayload.addEventListener("input", syncTaskIdentityControls);
  refs.taskPayload.addEventListener("blur", () => {
    if (!refs.taskIdentity.value) {
      return;
    }
    try {
      rewriteTaskPayloadForIdentity();
    } catch {}
  });

  refs.taskTemplateBtn.addEventListener("click", () => {
    loadTaskTemplate();
  });

  refs.taskRunBtn.addEventListener("click", () => {
    withBusyButton(refs.taskRunBtn, "入队中", runTaskRequest);
  });

  refs.taskCopyBtn.addEventListener("click", () => {
    copyTaskResult();
  });

  refs.taskQueueRefreshBtn.addEventListener("click", () => {
    withBusyButton(refs.taskQueueRefreshBtn, "刷新中", loadTaskList);
  });

  refs.taskAccountCheckpoints.addEventListener("toggle", () => {
    if (refs.taskAccountCheckpoints.open) {
      loadTaskAccounts();
    }
  });

  refs.taskAccountRefreshBtn.addEventListener("click", () => {
    withBusyButton(refs.taskAccountRefreshBtn, "刷新中", () => loadTaskAccounts());
  });

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && state.activeTab === "workbench") {
      loadTaskList();
    }
  });

  window.addEventListener("resize", () => {
    applyBoardColumns(false);
    scheduleFileMasonryLayout();
    syncTabOrientation();
  });
}

function startLogFallbackPolling() {
  setInterval(() => {
    if (!state.wsActive) {
      pollLogs();
    }
  }, 1500);

  setInterval(() => {
    if (!state.wsActive) {
      connectLogSocket();
    }
  }, 6000);
}

function startTaskPolling() {
  setInterval(() => {
    if (!document.hidden && state.activeTab === "workbench") {
      loadTaskList();
    }
  }, 2000);
}

async function bootstrap() {
  state.token = readStoredToken();
  refs.tokenInput.value = state.token;
  refreshIcons(document);
  applySidebarCollapsed(readStoredBoolean(SIDEBAR_COLLAPSE_STORAGE_KEY), false);
  bindEvents();
  syncWorkflowAccountIdentityOverrides();
  syncScheduleIdentityOverrides();
  syncTabOrientation();
  setBoardAvatarBatchBusy(false);
  syncBatchValuePlaceholder("douyin");
  syncBatchValuePlaceholder("tiktok");
  state.accountBoard.platform = refs.boardPlatform.value || "douyin";
  state.accountBoard.pageSize = Number(refs.boardPageSize.value || "24");
  state.accountBoard.refreshKind = refs.boardRefreshKind.value || "auto";
  state.accountBoard.viewMode = refs.boardViewMode?.value || "avatar";
  state.accountBoard.search = refs.boardSearch?.value.trim() || "";
  state.accountBoard.status = refs.boardStatusFilter?.value || "all";
  state.accountBoard.sort = refs.boardSort?.value || "configured";
  try {
    state.accountBoard.columns = Number(localStorage.getItem(BOARD_COLUMNS_STORAGE_KEY) || "4");
  } catch {
    state.accountBoard.columns = 4;
  }
  try {
    state.accountBoard.viewMode =
      localStorage.getItem(BOARD_VIEW_MODE_STORAGE_KEY) ||
      state.accountBoard.viewMode ||
      "avatar";
  } catch {}
  if (refs.boardViewMode) {
    refs.boardViewMode.value = state.accountBoard.viewMode;
  }
  applyBoardColumns(false);
  state.currentScope = refs.filesScope.value;
  state.currentPath = refs.filesPath.value.trim();
  state.fileSearch = refs.filesSearch?.value || "";
  state.filePageSize = Number(refs.filesPageSize?.value || "24");
  updateFilesAccountContext();
  try {
    state.showDebugLogs = localStorage.getItem(LOG_DEBUG_STORAGE_KEY) === "1";
  } catch {
    state.showDebugLogs = false;
  }
  if (refs.logsDebugToggle) {
    refs.logsDebugToggle.checked = state.showDebugLogs;
  }
  let activeTab = "workbench";
  try {
    activeTab = localStorage.getItem(ACTIVE_TAB_STORAGE_KEY) || "workbench";
  } catch {}
  switchTab(activeTab);
  let isCollapsed = false;
  try {
    isCollapsed = localStorage.getItem(ACCOUNTS_COLLAPSE_STORAGE_KEY) === "1";
  } catch {}
  toggleAccountsSettings(isCollapsed);
  setAccountRows("douyin", []);
  setAccountRows("tiktok", []);
  setDeletedRows("douyin", []);
  setDeletedRows("tiktok", []);
  syncCollectorCredentialFields();
  syncCollectorIdentitySelectors();
  syncWorkflowDetailInputState();
  loadTaskTemplate();
  if (state.token) {
    try {
      await establishWebUiSession();
      setApiStatus("已恢复保存的令牌", "ok");
    } catch (error) {
      setApiStatus(`保存的令牌无效: ${error.message}`, "error");
    }
  }
  connectLogSocket();
  startLogFallbackPolling();
  startTaskPolling();
  pollLogs();
  loadSettings();
  loadRawSettings();
  loadFiles();
  loadTaskList();
  loadSchedules();
  loadCollectMonitors();
  loadCollectorIdentities();
  loadCollectorPolicy(refs.collectorPolicyPlatform.value);
  loadCollectorAssignments(refs.collectorAssignmentPlatform.value);
}

void bootstrap();

export {};
