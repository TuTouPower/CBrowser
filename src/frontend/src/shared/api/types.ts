import type { components, paths } from "./generated/cbrowser_v1";

export type Schemas = components["schemas"];

export type ArtifactResponse = Schemas["ArtifactResponse"];
export type AutomationEndpointResponse = Schemas["AutomationEndpointResponse"];
export type ProfileResponse = Schemas["ProfileResponse"];
export type ProfileCreateRequest = Schemas["ProfileCreateRequest"];
export type ProfileUpdateRequest = Schemas["ProfileUpdateRequest"];
export type ProfileRuntimeResponse = Schemas["ProfileRuntimeResponse"];
export type ProfileRuntimeStatusEvent = Schemas["ProfileRuntimeStatusEvent"];
export type ProfileControlStateData = Schemas["ProfileControlStateData"];
export type SearchDefaultsStatusData = Schemas["SearchDefaultsStatusData"];
export type LoginRequest = Schemas["LoginRequest"];
export type LoginResponse = Schemas["LoginResponse"];
export type SessionResponse = Schemas["SessionResponse"];
export type GroupResponse = Schemas["GroupResponse"];
export type GroupCreateRequest = Schemas["GroupCreateRequest"];
export type GroupUpdateRequest = Schemas["GroupUpdateRequest"];
export type GroupReorderRequest = Schemas["GroupReorderRequest"];
export type ProxyResponse = Schemas["ProxyResponse"];
export type ProxyCreateRequest = Schemas["ProxyCreateRequest"];
export type ProxyUpdateRequest = Schemas["ProxyUpdateRequest"];
export type FontSetInfo = Schemas["FontSetInfo"];
export type FontSetIntegrity = Schemas["FontSetIntegrity"];

export type ApiPaths = paths;

export const DEFAULT_PROFILE_CREATE_VALUES: Omit<ProfileCreateRequest, "name"> = {
  screen_width: 1920,
  screen_height: 1080,
  gpu_family: "auto",
  humanize: false,
  human_preset: "default",
  geoip: true,
  clipboard_sync: true,
  auto_launch: false,
  allow_3p_cookies: true,
  set_google_default: true,
  capture_preview: true,
  restore_session: true,
  transparent_proxy: false,
  portable_cookies: false,
  sort_order: 0,
  fingerprint_platform: "windows",
  font_set_id: null,
  group_id: null,
  proxy_id: null,
  notes: null,
  timezone: null,
  locale: null,
  color_scheme: null,
  launch_args: [],
  extension_paths: [],
};
