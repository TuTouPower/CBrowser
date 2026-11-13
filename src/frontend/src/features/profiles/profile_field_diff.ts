import {
  PROFILE_INSTANT_FIELDS,
  PROFILE_METADATA_FIELDS,
  PROFILE_RUNTIME_FIELDS,
} from "../../shared/api/generated/profile_field_classification";
import type {
  ProfileCreateRequest,
  ProfileUpdateRequest,
} from "../../shared/api/types";

// t058 A24: the backend owns the profile field classification
// (metadata / instant / runtime). These sets are generated from the
// backend constants — never hand-copied — so the frontend can never
// drift from the config-version rule again.
export type ProfileFieldClass = "metadata" | "instant" | "runtime";

const METADATA_FIELDS = new Set<string>(PROFILE_METADATA_FIELDS);
const INSTANT_FIELDS = new Set<string>(PROFILE_INSTANT_FIELDS);
const RUNTIME_FIELDS = new Set<string>(PROFILE_RUNTIME_FIELDS);

export function classifyProfileField(key: string): ProfileFieldClass | null {
  if (METADATA_FIELDS.has(key)) return "metadata";
  if (INSTANT_FIELDS.has(key)) return "instant";
  if (RUNTIME_FIELDS.has(key)) return "runtime";
  return null;
}

function valuesEqual(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

/**
 * The incremental PATCH payload for an edit: only the fields whose
 * value differs from the baseline. A field another client changed in
 * the meantime is never written back with a stale value.
 */
export function diffProfileValues(
  current: ProfileCreateRequest,
  baseline: ProfileCreateRequest,
): ProfileUpdateRequest {
  const diff = {} as ProfileUpdateRequest;
  for (const key of Object.keys(current) as Array<
    keyof ProfileCreateRequest
  >) {
    if (!valuesEqual(current[key], baseline[key])) {
      (diff as Record<string, unknown>)[key] = current[key];
    }
  }
  return diff;
}

/**
 * Whether any changed field is a runtime field, i.e. the change creates
 * a new config version. Metadata and instant changes do not. A field
 * the backend does not classify counts as runtime: an unknown field
 * must never be silently treated as cheap.
 */
export function hasRuntimeConfigChange(
  current: ProfileCreateRequest,
  baseline: ProfileCreateRequest,
): boolean {
  return (Object.keys(current) as Array<keyof ProfileCreateRequest>).some(
    (key) =>
      !valuesEqual(current[key], baseline[key]) &&
      classifyProfileField(key) !== "metadata" &&
      classifyProfileField(key) !== "instant",
  );
}
