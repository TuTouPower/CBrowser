import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type Locale = "en" | "zh";

type Params = Record<string, string | number>;

type MessageDict = Record<string, string>;

const en: MessageDict = {
  // Common
  loading: "Loading...",
  retry: "Retry",
  cancel: "Cancel",
  save: "Save",
  saved: "Saved",
  saving: "Saving...",
  create: "Create",
  delete: "Delete",
  deleting: "Deleting...",
  close: "Close",
  dismiss: "Dismiss",
  add: "Add",
  settings: "Settings",
  applying: "Applying…",
  test: "Test",

  // Language
  languageEn: "English",
  languageZh: "中文",
  switchLanguage: "Switch language",
  language: "Language",

  // Auth / login
  unableToReachServer: "Unable to reach the server",
  enterAccessToken: "Enter your access token",
  accessToken: "Access token",
  authenticating: "Authenticating...",
  unlock: "Unlock",
  loginFailed: "Login failed",
  logOut: "Log out",

  // App chrome
  hideSidebar: "Hide sidebar",
  showSidebar: "Show sidebar",
  quitManager: "Quit Manager (stops the server)",
  quitConfirm:
    "Quit CBrowser? This stops the server and closes all running profiles.",
  managerStopped: "CBrowser has stopped",
  managerStoppedHint: "The server is no longer running. You can close this tab.",
  managerStoppedRelaunch: "Relaunch the app to start it again.",
  selectOrCreateProfile: "Select a profile or create a new one",
  noLicenseKeySet: "No license key set",
  noLicenseKeyBody:
    "You're running the free keyless build. Add a key to run the latest Pro build.",
  enterKeyInSettings: "Enter a key in Settings",
  getFreeKey: "Get a free key",
  seeProPlans: "See Pro plans →",
  orContinueKeyless: "Or select a profile or create a new one to continue keyless.",
  failedToLaunchProfile: "Failed to launch profile",

  // Profile list
  searchProfiles: "Search profiles...",
  noProfilesYet: "No profiles yet",
  noMatches: "No matches",
  runningCount: "{count} running",
  proxy: "Proxy",
  newProfile: "New Profile",

  // Launch
  firstTimeSetup: "First-time setup...",
  stopping: "Stopping...",
  launching: "Launching...",
  stop: "Stop",
  launch: "Launch",
  runtimeNotReady: "Runtime not ready",
  runtimeCoordinatorError: "Runtime coordination error: {error}",
  displaySettingsSavedPending:
    "Settings saved. Restart the profile to apply the new display size.",
  displayApplyAndRestart: "Apply and restart",
  displayApplyingRestart: "Applying and restarting...",
  displayApplyFailed: "Failed to apply display size: {error}",
  upgradePlan: "Upgrade your plan",
  dismissLaunchError: "Dismiss launch error",
  updateAvailable: "CBrowser {version} is available.",
  download: "Download",
  dismissUpdate: "Dismiss update notification",

  // System status
  tierPro: "Pro",
  tierFree: "Free key",
  tierKeyless: "Free (keyless)",
  tierKeylessTitle:
    "No license key set. Running the free keyless build. Open Settings to add a key for the latest Pro build.",
  tierLicenseTitle: "{tier} license — running {version}",
  fontsIncomplete: "Fonts incomplete",
  fontsIncompleteTitle:
    "Windows persona fonts incomplete: {present}/{required} found",

  // Settings
  licenseKey: "CBrowser license key",
  licenseKeyPlaceholderSet: "Current: {masked} — type to replace",
  licenseKeyPlaceholderEmpty: "cb_… (leave empty to run the free keyless build)",
  licenseKeyHelp:
    "One key per Manager instance — every profile shares its seat pool.",
  releaseChannel: "Release channel",
  channelStable: "Stable",
  channelPreview: "Preview (early access)",
  removeKey: "Remove key",
  failedToLoadSettings: "Failed to load settings",
  failedToSaveSettings: "Failed to save settings",
  failedToClearKey: "Failed to clear key",
  systemGatewayControlApi: "System Gateway & Control API",
  systemApiServicesStatus: "Status of v2 API services",
  healthHealthy: "Healthy",
  healthChecking: "Checking...",
  healthUnreachable: "Unreachable",

  // Profile form
  editProfile: "Edit Profile",
  deleteProfileConfirm:
    "Delete this profile? Browser data will be permanently removed.",
  resetProfileConfirm:
    "Reset this profile? Cookies, history and site data will be wiped and a new fingerprint generated. Bookmarks, settings and default search are kept.",
  duplicateWithStateConfirm:
    "Duplicate this profile with its browser state? A new profile with the same settings, fingerprint, cookies and logged-in sessions is created.",
  duplicateSettingsConfirm:
    "Duplicate this profile? A new profile with the same settings and fingerprint is created. Browser state (cookies, history) is not copied.",
  duplicate: "Duplicate",
  duplicating: "Duplicating...",
  duplicateSettingsOnly: "Duplicate settings and fingerprint only",
  failedToDuplicateProfile: "Failed to duplicate profile",
  failedToResetProfile: "Failed to reset profile",
  duplicateProfileTitle: "Duplicate profile",
  duplicateProfileHint:
    "Settings and fingerprint are copied. Browser state is only copied while the source is stopped; Artifacts are never copied.",
  resetProfileTitle: "Reset browser state",
  resetProfileDataList:
    "Deletes this profile's entire browser data, including cookies, site data, cache, history, bookmarks, saved passwords, extensions and logged-in sessions, and re-rolls the fingerprint identity.",
  resetProfileKeeps:
    "Keeps settings, tags, notes and Artifacts. Other profiles are untouched.",
  duplicateOptions: "Duplicate options",
  duplicateSettingsOnlyTitle: "Settings and fingerprint only",
  duplicateSettingsOnlyHint: "Starts with empty browser state",
  duplicateWithStateTitle: "With browser state",
  duplicateWithStateHint: "Cookies, logged-in sessions and history",
  stopProfileFirst: "Stop the profile first",
  reset: "Reset",
  resetting: "Resetting...",
  resetDone: "Reset done",
  lastPreview: "Last preview",
  lastBrowserPreview: "Last browser preview",
  basic: "Basic",
  profileName: "Profile Name",
  profileNamePlaceholder: "e.g. Amazon Seller #1",
  profileNameExample: "e.g. Work Profile",
  proxyUrlOptional: "Proxy URL (optional)",
  tagsPlaceholder: "dev, research, shopping",
  fingerprintSeed: "Fingerprint Seed",
  autoRandom: "Auto (random)",
  randomizeSeed: "Randomize seed",
  network: "Network",
  timezone: "Timezone",
  locale: "Locale",
  geoipAutoDetect:
    "Auto-detect timezone/locale from the proxy exit, or host public IP without a proxy (GeoIP)",
  proxyTestFailed: "Proxy test failed",
  hardware: "Hardware",
  screenResolution: "Screen Resolution",
  custom: "Custom",
  width: "Width",
  height: "Height",
  gpuFamily: "GPU Family",
  appleSiliconAuto: "Apple Silicon (automatic)",
  detectingRuntime: "Automatic (detecting runtime…)",
  autoFromSeed: "Auto (from seed)",
  gpuAppleHint:
    "The seed selects a coherent Apple Silicon model and matching hardware profile.",
  gpuFamilyHint:
    "The seed selects a coherent GPU model, CPU, memory, and screen profile within the family.",
  behavior: "Behavior",
  humanLikeBehavior: "Human-like mouse, keyboard, and scroll behavior",
  humanPreset: "Human Preset",
  humanPresetDefault: "Default (normal speed)",
  humanPresetCareful: "Careful (slower, deliberate)",
  enableClipboardByDefault: "Enable clipboard sync by default in VNC viewer",
  autoLaunch: "Launch automatically when Manager starts",
  capturePreview: "Save a preview screenshot of the browser",
  capturePreviewHint:
    "Captures the page periodically while running, shown here after the profile stops.",
  restoreSession: "Restore previous tabs on launch",
  restoreSessionHint:
    "Reopens the tabs that were open when this profile was last stopped.",
  compatibility: "Compatibility",
  allow3pCookies: "Allow third-party cookies for login, SSO, and challenge flows",
  transparentProxy: "Transparent proxy connection",
  transparentProxyHint:
    "Stronger proxy connection mode. Requires an http:// proxy with a username and password.",
  portableCookies: "Portable cookies",
  portableCookiesHint:
    "Lets this profile move to another machine with its logins. Only cookies saved while this is on are portable, so turn it on before logging in.",
  setGoogleDefault: "Set Google as the default search engine",
  setGoogleDefaultHint:
    "Adds a few seconds to the profile's first launch (one-time setup).",
  tags: "Tags",
  addTag: "Add tag...",
  extensions: "Extensions",
  extensionsHelp: "Add one unpacked Chrome extension directory per path.",
  advancedLaunchArgs: "Advanced launch arguments",
  advancedLaunchArgsHelp:
    "Unrestricted Chromium flags. Advanced arguments can override Manager-controlled behavior.",
  notes: "Notes",
  optionalNotes: "Optional notes about this profile...",

  // Viewer / CDP / native
  connectionFailed: "Connection failed",
  failedToConnect: "Failed to connect",
  connected: "Connected",
  connecting: "Connecting...",
  copied: "Copied!",
  copyCdpUrl: "Copy CDP endpoint URL",
  disableClipboardSync: "Disable clipboard sync",
  enableClipboardSync: "Enable clipboard sync",
  exitFullscreen: "Exit fullscreen",
  fullscreen: "Fullscreen",
  centerWindow: "Center / reset window",
  sendToBrowser: "Send clipboard text to browser",
  sendTextPlaceholder: "Paste or type text to send to remote browser...",
  send: "Send",
  uploadingToProfile: "Uploading to this profile...",
  inProfileFilesHint:
    "In profile files — pick it from Uploads — {name} in the page's file dialog",
  dropToUpload: "Drop to upload to this profile",
  dropToUploadHint: "Then pick it from Uploads — {name} in the page's file dialog",
  openedInNativeWindow: "Opened in a native window",
  nativeWindowHint:
    "{name} is running directly on this computer. Use its CBrowser window to browse.",
  automationViaCdp: "Automation remains available through Manager CDP",
  liveBrowserPreview: "Live browser preview",

  // Profile files
  profileFilesTitle: "Files available to this profile",
  profileFiles: "Profile files",
  filesForProfile: "Files for this profile",
  profileFilesAria: "Profile files, {count} {filesWord}",
  fileSingular: "file",
  filePlural: "files",
  dismissError: "Dismiss error",
  noFilesYet:
    "No files yet. Upload one, drop it onto the screen, or download one in the browser.",
  downloadedByBrowser: "Downloaded by the browser",
  uploaded: "Uploaded",
  downloading: "Downloading...",
  downloadFailed: "Download failed",
  downloadToComputer: "Download to this computer",
  removeFromProfile: "Remove from the profile",
  removeFileAria: "Remove {name}",
  uploading: "Uploading...",
  uploadAFile: "Upload a file",
  uploadsSidebarHint:
    "In the page's file dialog, pick Uploads — {name} in the sidebar.",
  failedToListFiles: "Failed to list files",
  uploadFailed: "Upload failed",
  deleteFailed: "Delete failed",
  profileFilesHint:
    "Uploads and downloads are stored by the Artifact Service, never through Selkies.",
  artifactsUploaded: "{count} file(s) uploaded",
  deleteArtifactConfirm: "Delete this file from the profile?",
  automationPageTitle: "CDP automation",
  automationPageHint:
    "Authorized endpoint for external automation through Supervisor and the Agent UDS.",
  automationEndpoint: "Authorized WebSocket endpoint",
  automationTokenHeader:
    "Send this header with an automation token: {value}",
  automationRuntimeState: "Runtime state",
  automationRuntimeInstance: "Runtime instance",
  automationSupervisor: "Supervisor",
  automationSupervisorReady: "Configured",
  automationSupervisorMissing: "Not configured",
  failedToLoadAutomation: "Failed to load automation status",
  copy: "Copy",
  copyEndpoint: "Copy automation endpoint",

  // Status
  statusRunning: "running",
  statusStopped: "stopped",
  statusInitializing: "initializing",

  // Hook errors
  audioStatus: "Audio status",
  audioStatusNormal: "Audio OK",
  audioStatusNoTrack: "No audio track",
  audioStatusNoData: "No audio data",
  audioStatusUnknown: "Audio status unknown",
  audioStatusMuted: "Audio muted",
  clipboardPermissionDenied: "Clipboard access is blocked",
  clipboardPermissionDeniedHint:
    "Click the session and allow clipboard access in your browser, then use the clipboard box in the Selkies sidebar explicitly.",
  clipboardPermissionPrompt: "Clipboard access will be requested",
  clipboardPermissionPromptHint:
    "Clipboard content moves only through the sidebar clipboard box; this page never overwrites it automatically.",
  audioMute: "Mute this page",
  audioUnmute: "Unmute this page",
  runtimeCheckFailed: "Profile runtime check failed (HTTP {status})",
  runtimeNotRunning: "Profile runtime is not running (state: {state})",
  runtimeReportedError: "Profile runtime reported an error (state: {state})",
  runtimeStateUnknown: "unknown",
  iceConnectivityCheckFailed: "WebRTC ICE connectivity check failed",
  iceConnectivityLost: "WebRTC ICE connectivity was lost",
  signalingDisconnected: "Signaling WebSocket disconnected (code {code})",
  mediaFramesTimeout: "No media frames decoded within the timeout window",

  // Browser session diagnostics & actions
  sessionStageCheckingRuntime: "Checking Runtime",
  sessionStageRuntimeNotReady: "Runtime Not Ready",
  sessionStageStopping: "Stopping Session",
  sessionStageConnectingSignaling: "Connecting Signaling",
  sessionStageSignalingFailed: "Signaling Failed",
  sessionStageIceFailed: "ICE Connection Failed",
  sessionStageMediaWaiting: "Waiting for Media",
  sessionStageMediaNoFrames: "No Media Frames Received",
  sessionStageConnected: "Connected",
  sessionStageReconnecting: "Reconnecting",
  sessionStageError: "Session Error",
  sessionReconnect: "Reconnect",
  sessionViewStatus: "View Status",
  sessionToggleDiagnostics: "Diagnostics",
  sessionHideDiagnostics: "Hide Diagnostics",
  sessionDiagConnectionState: "Connection State",
  sessionDiagIceState: "ICE State",
  sessionDiagSignalingState: "Signaling State",
  sessionDiagAudioStatus: "Audio Status",
  sessionDiagRoundTripTime: "Round Trip Time (RTT)",
  sessionDiagPacketsLost: "Packets Lost",
  sessionDiagPacketsReceived: "Packets Received",
  sessionDiagFramesDecoded: "Frames Decoded",
  sessionDiagCandidateType: "Candidate Type",
  sessionDiagRemoteEndpoint: "Remote Endpoint",
  sessionSelectHint:
    "Select a profile from the sidebar to launch or continue a remote browsing session.",
  configure: "Configure",
  files: "Files",
  automation: "Automation",
  startingBrowser: "Starting Browser...",
  launchRemoteBrowser: "Launch Remote Browser",
  profileNotFound: "Profile not found.",
  backToSession: "Back to Session",
  backToDashboard: "Back to Dashboard",
  profileNotFoundOrFailed: "Profile not found or failed to load.",
  profileUpdatedSuccessfully: "Profile updated successfully.",
  proxyUrl: "Proxy URL",
  widthPx: "Width (px)",
  heightPx: "Height (px)",
  tagsCommaSeparated: "Tags (comma separated)",

  failedToFetchProfiles: "Failed to fetch profiles",
  failedToCreateProfile: "Failed to create profile",
  failedToUpdateProfile: "Failed to update profile",
  failedToReorderProfiles: "Failed to reorder profiles",
  failedToDeleteProfile: "Failed to delete profile",
  failedToStopProfile: "Failed to stop profile",
};

