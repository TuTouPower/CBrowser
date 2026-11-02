import {
  createContext,
  useCallback,
  useContext,
  useEffect,
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
  cancel: "Cancel",
  save: "Save",
  saving: "Saving...",
  create: "Create",
  delete: "Delete",
  settings: "Settings",
  languageEn: "English",
  languageZh: "中文",
  switchLanguage: "Switch language",
  language: "Language",

  // Auth / login
  enterAccessToken: "Enter your access token",
  accessToken: "Access token",
  authenticating: "Authenticating...",
  unlock: "Unlock",
  loginFailed: "Login failed",
  logOut: "Log out",

  // App chrome
  hideSidebar: "Hide sidebar",
  showSidebar: "Show sidebar",
  selectOrCreateProfile: "Select a profile or create a new one",
  searchProfiles: "Search profiles...",
  noProfilesYet: "No profiles yet",
  noMatches: "No matches",
  newProfile: "New Profile",

  // Launch
  stop: "Stop",
  launch: "Launch",
  runtimeNotReady: "Runtime not ready",
  runtimeCoordinatorError: "Runtime coordination error: {error}",
  displaySettingsSavedPending:
    "Settings saved. Restart the profile to apply the new display size.",
  displayApplyAndRestart: "Apply and restart",
  displayApplyingRestart: "Applying and restarting...",
  displayApplyFailed: "Failed to apply display size: {error}",
  systemGatewayControlApi: "System Gateway & Control API",
  systemApiServicesStatus: "Status of v2 API services",
  healthHealthy: "Healthy",
  healthChecking: "Checking...",
  healthUnreachable: "Unreachable",

  // Profile form
  editProfile: "Edit Profile",
  deleteProfileConfirm:
    "Delete this profile? Browser data will be permanently removed.",
  duplicate: "Duplicate",
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
  duplicateWithStateTitle: "With browser state",
  stopProfileFirst: "Stop the profile first",
  reset: "Reset",
  resetting: "Resetting...",
  profileName: "Profile Name",
  profileNameExample: "e.g. Work Profile",
  proxyUrlOptional: "Proxy URL (optional)",
  tagsPlaceholder: "dev, research, shopping",
  copied: "Copied!",
  profileFiles: "Profile files",
  noFilesYet:
    "No files yet. Upload one, drop it onto the screen, or download one in the browser.",
  downloadedByBrowser: "Downloaded by the browser",
  uploaded: "Uploaded",
  downloadToComputer: "Download to this computer",
  removeFromProfile: "Remove from the profile",
  uploading: "Uploading...",
  uploadAFile: "Upload a file",
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
  audioStatusNormal: "Audio OK",
  audioStatusNoTrack: "No audio track",
  audioStatusNoData: "No audio data",
  audioStatusUnknown: "Audio status unknown",
  audioStatusMuted: "Audio muted",
  clipboardPermissionDenied: "Clipboard access is blocked",
  clipboardPermissionDeniedHint:
    "Click the session and allow clipboard access in your browser so copy and paste sync automatically with the remote browser.",
  clipboardPermissionPrompt: "Clipboard access will be requested",
  clipboardPermissionPromptHint:
    "When the session gets focus, the browser asks for clipboard access; allow it so copied text syncs both ways automatically.",
  audioMute: "Mute this page",
  audioUnmute: "Unmute this page",
  runtimeCheckUnavailable: "Profile runtime status unavailable: {reason}",
  runtimeNotRunning: "Profile runtime is not running (state: {state})",
  sessionStartFailed: "Failed to start the session: {error}",
  runtimeReportedError: "Profile runtime reported an error (state: {state})",
  runtimeStateUnknown: "unknown",
  iceConnectivityCheckFailed: "WebRTC ICE connectivity check failed",
  iceConnectivityLost: "WebRTC ICE connectivity was lost",
  signalingDisconnected: "Signaling WebSocket disconnected (code {code})",
  webLocksUnavailable:
    "This browser does not provide Web Locks, so tab identity cannot be kept safe.",
  mediaFramesTimeout: "No media frames decoded within the timeout window",

  // Browser session diagnostics & actions
  sessionStageCheckingRuntime: "Checking Runtime",
  sessionStageRuntimeNotReady: "Runtime Not Ready",
  sessionStageStopping: "Stopping Session",
  sessionStageConnectingSignaling: "Connecting Signaling",
  sessionStageSignalingFailed: "Signaling Failed",
  sessionStageWebLocksUnavailable: "Web Locks Unavailable",
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

  failedToCreateProfile: "Failed to create profile",
  failedToUpdateProfile: "Failed to update profile",
  failedToDeleteProfile: "Failed to delete profile",

};

