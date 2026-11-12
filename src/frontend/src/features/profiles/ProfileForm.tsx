import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import {
  Banner,
  Button,
  Checkbox,
  FieldLabel,
  Input,
  Select,
  type SelectOption,
} from "../../shared/ui";
import { useI18n, type TranslationKey } from "../../i18n";
import { useApiClient } from "../../shared/api/client_context";
import { DEFAULT_PROFILE_CREATE_VALUES } from "../../shared/api/types";
import type {
  FontSetInfo,
  GroupResponse,
  ProfileCreateRequest,
  ProfileResponse,
  ProfileUpdateRequest,
  ProxyResponse,
} from "../../shared/api/types";
import {
  useCreateGroupMutation,
  useFontSetsQuery,
  useGroupsQuery,
  useProxiesQuery,
} from "./useProfilesQuery";
import { localeForTimezone } from "./profile_locale";
import { diffProfileValues } from "./profile_field_diff";
import { TimezoneCombobox } from "./TimezoneCombobox";

export type ProfileFormValues = ProfileCreateRequest;

export interface ProfileFormProps {
  mode: "create" | "edit";
  initial?: ProfileResponse;
  onSubmit: (
    values: ProfileCreateRequest | ProfileUpdateRequest,
  ) => Promise<void>;
  submitLabel?: string;
  isPending?: boolean;
}

const EMPTY_GROUPS: GroupResponse[] = [];
const EMPTY_PROXIES: ProxyResponse[] = [];
const EMPTY_FONT_SETS: FontSetInfo[] = [];

function normalizePlatform(value: string | undefined): "windows" | "macos" {
  return value === "macos" ? "macos" : "windows";
}

function normalizeGpu(value: string): "auto" | "nvidia" | "intel" {
  return value === "nvidia" || value === "intel" ? value : "auto";
}

function normalizePreset(value: string): "default" | "careful" {
  return value === "careful" ? "careful" : "default";
}

function normalizeColorScheme(
  value: string | null | undefined,
): "light" | "dark" | "no-preference" | null {
  return value === "light" || value === "dark" || value === "no-preference"
    ? value
    : null;
}

function toFormValues(initial?: ProfileResponse): ProfileFormValues {
  if (!initial) {
    return { name: "", ...DEFAULT_PROFILE_CREATE_VALUES };
  }
  return {
    name: initial.name,
    fingerprint_seed: initial.fingerprint_seed,
    group_id: initial.group_id ?? null,
    proxy_id: initial.proxy_id ?? null,
    timezone: initial.timezone ?? null,
    locale: initial.locale ?? null,
    screen_width: initial.screen_width,
    screen_height: initial.screen_height,
    gpu_family: normalizeGpu(initial.gpu_family),
    humanize: initial.humanize,
    human_preset: normalizePreset(initial.human_preset),
    geoip: initial.geoip,
    clipboard_sync: initial.clipboard_sync,
    auto_launch: initial.auto_launch,
    color_scheme: normalizeColorScheme(initial.color_scheme),
    fingerprint_platform: normalizePlatform(initial.fingerprint_platform),
    font_set_id: initial.font_set_id ?? null,
    launch_args: initial.launch_args ?? [],
    extension_paths: initial.extension_paths ?? [],
    allow_3p_cookies: initial.allow_3p_cookies,
    set_google_default: initial.set_google_default,
    capture_preview: initial.capture_preview,
    restore_session: initial.restore_session,
    transparent_proxy: initial.transparent_proxy,
    portable_cookies: initial.portable_cookies,
    notes: initial.notes ?? null,
    sort_order: initial.sort_order,
  };
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-xs">
      <FieldLabel>{label}</FieldLabel>
      {children}
    </div>
  );
}

function BoolRow({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="flex items-center gap-sm font-ui text-body-sm text-on-surface">
      <Checkbox checked={checked} onCheckedChange={onChange} label={label} />
      <span>{label}</span>
    </label>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="flex flex-col gap-md rounded-md border border-outline bg-surface p-md">
      <h2 className="font-ui text-headline-md text-on-surface">{title}</h2>
      {children}
    </section>
  );
}

const ADVANCED_BOOL_FIELDS: Array<{
  key: keyof ProfileFormValues;
  labelKey: TranslationKey;
}> = [
  { key: "humanize", labelKey: "formHumanize" },
  { key: "clipboard_sync", labelKey: "formClipboardSync" },
  { key: "auto_launch", labelKey: "formAutoLaunch" },
  { key: "allow_3p_cookies", labelKey: "formAllow3pCookies" },
  { key: "set_google_default", labelKey: "formSetGoogleDefault" },
  { key: "restore_session", labelKey: "formRestoreSession" },
  { key: "transparent_proxy", labelKey: "formTransparentProxy" },
  { key: "portable_cookies", labelKey: "formPortableCookies" },
  { key: "capture_preview", labelKey: "formCapturePreview" },
];

