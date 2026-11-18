import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { AlertCircle, RefreshCw } from "lucide-react";
import {
  Banner,
  Button,
  Checkbox,
  FieldLabel,
  IconButton,
  Input,
  Select,
  Tooltip,
  type SelectOption,
} from "../../shared/ui";
import { useI18n, type TranslationKey } from "../../i18n";
import { useApiClient } from "../../shared/api/client_context";
import { DEFAULT_PROFILE_CREATE_VALUES } from "../../shared/api/types";
import type {
  GroupResponse,
  ProfileCreateRequest,
  ProfileResponse,
  ProfileUpdateRequest,
  ProxyResponse,
} from "../../shared/api/types";
import {
  useCreateGroupMutation,
  useGroupsQuery,
  useProxiesQuery,
} from "./useProfilesQuery";
import {
  defaultIncludeCjkForLocale,
  localeForTimezone,
  timezoneForLocale,
  timezoneForProxy,
} from "./profile_locale";
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

function normalizePlatform(value: string | undefined): "windows" | "macos" {
  return value === "macos" ? "macos" : "windows";
}

function normalizePreset(value: string): "default" | "careful" {
  return value === "careful" ? "careful" : "default";
}

function normalizeColorScheme(
  value: string | null | undefined,
): "light" | "dark" {
  return value === "dark" ? "dark" : "light";
}

function randomValidSeed(): number {
  return Math.floor(100000 + Math.random() * 900000);
}

