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
  font_bundle: "none",
  allow_3p_cookies: true,
  set_google_default: true,
  capture_preview: true,
  restore_session: true,
  transparent_proxy: false,
  portable_cookies: false,
  sort_order: 0,
};