export function ProfileForm({
  mode,
  initial,
  onSubmit,
  submitLabel,
  isPending = false,
}: ProfileFormProps) {
  const { t } = useI18n();
  const client = useApiClient();
  const { data: groupsData } = useGroupsQuery(client);
  const { data: proxiesData } = useProxiesQuery(client);
  const { data: fontSetsData } = useFontSetsQuery(client);
  const createGroupMutation = useCreateGroupMutation(client);

  const groups = groupsData ?? EMPTY_GROUPS;
  const proxies = proxiesData ?? EMPTY_PROXIES;
  const fontSets = fontSetsData?.items ?? EMPTY_FONT_SETS;
  const defaultFontSetId = fontSetsData?.default_font_set_id ?? {};

  const [values, setValues] = useState<ProfileFormValues>(() =>
    toFormValues(initial),
  );
  const baselineRef = useRef<ProfileFormValues>(toFormValues(initial));
  const intentRef = useRef<"create" | "create-start" | "save">("create");
  const [showErrors, setShowErrors] = useState(false);
  const [creatingGroup, setCreatingGroup] = useState(false);
  const [newGroupName, setNewGroupName] = useState("");
  const [groupError, setGroupError] = useState<string | null>(null);
  // P1-13: 本地提交态与父级 pending 合并禁用，防双击重复创建。
  const [submitting, setSubmitting] = useState(false);
  const submitDisabled = submitting || isPending;

  const setField = <K extends keyof ProfileFormValues>(
    key: K,
    value: ProfileFormValues[K],
  ) => {
    setValues((prev) => ({ ...prev, [key]: value }) as ProfileFormValues);
  };

  const platform = normalizePlatform(values.fingerprint_platform);
  const platformFontSets = useMemo(
    () => fontSets.filter((fontSet) => fontSet.platform === platform),
    [fontSets, platform],
  );
  const sortedFontSets = useMemo(
    () =>
      [...platformFontSets].sort((a, b) =>
        (b.created_at ?? "").localeCompare(a.created_at ?? ""),
      ),
    [platformFontSets],
  );

  // A16: the default font set comes only from the backend
  // (`default_font_set_id` per platform, integrity-ok only). The form
  // never derives a default of its own. The refs below make "none" a
  // sticky, explicit choice: once the user picks it, the backend default
  // is never re-applied over it.
  const fontSetUserChosenRef = useRef(false);
  const defaultFontSetAppliedRef = useRef<string | null>(null);

  useEffect(() => {
    if (mode !== "create" || fontSetUserChosenRef.current) return;
    if (!fontSetsData) return;
    if (defaultFontSetAppliedRef.current === platform) return;
    defaultFontSetAppliedRef.current = platform;
    const fallback = defaultFontSetId[platform] ?? null;
    setValues(
      (prev) => ({ ...prev, font_set_id: fallback }) as ProfileFormValues,
    );
  }, [mode, platform, fontSetsData, defaultFontSetId]);

  const selectedFontSet = platformFontSets.find(
    (fontSet) => fontSet.set_id === values.font_set_id,
  );
  const missingFontSet =
    values.font_set_id != null && selectedFontSet === undefined;
  const inconsistent =
    selectedFontSet !== undefined && !selectedFontSet.integrity.ok;

  const groupOptions: SelectOption[] = [
    { value: "__none__", label: t("envUngrouped") },
    ...groups.map((item) => ({ value: item.id, label: item.name })),
    { value: "__create_group__", label: t("formNewGroup") },
  ];
  const proxyOptions: SelectOption[] = [
    { value: "__direct__", label: t("formDirect") },
    ...proxies.map((item) => ({ value: item.id, label: item.name })),
  ];
  const fontSetOptions: SelectOption[] = [
    { value: "__none__", label: t("formFontSetNone") },
    ...sortedFontSets.map((fontSet) => ({
      value: fontSet.set_id,
      label: `${fontSet.set_id} · ${fontSet.source_version ?? ""}`,
    })),
  ];
  const localeOptions: SelectOption[] = [
    { value: "zh-CN", label: t("formLocaleChinese") },
    { value: "en-US", label: t("formLocaleEnglish") },
  ];
  const platformOptions: SelectOption[] = [
    { value: "windows", label: t("formPlatformWindows") },
    { value: "macos", label: t("formPlatformMacos") },
  ];
  const gpuOptions: SelectOption[] = [
    { value: "auto", label: t("formGpuAuto") },
    { value: "nvidia", label: t("formGpuNvidia") },
    { value: "intel", label: t("formGpuIntel") },
  ];
  const presetOptions: SelectOption[] = [
    { value: "default", label: t("formPresetDefault") },
    { value: "careful", label: t("formPresetCareful") },
  ];
  const colorSchemeOptions: SelectOption[] = [
    { value: "__none__", label: t("formFontSetNone") },
    { value: "light", label: t("formColorLight") },
    { value: "dark", label: t("formColorDark") },
    { value: "no-preference", label: t("formColorNoPreference") },
  ];

  const submitValues = async () => {
    if (submitDisabled) return;
    if (!values.name.trim()) {
      setShowErrors(true);
      return;
    }
    setShowErrors(false);
    setSubmitting(true);
    try {
      const start = intentRef.current === "create-start";
      intentRef.current = "create";
      // t058 A24: an edit submits only the fields that differ from the
      // initial values, so another client's concurrent edits are never
      // written back with stale values. Create still sends the full form.
      const payload: ProfileCreateRequest | ProfileUpdateRequest =
        mode === "edit"
          ? diffProfileValues(values, baselineRef.current)
          : start
            ? Object.assign({}, values, { __startAfterCreate: true })
            : values;
      await onSubmit(payload);
    } finally {
      setSubmitting(false);
    }
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void submitValues();
  };

  const nameInvalid = !values.name.trim();

  return (
    <form
      id="profile-form"
      data-testid="profile-form"
      onSubmit={handleSubmit}
      className="flex flex-col gap-md"
    >
      <Section title={t("formSectionBasic")}>
        <Row label={t("formName")}>
          <Input
            data-testid="profile-form-name"
            aria-label={t("formName")}
            value={values.name}
            onChange={(event) => setField("name", event.target.value)}
          />
          {showErrors && nameInvalid && (
            <p
              data-testid="profile-form-name-error"
              className="font-ui text-label-sm text-on-surface"
            >
              {t("formNameRequired")}
            </p>
          )}
        </Row>
        <Row label={t("formGroup")}>
          <div data-testid="profile-form-group">
            <Select
              value={values.group_id ?? "__none__"}
              onValueChange={(value) => {
                if (value === "__create_group__") {
                  setCreatingGroup(true);
                  return;
                }
                setField("group_id", value === "__none__" ? null : value);
              }}
              options={groupOptions}
              ariaLabel={t("formGroup")}
            />
          </div>
          {creatingGroup && (
            <div className="flex items-center gap-sm">
              <Input
                aria-label={t("formNewGroup")}
                value={newGroupName}
                onChange={(event) => {
                  setNewGroupName(event.target.value);
                  setGroupError(null);
                }}
              />
              <Button
                disabled={createGroupMutation.isPending}
                onClick={async () => {
                  const name = newGroupName.trim();
                  if (!name) {
                    setGroupError(t("formNameRequired"));
                    return;
                  }
                  setGroupError(null);
                  try {
                    const created = await createGroupMutation.mutateAsync({
                      name,
                      color: "slate",
                      sort_order: 0,
                    });
                    setField("group_id", created.id);
                    setCreatingGroup(false);
                    setNewGroupName("");
                  } catch (err: unknown) {
                    setGroupError(
                      err instanceof Error ? err.message : t("failedToCreateGroup"),
                    );
                  }
                }}
              >
                {t("groupSave")}
              </Button>
            </div>
          )}
          {groupError && (
            <Banner tone="danger" testId="profile-form-group-error">
              {groupError}
            </Banner>
          )}
        </Row>
        <Row label={t("formNotes")}>
          <Input
            data-testid="profile-form-notes"
            aria-label={t("formNotes")}
            value={values.notes ?? ""}
            onChange={(event) => setField("notes", event.target.value)}
          />
        </Row>
      </Section>

      <Section title={t("formSectionNetwork")}>
        <Row label={t("formProxy")}>
          <div data-testid="profile-form-proxy">
            <Select
              value={values.proxy_id ?? "__direct__"}
              onValueChange={(value) =>
                setField("proxy_id", value === "__direct__" ? null : value)
              }
              options={proxyOptions}
              ariaLabel={t("formProxy")}
            />
          </div>
        </Row>
        <BoolRow
          label={t("formGeoip")}
          checked={values.geoip}
          onChange={(checked) => setField("geoip", checked)}
        />
        <div className="flex gap-sm">
          <Row label={t("formTimezone")}>
            <TimezoneCombobox
              testId="profile-form-timezone"
              ariaLabel={t("formTimezone")}
              value={values.timezone ?? null}
              onValueChange={(timezone) => {
                setValues((prev) => {
                  const locale =
                    timezone == null
                      ? prev.locale
                      : localeForTimezone(timezone);
                  return {
                    ...prev,
                    timezone,
                    locale,
                  } as ProfileFormValues;
                });
              }}
            />
          </Row>
          <Row label={t("formLocale")}>
            <div data-testid="profile-form-locale">
              <Select
                value={values.locale ?? "en-US"}
                onValueChange={(value) =>
                  setField("locale", value === "zh-CN" ? "zh-CN" : "en-US")
                }
                options={localeOptions}
                ariaLabel={t("formLocale")}
              />
            </div>
          </Row>
        </div>
      </Section>

      <Section title={t("formSectionFingerprint")}>
        <div className="flex gap-sm">
          <Row label={t("formPlatform")}>
            <div data-testid="profile-form-platform">
              <Select
                value={platform}
                onValueChange={(value) => {
                  const nextPlatform = normalizePlatform(value);
                  fontSetUserChosenRef.current = false;
                  defaultFontSetAppliedRef.current = nextPlatform;
                  setValues(
                    (prev) =>
                      ({
                        ...prev,
                        fingerprint_platform: nextPlatform,
                        font_set_id: defaultFontSetId[nextPlatform] ?? null,
                      }) as ProfileFormValues,
                  );
                }}
                options={platformOptions}
                ariaLabel={t("formPlatform")}
              />
            </div>
          </Row>
          <Row label={t("formFontSet")}>
            <div data-testid="profile-form-fontset">
              <Select
                value={values.font_set_id ?? "__none__"}
                onValueChange={(value) => {
                  fontSetUserChosenRef.current = true;
                  setField("font_set_id", value === "__none__" ? null : value);
                }}
                // The "none" pick must count as an explicit choice even
                // when "none" is already showing (e.g. picked before
                // the backend default arrives): Radix does not call
                // onValueChange for a same-value pick, so record it here.
                onOptionSelect={() => {
                  fontSetUserChosenRef.current = true;
                }}
                options={fontSetOptions}
                ariaLabel={t("formFontSet")}
              />
            </div>
          </Row>
        </div>
        <div className="flex flex-col gap-xs rounded-md bg-surface-subtle p-sm">
          <span
            data-testid="profile-form-fontset-selected"
            className="font-mono text-mono-md text-on-surface"
          >
            {values.font_set_id ?? t("formFontSetNone")}
          </span>
          <div
            data-testid="profile-form-fontset-meta"
            className="font-ui text-label-sm text-on-surface-muted"
          >
            {selectedFontSet ? (
              <>
                <span>
                  {t("formFontSetSourceVersion", {
                    name: selectedFontSet.source_version ?? "",
                  })}
                </span>
                <span>
                  {t("formFontSetIntegrity")}:{" "}
                  {selectedFontSet.integrity.ok
                    ? t("fontSetIntegrityOk")
                    : t("fontSetIntegrityBad")}
                </span>
              </>
            ) : (
              <span>{t("formFontSetNone")}</span>
            )}
          </div>
          <ul
            data-testid="profile-form-fontset-list"
            className="flex flex-col gap-xs font-ui text-label-sm text-on-surface-muted"
          >
            {platformFontSets.map((fontSet) => (
              <li
                key={fontSet.set_id}
                data-testid={`profile-form-fontset-option-${fontSet.set_id}`}
              >
                {fontSet.set_id} —{" "}
                {t("formFontSetSourceVersion", {
                  name: fontSet.source_version ?? "",
                })}{" "}
                —{" "}
                {fontSet.integrity.ok
                  ? t("fontSetIntegrityOk")
                  : t("fontSetIntegrityBad")}
              </li>
            ))}
          </ul>
        </div>
        {(missingFontSet || inconsistent) && (
          <Banner tone="warning" testId="profile-form-fontset-warning">
            {missingFontSet
              ? t("formFontSetMissing")
              : t("formFontSetInconsistent")}
          </Banner>
        )}
        <Row label={t("formSeed")}>
          <div className="flex items-center gap-sm">
            <span
              data-testid="profile-form-seed"
              className="font-mono text-mono-md text-on-surface"
            >
              {values.fingerprint_seed ?? ""}
            </span>
            <Button
              data-testid="profile-form-reseed"
              onClick={() =>
                setField(
                  "fingerprint_seed",
                  Math.floor(Math.random() * 2147483647) + 1,
                )
              }
            >
              {t("formReseed")}
            </Button>
          </div>
        </Row>
        <div className="flex gap-sm">
          <Row label={t("formGpu")}>
            <Select
              value={values.gpu_family}
              onValueChange={(value) => setField("gpu_family", normalizeGpu(value))}
              options={gpuOptions}
              ariaLabel={t("formGpu")}
            />
          </Row>
          <Row label={t("formColorScheme")}>
            <Select
              value={values.color_scheme ?? "__none__"}
              onValueChange={(value) =>
                setField(
                  "color_scheme",
                  value === "__none__" ? null : normalizeColorScheme(value),
                )
              }
              options={colorSchemeOptions}
              ariaLabel={t("formColorScheme")}
            />
          </Row>
        </div>
        <Row label={t("formResolution")}>
          <div className="flex gap-sm">
            <Input
              type="number"
              aria-label={t("widthPx")}
              value={values.screen_width}
              onChange={(event) =>
                setField("screen_width", Number(event.target.value))
              }
            />
            <Input
              type="number"
              aria-label={t("heightPx")}
              value={values.screen_height}
              onChange={(event) =>
                setField("screen_height", Number(event.target.value))
              }
            />
          </div>
        </Row>
      </Section>

      <details
        data-testid="profile-form-advanced"
        className="rounded-md border border-outline bg-surface p-md"
      >
        <summary className="cursor-pointer font-ui text-headline-md text-on-surface">
          {t("formSectionAdvanced")}
        </summary>
        <div className="mt-md flex flex-col gap-md">
          <p className="font-ui text-label-sm text-on-surface-muted">
            {t("formAdvancedHint")}
          </p>
          <div className="grid grid-cols-2 gap-sm">
            {ADVANCED_BOOL_FIELDS.map(({ key, labelKey }) => (
              <BoolRow
                key={key}
                label={t(labelKey)}
                checked={values[key] as boolean}
                onChange={(checked) =>
                  setField(key, checked as ProfileFormValues[typeof key])
                }
              />
            ))}
          </div>
          <Row label={t("formHumanPreset")}>
            <Select
              value={values.human_preset}
              onValueChange={(value) =>
                setField("human_preset", normalizePreset(value))
              }
              options={presetOptions}
              ariaLabel={t("formHumanPreset")}
            />
          </Row>
          <Row label={t("formLaunchArgs")}>
            <Input
              aria-label={t("formLaunchArgs")}
              value={(values.launch_args ?? []).join(", ")}
              onChange={(event) =>
                setField(
                  "launch_args",
                  event.target.value
                    .split(",")
                    .map((item) => item.trim())
                    .filter(Boolean),
                )
              }
            />
          </Row>
          <Row label={t("formExtensionPaths")}>
            <Input
              aria-label={t("formExtensionPaths")}
              value={(values.extension_paths ?? []).join(", ")}
              onChange={(event) =>
                setField(
                  "extension_paths",
                  event.target.value
                    .split(",")
                    .map((item) => item.trim())
                    .filter(Boolean),
                )
              }
            />
          </Row>
        </div>
      </details>

      {showErrors && nameInvalid && (
        <div
          data-testid="profile-form-error"
          className="font-ui text-label-sm text-on-surface"
        >
          {t("formValidationError")}
        </div>
      )}

      {mode === "create" ? (
        <div className="flex justify-end gap-sm">
          <Button
            data-testid="profile-form-submit"
            variant="secondary"
            disabled={submitDisabled}
            onClick={() => {
              intentRef.current = "create";
              void submitValues();
            }}
          >
            {submitLabel ?? t("formCreate")}
          </Button>
          <Button
            data-testid="profile-form-submit-start"
            variant="primary"
            disabled={submitDisabled}
            onClick={() => {
              intentRef.current = "create-start";
              void submitValues();
            }}
          >
            {t("formCreateAndStart")}
          </Button>
        </div>
      ) : (
        <div className="flex justify-end">
          <Button
            data-testid="profile-form-submit"
            variant="primary"
            disabled={submitDisabled}
            onClick={() => {
              intentRef.current = "save";
              void submitValues();
            }}
          >
            {submitLabel ?? t("formSave")}
          </Button>
        </div>
      )}
    </form>
  );
}