const zh: MessageDict = {
  loading: "加载中...",
  retry: "重试",
  cancel: "取消",
  save: "保存",
  saved: "已保存",
  saving: "保存中...",
  create: "创建",
  delete: "删除",
  deleting: "删除中...",
  close: "关闭",
  dismiss: "关闭",
  add: "添加",
  settings: "设置",
  applying: "应用中…",
  test: "测试",

  languageEn: "English",
  languageZh: "中文",
  switchLanguage: "切换语言",
  language: "界面语言",

  unableToReachServer: "无法连接服务器",
  enterAccessToken: "请输入访问令牌",
  accessToken: "访问令牌",
  authenticating: "验证中...",
  unlock: "解锁",
  loginFailed: "登录失败",
  logOut: "退出登录",

  hideSidebar: "隐藏侧边栏",
  showSidebar: "显示侧边栏",
  quitManager: "退出管理器（会停止服务）",
  quitConfirm:
    "退出 CBrowser？这将停止服务并关闭所有正在运行的配置。",
  managerStopped: "CBrowser 已停止",
  managerStoppedHint: "服务已不再运行，可以关闭此标签页。",
  managerStoppedRelaunch: "重新启动应用即可再次使用。",
  selectOrCreateProfile: "请选择一个配置，或新建配置",
  noLicenseKeySet: "尚未设置许可证密钥",
  noLicenseKeyBody:
    "当前运行的是免费无密钥构建。添加密钥后可使用最新的 Pro 构建。",
  enterKeyInSettings: "在设置中输入密钥",
  getFreeKey: "获取免费密钥",
  seeProPlans: "查看 Pro 方案 →",
  orContinueKeyless: "也可以选择或新建配置，继续以无密钥方式使用。",
  failedToLaunchProfile: "启动配置失败",

  searchProfiles: "搜索配置...",
  noProfilesYet: "暂无配置",
  noMatches: "无匹配结果",
  runningCount: "运行中 {count} 个",
  proxy: "代理",
  newProfile: "新建配置",

  firstTimeSetup: "首次初始化...",
  stopping: "停止中...",
  launching: "启动中...",
  stop: "停止",
  launch: "启动",
  runtimeNotReady: "运行时未就绪",
  runtimeCoordinatorError: "运行时协调错误：{error}",
  displaySettingsSavedPending: "设置已保存，重启后生效。",
  displayApplyAndRestart: "应用并重启",
  displayApplyingRestart: "正在应用并重启...",
  displayApplyFailed: "应用显示尺寸失败：{error}",
  upgradePlan: "升级方案",
  dismissLaunchError: "关闭启动错误",
  updateAvailable: "CBrowser {version} 已可用。",
  download: "下载",
  dismissUpdate: "关闭更新提示",

  tierPro: "Pro",
  tierFree: "免费密钥",
  tierKeyless: "免费（无密钥）",
  tierKeylessTitle:
    "尚未设置许可证密钥。当前为免费无密钥构建。打开设置添加密钥以使用最新 Pro 构建。",
  tierLicenseTitle: "{tier} 许可证 — 运行 {version}",
  fontsIncomplete: "字体不完整",
  fontsIncompleteTitle: "Windows 人设字体不完整：已找到 {present}/{required}",

  licenseKey: "CBrowser 许可证密钥",
  licenseKeyPlaceholderSet: "当前：{masked} — 输入以替换",
  licenseKeyPlaceholderEmpty: "cb_…（留空则使用免费无密钥构建）",
  licenseKeyHelp: "每个管理器实例一把密钥 — 所有配置共享席位池。",
  releaseChannel: "发布通道",
  channelStable: "稳定版",
  channelPreview: "预览版（抢先体验）",
  removeKey: "移除密钥",
  failedToLoadSettings: "加载设置失败",
  failedToSaveSettings: "保存设置失败",
  failedToClearKey: "清除密钥失败",
  systemGatewayControlApi: "系统网关与控制 API",
  systemApiServicesStatus: "v2 API 服务状态",
  healthHealthy: "正常",
  healthChecking: "检查中...",
  healthUnreachable: "无法访问",

  editProfile: "编辑配置",
  deleteProfileConfirm: "删除该配置？浏览器数据将被永久移除。",
  resetProfileConfirm:
    "重置该配置？Cookie、历史记录和站点数据将被清除，并生成新指纹。书签、设置和默认搜索会保留。",
  duplicateWithStateConfirm:
    "复制该配置及其浏览器状态？将创建具有相同设置、指纹、Cookie 和已登录会话的新配置。",
  duplicateSettingsConfirm:
    "复制该配置？将创建具有相同设置和指纹的新配置。浏览器状态（Cookie、历史）不会复制。",
  duplicate: "复制",
  duplicating: "复制中...",
  duplicateSettingsOnly: "仅复制设置与指纹",
  failedToDuplicateProfile: "复制配置失败",
  failedToResetProfile: "重置配置失败",
  duplicateProfileTitle: "复制配置",
  duplicateProfileHint:
    "复制设置与指纹。仅在源已停止时复制浏览器状态；不复制 Artifact。",
  resetProfileTitle: "重置浏览器状态",
  resetProfileDataList:
    "将清除此配置的全部浏览器数据，包括 Cookie、站点数据、缓存、历史、书签、保存的密码、扩展与登录状态，并重新生成指纹身份。",
  resetProfileKeeps: "保留设置、标签、备注与 Artifact；不影响其他配置。",
  duplicateOptions: "复制选项",
  duplicateSettingsOnlyTitle: "仅设置与指纹",
  duplicateSettingsOnlyHint: "以空的浏览器状态开始",
  duplicateWithStateTitle: "包含浏览器状态",
  duplicateWithStateHint: "Cookie、已登录会话与历史记录",
  stopProfileFirst: "请先停止该配置",
  reset: "重置",
  resetting: "重置中...",
  resetDone: "已重置",
  lastPreview: "最近预览",
  lastBrowserPreview: "最近浏览器预览",
  basic: "基础",
  profileName: "配置名称",
  profileNamePlaceholder: "例如：Amazon Seller #1",
  profileNameExample: "例如：工作配置",
  proxyUrlOptional: "代理 URL（可选）",
  tagsPlaceholder: "开发, 调研, 购物",
  fingerprintSeed: "指纹种子",
  autoRandom: "自动（随机）",
  randomizeSeed: "随机生成种子",
  network: "网络",
  timezone: "时区",
  locale: "语言区域",
  geoipAutoDetect:
    "根据代理出口 IP（或无代理时的本机公网 IP）自动识别时区/语言（GeoIP）",
  proxyTestFailed: "代理测试失败",
  hardware: "硬件",
  screenResolution: "屏幕分辨率",
  custom: "自定义",
  width: "宽度",
  height: "高度",
  gpuFamily: "GPU 系列",
  appleSiliconAuto: "Apple Silicon（自动）",
  detectingRuntime: "自动（正在检测运行环境…）",
  autoFromSeed: "自动（基于种子）",
  gpuAppleHint: "种子会选择一致的 Apple Silicon 型号及匹配的硬件配置。",
  gpuFamilyHint: "种子会在所选系列内选择一致的 GPU、CPU、内存与屏幕配置。",
  behavior: "行为",
  humanLikeBehavior: "启用拟人化鼠标、键盘与滚动行为",
  humanPreset: "拟人化预设",
  humanPresetDefault: "默认（正常速度）",
  humanPresetCareful: "谨慎（更慢、更稳）",
  enableClipboardByDefault: "在 VNC 查看器中默认启用剪贴板同步",
  autoLaunch: "管理器启动时自动启动此配置",
  capturePreview: "保存浏览器预览截图",
  capturePreviewHint: "运行期间定期截取页面，配置停止后显示在此处。",
  restoreSession: "启动时恢复上次标签页",
  restoreSessionHint: "重新打开该配置上次停止时所开的标签页。",
  compatibility: "兼容性",
  allow3pCookies: "允许第三方 Cookie（登录、SSO 与验证流程）",
  transparentProxy: "透明代理连接",
  transparentProxyHint:
    "更强的代理连接模式。需要带用户名和密码的 http:// 代理。",
  portableCookies: "可移植 Cookie",
  portableCookiesHint:
    "允许将此配置连同登录状态迁移到另一台机器。仅在此选项开启期间保存的 Cookie 可移植，请在登录前开启。",
  setGoogleDefault: "将 Google 设为默认搜索引擎",
  setGoogleDefaultHint: "首次启动该配置时会多花几秒（一次性设置）。",
  tags: "标签",
  addTag: "添加标签...",
  extensions: "扩展",
  extensionsHelp: "每个路径添加一个未打包的 Chrome 扩展目录。",
  advancedLaunchArgs: "高级启动参数",
  advancedLaunchArgsHelp:
    "不受限的 Chromium 参数。高级参数可能覆盖管理器控制的行为。",
  notes: "备注",
  optionalNotes: "关于该配置的可选备注...",

  connectionFailed: "连接失败",
  failedToConnect: "连接失败",
  connected: "已连接",
  connecting: "连接中...",
  copied: "已复制！",
  copyCdpUrl: "复制 CDP 地址",
  disableClipboardSync: "关闭剪贴板同步",
  enableClipboardSync: "开启剪贴板同步",
  exitFullscreen: "退出全屏",
  fullscreen: "全屏",
  centerWindow: "居中复位窗口",
  sendToBrowser: "发送剪贴板文本到浏览器",
  sendTextPlaceholder: "在此输入或粘贴文本，直接推送到远程浏览器...",
  send: "发送",
  uploadingToProfile: "正在上传到此配置...",
  inProfileFilesHint:
    "已在配置文件中 — 请在页面文件对话框的「上传 — {name}」中选择",
  dropToUpload: "拖放以上传到此配置",
  dropToUploadHint: "然后在页面文件对话框的「上传 — {name}」中选择",
  openedInNativeWindow: "已在原生窗口中打开",
  nativeWindowHint:
    "{name} 正在本机直接运行。请使用其 CBrowser 窗口浏览。",
  automationViaCdp: "仍可通过管理器 CDP 进行自动化",
  liveBrowserPreview: "实时浏览器预览",

  profileFilesTitle: "此配置可用的文件",
  profileFiles: "配置文件",
  filesForProfile: "此配置的文件",
  profileFilesAria: "配置文件，{count} 个{filesWord}",
  fileSingular: "文件",
  filePlural: "文件",
  dismissError: "关闭错误",
  noFilesYet: "暂无文件。可上传、拖放到画面，或在浏览器中下载。",
  downloadedByBrowser: "由浏览器下载",
  uploaded: "已上传",
  downloading: "下载中...",
  downloadFailed: "下载失败",
  downloadToComputer: "下载到本机",
  removeFromProfile: "从此配置中移除",
  removeFileAria: "移除 {name}",
  uploading: "上传中...",
  uploadAFile: "上传文件",
  uploadsSidebarHint: "在页面文件对话框侧边栏中选择「上传 — {name}」。",
  failedToListFiles: "获取文件列表失败",
  uploadFailed: "上传失败",
  deleteFailed: "删除失败",
  profileFilesHint:
    "上传与下载均由 Artifact Service 管理，不经过 Selkies 文件传输。",
  artifactsUploaded: "已上传 {count} 个文件",
  deleteArtifactConfirm: "确定从此配置删除该文件？",
  automationPageTitle: "CDP 自动化",
  automationPageHint:
    "经 Supervisor 与 Agent UDS 提供给外部自动化的授权端点。",
  automationEndpoint: "授权 WebSocket 端点",
  automationTokenHeader: "请求时携带自动化令牌：{value}",
  automationRuntimeState: "运行状态",
  automationRuntimeInstance: "运行实例",
  automationSupervisor: "Supervisor",
  automationSupervisorReady: "已配置",
  automationSupervisorMissing: "未配置",
  failedToLoadAutomation: "获取自动化状态失败",
  copy: "复制",
  copyEndpoint: "复制自动化端点",

  statusRunning: "运行中",
  statusStopped: "已停止",
  statusInitializing: "初始化中",

  audioStatus: "音频状态",
  audioStatusNormal: "音频正常",
  audioStatusNoTrack: "无音频轨道",
  audioStatusNoData: "音频无数据",
  audioStatusUnknown: "音频状态未知",
  audioStatusMuted: "已静音",
  clipboardPermissionDenied: "剪贴板权限被拒绝",
  clipboardPermissionDeniedHint:
    "点击会话页面并在浏览器中允许剪贴板访问，然后显式使用 Selkies 侧栏的剪贴板输入框。",
  clipboardPermissionPrompt: "剪贴板访问将按需请求",
  clipboardPermissionPromptHint:
    "只有通过侧栏剪贴板输入框才会传输内容；本页面不会自动覆盖本机剪贴板。",
  audioMute: "静音本页",
  audioUnmute: "取消本页静音",
  runtimeCheckFailed: "配置运行时检查失败（HTTP {status}）",
  runtimeNotRunning: "配置运行时未运行（状态：{state}）",
  runtimeReportedError: "配置运行时报告错误（状态：{state}）",
  runtimeStateUnknown: "未知",
  iceConnectivityCheckFailed: "WebRTC ICE 连接检查失败",
  iceConnectivityLost: "WebRTC ICE 连接已丢失",
  signalingDisconnected: "信令 WebSocket 已断开（代码 {code}）",
  mediaFramesTimeout: "超时未收到解码画面",

  // Browser session diagnostics & actions
  sessionStageCheckingRuntime: "检查运行时状态",
  sessionStageRuntimeNotReady: "运行时未就绪",
  sessionStageStopping: "正在停止会话",
  sessionStageConnectingSignaling: "正在连接信令服务器",
  sessionStageSignalingFailed: "信令连接失败",
  sessionStageIceFailed: "ICE 协商失败",
  sessionStageMediaWaiting: "等待媒体流渲染",
  sessionStageMediaNoFrames: "媒体未产生画面",
  sessionStageConnected: "已连接",
  sessionStageReconnecting: "正在重新连接",
  sessionStageError: "会话错误",
  sessionReconnect: "重连",
  sessionViewStatus: "查看运行状态",
  sessionToggleDiagnostics: "诊断",
  sessionHideDiagnostics: "隐藏诊断",
  sessionDiagConnectionState: "连接状态",
  sessionDiagIceState: "ICE 状态",
  sessionDiagSignalingState: "信令状态",
  sessionDiagAudioStatus: "音频状态",
  sessionDiagRoundTripTime: "往返时延 (RTT)",
  sessionDiagPacketsLost: "丢包数",
  sessionDiagPacketsReceived: "接收包数",
  sessionDiagFramesDecoded: "已解码帧数",
  sessionDiagCandidateType: "候选类型",
  sessionDiagRemoteEndpoint: "远端地址",
  sessionSelectHint: "从侧边栏选择一个配置，以启动或继续远程浏览会话。",
  configure: "配置",
  files: "文件",
  automation: "自动化",
  startingBrowser: "正在启动浏览器...",
  launchRemoteBrowser: "启动远程浏览器",
  profileNotFound: "未找到配置。",
  backToSession: "返回会话",
  backToDashboard: "返回控制台",
  profileNotFoundOrFailed: "配置不存在或加载失败。",
  profileUpdatedSuccessfully: "配置更新成功。",
  proxyUrl: "代理 URL",
  widthPx: "宽度 (px)",
  heightPx: "高度 (px)",
  tagsCommaSeparated: "标签（逗号分隔）",

  failedToFetchProfiles: "获取配置列表失败",
  failedToCreateProfile: "创建配置失败",
  failedToUpdateProfile: "更新配置失败",
  failedToReorderProfiles: "调整配置顺序失败",
  failedToDeleteProfile: "删除配置失败",
  failedToStopProfile: "停止配置失败",
};

export type TranslationKey = keyof typeof en;

const messages = { en, zh } as const;

const STORAGE_KEY = "cbm.locale";

interface I18nContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: TranslationKey, params?: Params) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

function detectInitialLocale(): Locale {
  if (typeof window === "undefined") return "en";
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "zh" || stored === "en") return stored;
  const nav = (navigator.language || "").toLowerCase();
  return nav.startsWith("zh") ? "zh" : "en";
}

function interpolate(template: string, params?: Params): string {
  if (!params) return template;
  let out = template;
  for (const [name, value] of Object.entries(params)) {
    out = out.replaceAll(`{${name}}`, String(value));
  }
  return out;
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(() => detectInitialLocale());

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    localStorage.setItem(STORAGE_KEY, next);
  }, []);

  const t = useCallback(
    (key: TranslationKey, params?: Params) => {
      const template = messages[locale][key] ?? messages.en[key] ?? String(key);
      return interpolate(template, params);
    },
    [locale],
  );

  const value = useMemo(() => ({ locale, setLocale, t }), [locale, setLocale, t]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used within I18nProvider");
  return ctx;
}