const zh: MessageDict = {
  loading: "加载中...",
  cancel: "取消",
  save: "保存",
  saving: "保存中...",
  create: "创建",
  delete: "删除",
  settings: "设置",
  languageEn: "English",
  languageZh: "中文",
  switchLanguage: "切换语言",
  language: "界面语言",

  enterAccessToken: "请输入访问令牌",
  accessToken: "访问令牌",
  authenticating: "验证中...",
  unlock: "解锁",
  loginFailed: "登录失败",
  logOut: "退出登录",

  hideSidebar: "隐藏侧边栏",
  showSidebar: "显示侧边栏",
  selectOrCreateProfile: "请选择一个配置，或新建配置",
  searchProfiles: "搜索配置...",
  noProfilesYet: "暂无配置",
  noMatches: "无匹配结果",
  newProfile: "新建配置",

  stop: "停止",
  launch: "启动",
  runtimeNotReady: "运行时未就绪",
  runtimeCoordinatorError: "运行时协调错误：{error}",
  displaySettingsSavedPending: "设置已保存，重启后生效。",
  displayApplyAndRestart: "应用并重启",
  displayApplyingRestart: "正在应用并重启...",
  displayApplyFailed: "应用显示尺寸失败：{error}",
  systemGatewayControlApi: "系统网关与控制 API",
  systemApiServicesStatus: "v2 API 服务状态",
  healthHealthy: "正常",
  healthChecking: "检查中...",
  healthUnreachable: "无法访问",

  editProfile: "编辑配置",
  deleteProfileConfirm: "删除该配置？浏览器数据将被永久移除。",
  duplicate: "复制",
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
  duplicateWithStateTitle: "包含浏览器状态",
  stopProfileFirst: "请先停止该配置",
  reset: "重置",
  resetting: "重置中...",
  profileName: "配置名称",
  profileNameExample: "例如：工作配置",
  proxyUrlOptional: "代理 URL（可选）",
  tagsPlaceholder: "开发, 调研, 购物",
  copied: "已复制！",
  profileFiles: "配置文件",
  noFilesYet: "暂无文件。可上传、拖放到画面，或在浏览器中下载。",
  downloadedByBrowser: "由浏览器下载",
  uploaded: "已上传",
  downloadToComputer: "下载到本机",
  removeFromProfile: "从此配置中移除",
  uploading: "上传中...",
  uploadAFile: "上传文件",
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
  audioStatusNormal: "音频正常",
  audioStatusNoTrack: "无音频轨道",
  audioStatusNoData: "音频无数据",
  audioStatusUnknown: "音频状态未知",
  audioStatusMuted: "已静音",
  clipboardPermissionDenied: "剪贴板权限被拒绝",
  clipboardPermissionDeniedHint:
    "点击会话页面并在浏览器中允许剪贴板访问，本机与远程浏览器之间的复制粘贴才会自动同步。",
  clipboardPermissionPrompt: "剪贴板访问将按需请求",
  clipboardPermissionPromptHint:
    "会话页面获得焦点时浏览器会请求剪贴板权限；允许后复制的文本双向自动同步。",
  audioMute: "静音本页",
  audioUnmute: "取消本页静音",
  runtimeCheckUnavailable: "无法获取运行时状态：{reason}",
  runtimeNotRunning: "配置运行时未运行（状态：{state}）",
  sessionStartFailed: "启动会话失败：{error}",
  runtimeReportedError: "配置运行时报告错误（状态：{state}）",
  runtimeStateUnknown: "未知",
  iceConnectivityCheckFailed: "WebRTC ICE 连接检查失败",
  iceConnectivityLost: "WebRTC ICE 连接已丢失",
  signalingDisconnected: "信令 WebSocket 已断开（代码 {code}）",
  webLocksUnavailable:
    "当前浏览器不支持 Web Locks，无法安全保持标签页身份。",
  mediaFramesTimeout: "超时未收到解码画面",

  // Browser session diagnostics & actions
  sessionStageCheckingRuntime: "检查运行时状态",
  sessionStageRuntimeNotReady: "运行时未就绪",
  sessionStageStopping: "正在停止会话",
  sessionStageConnectingSignaling: "正在连接信令服务器",
  sessionStageSignalingFailed: "信令连接失败",
  sessionStageWebLocksUnavailable: "Web Locks 不可用",
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

  failedToCreateProfile: "创建配置失败",
  failedToUpdateProfile: "更新配置失败",
  failedToDeleteProfile: "删除配置失败",

};

export type TranslationKey = keyof typeof en;

const messages = { en, zh } as const;

const STORAGE_KEY = "cbrowser.locale";
const LEGACY_STORAGE_KEY = "cbm.locale";

interface I18nContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: TranslationKey, params?: Params) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

function detectInitialLocale(): Locale {
  if (typeof window === "undefined") return "en";
  const stored =
    localStorage.getItem(STORAGE_KEY) ?? localStorage.getItem(LEGACY_STORAGE_KEY);
  if (stored === "zh" || stored === "en") {
    if (!localStorage.getItem(STORAGE_KEY)) {
      localStorage.setItem(STORAGE_KEY, stored);
      localStorage.removeItem(LEGACY_STORAGE_KEY);
    }
    return stored;
  }
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

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    localStorage.setItem(STORAGE_KEY, next);
    localStorage.removeItem(LEGACY_STORAGE_KEY);
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