function toFormValues(initial?: ProfileResponse): ProfileFormValues {
  if (!initial) {
    return {
      name: "",
      ...DEFAULT_PROFILE_CREATE_VALUES,
      fingerprint_seed:
        DEFAULT_PROFILE_CREATE_VALUES.fingerprint_seed ?? randomValidSeed(),
    };
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
    humanize: initial.humanize,
    human_preset: normalizePreset(initial.human_preset),
    geoip: initial.geoip,
    clipboard_sync: initial.clipboard_sync,
    auto_launch: initial.auto_launch,
    color_scheme: normalizeColorScheme(initial.color_scheme),
    include_cjk_fonts: initial.include_cjk_fonts,
    fingerprint_platform: normalizePlatform(initial.fingerprint_platform),
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

function Row({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-1 flex-col gap-xs">
      <div className="flex items-center gap-xs">
        <FieldLabel>{label}</FieldLabel>
        {hint}
      </div>
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
      <div className="grid grid-cols-1 gap-md md:grid-cols-2 lg:grid-cols-3">
        {children}
      </div>
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
  const createGroupMutation = useCreateGroupMutation(client);

  const groups = groupsData ?? EMPTY_GROUPS;
  const proxies = proxiesData ?? EMPTY_PROXIES;

  const [values, setValues] = useState<ProfileFormValues>(() =>
    toFormValues(initial),
  );
  const baselineRef = useRef<ProfileFormValues>(toFormValues(initial));
  const intentRef = useRef<"create" | "create-start" | "save">("create");
  const [showErrors, setShowErrors] = useState(false);
  const [creatingGroup, setCreatingGroup] = useState(false);
  const [newGroupName, setNewGroupName] = useState("");
  const [groupError, setGroupError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const submitDisabled = submitting || isPending;

  const setField = <K extends keyof ProfileFormValues>(
    key: K,
    value: ProfileFormValues[K],
  ) => {
    setValues((prev) => ({ ...prev, [key]: value }) as ProfileFormValues);
  };

  const platform = normalizePlatform(values.fingerprint_platform);

  const timezoneManualRef = useRef(false);
  const localeManualRef = useRef(false);
  const cjkUserChosenRef = useRef(false);
  const [manualOverrides, setManualOverrides] = useState({
    timezone: false,
    locale: false,
  });

  // t075: until the user touches the switch, the CJK inclusion default
  // follows the language (Chinese on, English off), mirroring the
  // backend derivation for requests that omit the field.
  useEffect(() => {
    if (mode !== "create" || cjkUserChosenRef.current) return;
    setValues((prev) => {
      const aligned = defaultIncludeCjkForLocale(prev.locale);
      return prev.include_cjk_fonts === aligned
        ? prev
        : ({ ...prev, include_cjk_fonts: aligned } as ProfileFormValues);
    });
  }, [mode, values.locale]);

  const selectedProxy = proxies.find((item) => item.id === values.proxy_id);

  const groupOptions: SelectOption[] = [
    { value: "__none__", label: t("envUngrouped") },
    ...groups.map((item) => ({ value: item.id, label: item.name })),
    { value: "__create_group__", label: t("formNewGroup") },
  ];
  const proxyOptions: SelectOption[] = [
    { value: "__direct__", label: t("formDirect") },
    ...proxies.map((item) => ({ value: item.id, label: item.name })),
  ];
  const localeOptions: SelectOption[] = [
    { value: "zh-CN", label: t("formLocaleChinese") },
    { value: "en-US", label: t("formLocaleEnglish") },
  ];
  const platformOptions: SelectOption[] = [
    { value: "windows", label: t("formPlatformWindows") },
    { value: "macos", label: t("formPlatformMacos") },
  ];
  const presetOptions: SelectOption[] = [
    { value: "default", label: t("formPresetDefault") },
    { value: "careful", label: t("formPresetCareful") },
  ];
  const colorSchemeOptions: SelectOption[] = [
    { value: "light", label: t("formColorLight") },
    { value: "dark", label: t("formColorDark") },
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
              onValueChange={(value) => {
                const nextProxyId = value === "__direct__" ? null : value;
                const matchedProxy = proxies.find((item) => item.id === nextProxyId);
                const inferredTz = timezoneForProxy(matchedProxy);
                if (inferredTz != null) {
                  timezoneManualRef.current = false;
                  localeManualRef.current = false;
                  cjkUserChosenRef.current = false;
                  setManualOverrides({
                    timezone: false,
                    locale: false,
                  });
                }
                setValues((prev) => {
                  const nextTz =
                    inferredTz ??
                    (timezoneManualRef.current ? prev.timezone : null);
                  const nextLocale =
                    inferredTz != null
                      ? localeForTimezone(inferredTz)
                      : prev.locale;
                  return {
                    ...prev,
                    proxy_id: nextProxyId,
                    timezone: nextTz,
                    locale: nextLocale,
                    include_cjk_fonts: cjkUserChosenRef.current
                      ? prev.include_cjk_fonts
                      : defaultIncludeCjkForLocale(nextLocale),
                  } as ProfileFormValues;
                });
              }}
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
                timezoneManualRef.current = true;
                setManualOverrides((prev) => ({ ...prev, timezone: true }));
                setValues((prev) => {
                  const nextLocale =
                    !localeManualRef.current && timezone != null
                      ? localeForTimezone(timezone)
                      : prev.locale;
                  return {
                    ...prev,
                    timezone,
                    locale: nextLocale,
                    include_cjk_fonts: cjkUserChosenRef.current
                      ? prev.include_cjk_fonts
                      : defaultIncludeCjkForLocale(nextLocale),
                  } as ProfileFormValues;
                });
              }}
            />
          </Row>
          <Row label={t("formLocale")}>
            <div data-testid="profile-form-locale">
              <Select
                value={values.locale ?? "en-US"}
                onValueChange={(value) => {
                  const nextLocale = value === "zh-CN" ? "zh-CN" : "en-US";
                  localeManualRef.current = true;
                  setManualOverrides((prev) => ({ ...prev, locale: true }));
                  setValues((prev) => {
                    const nextTimezone = timezoneManualRef.current
                      ? prev.timezone
                      : timezoneForLocale(nextLocale, prev.timezone);
                    return {
                      ...prev,
                      locale: nextLocale,
                      timezone: nextTimezone,
                      include_cjk_fonts: cjkUserChosenRef.current
                        ? prev.include_cjk_fonts
                        : defaultIncludeCjkForLocale(nextLocale),
                    } as ProfileFormValues;
                  });
                }}
                options={localeOptions}
                ariaLabel={t("formLocale")}
              />
            </div>
          </Row>
        </div>
        {(() => {
          const proxyInferredTz = timezoneForProxy(selectedProxy);
          const proxyRegion =
            selectedProxy?.country_code ||
            selectedProxy?.region_label ||
            selectedProxy?.name ||
            "";
          const activeLocale = values.locale === "zh-CN" ? "zh-CN" : "en-US";
          const localeText =
            activeLocale === "zh-CN"
              ? t("formLocaleChinese")
              : t("formLocaleEnglish");
          const fontRule =
            activeLocale === "zh-CN"
              ? t("formAlignFontsZh")
              : t("formAlignFontsEn");
          const tzText = values.timezone ?? t("formTimezoneAuto");
          const hasOverrides =
            manualOverrides.timezone || manualOverrides.locale;
          if (!proxyInferredTz && !values.timezone && !hasOverrides) {
            return null;
          }
          return (
            <div
              data-testid="profile-form-alignment-summary"
              className="flex flex-wrap items-center justify-between gap-sm rounded-md border border-outline bg-surface-subtle px-sm py-xs font-ui text-label-sm text-on-surface-muted"
            >
              <span>
                {proxyInferredTz
                  ? t("formAlignProxySummary", {
                      region: proxyRegion,
                      timezone: tzText,
                      locale: localeText,
                      fontRule,
                    })
                  : t("formAlignLocaleSummary", {
                      timezone: tzText,
                      locale: localeText,
                      fontRule,
                    })}
              </span>
              {hasOverrides && (
                <span className="flex items-center gap-sm">
                  <span>{t("formAlignManualNote")}</span>
                  <button
                    type="button"
                    data-testid="profile-form-reset-alignment"
                    onClick={() => {
                      timezoneManualRef.current = false;
                      localeManualRef.current = false;
                      cjkUserChosenRef.current = false;
                      setManualOverrides({
                        timezone: false,
                        locale: false,
                      });
                      setValues((prev) => {
                        const resetTz = proxyInferredTz ?? null;
                        const resetLocale =
                          proxyInferredTz != null
                            ? localeForTimezone(proxyInferredTz)
                            : (DEFAULT_PROFILE_CREATE_VALUES.locale ?? "en-US");
                        return {
                          ...prev,
                          timezone: resetTz,
                          locale: resetLocale,
                          include_cjk_fonts:
                            defaultIncludeCjkForLocale(resetLocale),
                        } as ProfileFormValues;
                      });
                    }}
                    className="cursor-pointer font-ui text-label-sm text-primary hover:underline focus-visible:outline-2 focus-visible:outline-focus"
                  >
                    {t("formAlignReset")}
                  </button>
                </span>
              )}
            </div>
          );
        })()}
      </Section>

      <Section title={t("formSectionFingerprint")}>
        <Row label={t("formPlatform")}>
          <div data-testid="profile-form-platform">
            <Select
              value={platform}
              onValueChange={(value) => {
                const nextPlatform = normalizePlatform(value);
                setValues((prev) => {
                  const isDefaultResolution =
                    (prev.screen_width === 1920 && prev.screen_height === 1080) ||
                    (prev.screen_width === 1440 && prev.screen_height === 900);
                  return {
                    ...prev,
                    fingerprint_platform: nextPlatform,
                    screen_width: isDefaultResolution
                      ? nextPlatform === "macos"
                        ? 1440
                        : 1920
                      : prev.screen_width,
                    screen_height: isDefaultResolution
                      ? nextPlatform === "macos"
                        ? 900
                        : 1080
                      : prev.screen_height,
                  } as ProfileFormValues;
                });
              }}
              options={platformOptions}
              ariaLabel={t("formPlatform")}
            />
          </div>
        </Row>
        <Row
          label={t("formSeed")}
          hint={
            <Tooltip content={t("formSeedRangeHint")}>
              <span
                data-testid="profile-form-seed-hint"
                aria-label={t("formSeedRangeHint")}
                className="inline-flex cursor-help items-center text-on-surface-muted hover:text-on-surface"
              >
                <AlertCircle
                  aria-hidden="true"
                  className="size-(--component-icon-sm-size)"
                />
              </span>
            </Tooltip>
          }
        >
          <div className="flex items-center gap-sm">
            <Input
              type="number"
              min={100000}
              max={999999}
              aria-label={t("formSeed")}
              value={values.fingerprint_seed ?? ""}
              onChange={(event) => {
                const parsed = Number(event.target.value);
                if (Number.isFinite(parsed)) {
                  setField("fingerprint_seed", parsed);
                }
              }}
              className="no-spin font-mono"
            />
            <span data-testid="profile-form-seed" className="sr-only">
              {values.fingerprint_seed ?? ""}
            </span>
            <IconButton
              data-testid="profile-form-reseed"
              label={t("formReseed")}
              onClick={() => setField("fingerprint_seed", randomValidSeed())}
            >
              <RefreshCw
                aria-hidden="true"
                className="size-(--component-icon-md-size)"
              />
            </IconButton>
          </div>
        </Row>
        <div className="flex gap-sm">
          <Row label={t("formColorScheme")}>
            <Select
              value={values.color_scheme ?? "light"}
              onValueChange={(value) =>
                setField("color_scheme", normalizeColorScheme(value))
              }
              options={colorSchemeOptions}
              ariaLabel={t("formColorScheme")}
            />
          </Row>
          <div data-testid="profile-form-include-cjk">
            <BoolRow
              label={t("formIncludeCjk")}
              checked={values.include_cjk_fonts ?? false}
              onChange={(checked) => {
                cjkUserChosenRef.current = true;
                setField("include_cjk_fonts", checked);
              }}
            />
          </div>
        </div>
        <Row label={t("formResolution")}>
          <div className="flex items-center gap-sm">
            <Input
              type="number"
              aria-label={t("widthPx")}
              value={values.screen_width}
              onChange={(event) =>
                setField("screen_width", Number(event.target.value))
              }
              className="no-spin font-mono"
            />
            <span className="font-mono text-mono-md text-on-surface-muted">×</span>
            <Input
              type="number"
              aria-label={t("heightPx")}
              value={values.screen_height}
              onChange={(event) =>
                setField("screen_height", Number(event.target.value))
              }
              className="no-spin font-mono"
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
