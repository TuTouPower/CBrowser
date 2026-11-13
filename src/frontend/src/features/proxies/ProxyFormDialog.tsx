import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";
import type { JSX } from "react";
import {
  Banner,
  Button,
  Dialog,
  FieldLabel,
  Input,
  RegionCode,
  Select,
  useToast,
  type SelectOption,
} from "../../shared/ui";
import { useI18n, type TranslationKey } from "../../i18n";
import { ApiError } from "../../shared/api/client";
import { useApiClient } from "../../shared/api/client_context";
import type {
  ProxyCreateRequest,
  ProxyResponse,
  ProxyUpdateRequest,
} from "../../shared/api/types";
import {
  useCreateProxyMutation,
  useUpdateProxyMutation,
} from "../profiles/useProfilesQuery";
import {
  buildProxyUrl,
  parseProxyUrl,
  proxyDisplayName,
  redactedProxyUrl,
  type ParsedProxyFields,
  type ProxyScheme,
} from "./parseProxyUrl";

export interface ProxyFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  proxy: ProxyResponse | null;
}

interface EndpointFields {
  scheme: ProxyScheme;
  host: string;
  port: string;
  username: string;
  password: string;
}

interface FormState {
  name: string;
  endpoint: EndpointFields;
  region_label: string;
  notes: string;
}

type FieldKey =
  | "name"
  | "host"
  | "port"
  | "url"
  | "username"
  | "password"
  | "region-label";

const SCHEMES: ProxyScheme[] = ["http", "https", "socks5"];

const SCHEME_OPTIONS: SelectOption[] = SCHEMES.map((scheme) => ({
  value: scheme,
  label: scheme.toUpperCase(),
}));

const EMPTY_FORM: FormState = {
  name: "",
  endpoint: { scheme: "http", host: "", port: "", username: "", password: "" },
  region_label: "",
  notes: "",
};

function fieldsFromParsed(parsed: ParsedProxyFields): EndpointFields {
  return {
    scheme: parsed.scheme,
    host: parsed.host,
    port: String(parsed.port),
    username: parsed.username ?? "",
    password: parsed.password ?? "",
  };
}

/** Validate the advanced endpoint fields; null when they form an endpoint. */
function parseEndpointFields(endpoint: EndpointFields): ParsedProxyFields | null {
  const portText = endpoint.port.trim();
  if (!/^\d+$/.test(portText)) return null;
  const port = Number(portText);
  if (!Number.isInteger(port) || port < 1 || port > 65535) return null;
  if (endpoint.host.trim().length === 0) return null;
  if (!SCHEMES.includes(endpoint.scheme)) return null;
  const candidate: ParsedProxyFields = {
    scheme: endpoint.scheme,
    host: endpoint.host.trim(),
    port,
    username: endpoint.username.trim() === "" ? null : endpoint.username.trim(),
    password: endpoint.password === "" ? null : endpoint.password,
  };
  // Normalise through the shared parser (lowercase host, IPv6 compression).
  const result = parseProxyUrl(buildProxyUrl(candidate));
  return result.ok ? result.fields : null;
}

function initialState(proxy: ProxyResponse | null): {
  form: FormState;
  linkText: string;
  parsed: ParsedProxyFields | null;
  nameTouched: boolean;
} {
  if (!proxy) {
    return { form: { ...EMPTY_FORM }, linkText: "", parsed: null, nameTouched: false };
  }
  const parsed = parseProxyUrl(proxy.proxy_url);
  const fields = parsed.ok ? parsed.fields : null;
  const form: FormState = {
    name: proxy.name,
    endpoint: fields
      ? fieldsFromParsed(fields)
      : { ...EMPTY_FORM.endpoint },
    region_label: proxy.region_label ?? "",
    notes: proxy.notes ?? "",
  };
  return {
    form,
    linkText: proxy.proxy_url,
    parsed: fields,
    nameTouched: fields ? proxy.name !== proxyDisplayName(fields) : true,
  };
}

function validate(
  form: FormState,
  parsed: ParsedProxyFields | null,
  linkError: boolean,
  endpointTouched: boolean,
  clearPassword: boolean,
  proxy: ProxyResponse | null,
): Partial<Record<FieldKey, TranslationKey>> {
  const errors: Partial<Record<FieldKey, TranslationKey>> = {};
  const name = form.name.trim();
  if (name.length > 255) errors.name = "proxyValidationError";
  if (linkError) errors.url = "proxyUrlInvalid";
  if (parsed === null) {
    if (!linkError) errors.url = "proxyUrlInvalid";
  }
  if (form.endpoint.host.trim().length < 1) errors.host = "proxyHostRequired";
  if (form.endpoint.host.trim().length > 512) errors.host = "proxyValidationError";
  const port = form.endpoint.port.trim();
  const portNumber = Number(port);
  if (
    !/^\d+$/.test(port) ||
    !Number.isInteger(portNumber) ||
    portNumber < 1 ||
    portNumber > 65535
  ) {
    errors.port = "proxyPortInvalid";
  }
  if (form.endpoint.username.trim().length > 255) {
    errors.username = "proxyValidationError";
  }
  if (form.region_label.trim().length > 255) {
    errors["region-label"] = "proxyValidationError";
  }
  // Editing the endpoint of a password-protected proxy without re-entering
  // the password would silently clear it (proxy_url replaces the endpoint
  // wholesale): block until the password is re-entered or explicitly cleared.
  if (
    proxy !== null &&
    proxy.has_password &&
    endpointTouched &&
    !clearPassword &&
    form.endpoint.password === ""
  ) {
    errors.password = "proxyPasswordRequiredOnEndpointChange";
  }
  return errors;
}

function nullable(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}

function readableDetail(value: unknown): string | null {
  if (typeof value === "string" && value.length > 0) return value;
  if (Array.isArray(value)) {
    // t056 A15: a 422 carries its field errors as a `details` list.
    const messages = value
      .map((item) => {
        if (item && typeof item === "object") {
          const record = item as Record<string, unknown>;
          const msg = record.msg;
          if (typeof msg === "string" && msg.length > 0) return msg;
        }
        return null;
      })
      .filter((msg): msg is string => msg !== null);
    return messages.length > 0 ? messages.join("; ") : null;
  }
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    for (const key of ["message", "details", "error", "reason"]) {
      const candidate = record[key];
      if (typeof candidate === "string" && candidate.length > 0) return candidate;
    }
    try {
      return JSON.stringify(value);
    } catch {
      return null;
    }
  }
  return null;
}

function describeError(err: unknown): string {
  if (!(err instanceof ApiError)) {
    return err instanceof Error ? err.message : String(err);
  }
  const detail =
    readableDetail(err.details) ?? readableDetail(err.data) ?? err.message;
  return err.errorCode ? `${detail} (${err.errorCode})` : detail;
}

function FieldRow({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-xs">
      <FieldLabel>{label}</FieldLabel>
      {children}
    </div>
  );
}

export function ProxyFormDialog(props: ProxyFormDialogProps): JSX.Element {
  const { open, onOpenChange, proxy } = props;
  const { t } = useI18n();
  const client = useApiClient();
  const toast = useToast();
  const createMutation = useCreateProxyMutation(client);
  const updateMutation = useUpdateProxyMutation(client);

  const isEdit = proxy !== null;

  const [form, setForm] = useState<FormState>(() => initialState(proxy).form);
  const [linkText, setLinkText] = useState<string>(() => initialState(proxy).linkText);
  const [linkFocused, setLinkFocused] = useState(false);
  const [parsed, setParsed] = useState<ParsedProxyFields | null>(
    () => initialState(proxy).parsed,
  );
  const [linkError, setLinkError] = useState(false);
  const [nameTouched, setNameTouched] = useState<boolean>(
    () => initialState(proxy).nameTouched,
  );
  const [endpointTouched, setEndpointTouched] = useState(false);
  const [clearPassword, setClearPassword] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [showErrors, setShowErrors] = useState(false);
  const [banner, setBanner] = useState<string | null>(null);

  const clearLocalState = useCallback(() => {
    const initial = initialState(null);
    setForm(initial.form);
    setLinkText(initial.linkText);
    setLinkFocused(false);
    setParsed(initial.parsed);
    setLinkError(false);
    setNameTouched(initial.nameTouched);
    setEndpointTouched(false);
    setClearPassword(false);
    setAdvancedOpen(false);
    setShowErrors(false);
    setBanner(null);
  }, []);

  useEffect(() => {
    const initial = initialState(open ? proxy : null);
    setForm(initial.form);
    setLinkText(initial.linkText);
    setLinkFocused(false);
    setParsed(initial.parsed);
    setLinkError(false);
    setNameTouched(initial.nameTouched);
    setEndpointTouched(false);
    setClearPassword(false);
    setAdvancedOpen(false);
    setShowErrors(false);
    setBanner(null);
  }, [open, proxy]);

  /** Re-derive the parsed endpoint + link display from advanced fields. */
  const syncFromEndpoint = (
    nextEndpoint: EndpointFields,
    nextForm: FormState,
    touched: boolean,
  ) => {
    const nextParsed = parseEndpointFields(nextEndpoint);
    setForm(nextForm);
    setParsed(nextParsed);
    if (nextParsed !== null) {
      setLinkText(
        linkFocused ? buildProxyUrl(nextParsed) : redactedProxyUrl(nextParsed),
      );
      setLinkError(false);
    }
    if (touched) setEndpointTouched(true);
  };

  const setEndpointField = <K extends keyof EndpointFields>(
    key: K,
    value: EndpointFields[K],
  ) => {
    const nextEndpoint = { ...form.endpoint, [key]: value };
    const nextForm = { ...form, endpoint: nextEndpoint };
    if (key === "password") setClearPassword(false);
    syncFromEndpoint(nextEndpoint, nextForm, true);
  };

  const setMetaField = <K extends "name" | "region_label" | "notes">(
    key: K,
    value: string,
  ) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    if (key === "name") setNameTouched(true);
  };

  const onLinkChange = (value: string) => {
    setLinkText(value);
    const result = parseProxyUrl(value);
    if (!result.ok) {
      // Invalid input shows a field-level error and keeps the last
      // successfully parsed endpoint (and its advanced fields) intact.
      setLinkError(true);
      return;
    }
    setLinkError(false);
    const nextParsed = result.fields;
    setParsed(nextParsed);
    const nextForm: FormState = {
      ...form,
      endpoint: fieldsFromParsed(nextParsed),
    };
    if (!nameTouched) {
      nextForm.name = proxyDisplayName(nextParsed);
    }
    setForm(nextForm);
    setEndpointTouched(true);
  };

  const onLinkFocus = () => {
    setLinkFocused(true);
    // Editing shows the full link (with password) so a later parse keeps it;
    // blurring switches back to the redacted display.
    if (parsed !== null) setLinkText(buildProxyUrl(parsed));
  };

  const onLinkBlur = () => {
    setLinkFocused(false);
    if (parsed !== null) setLinkText(redactedProxyUrl(parsed));
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const errors = validate(
      form,
      parsed,
      linkError,
      endpointTouched,
      clearPassword,
      proxy,
    );
    if (Object.keys(errors).length > 0 || parsed === null) {
      setShowErrors(true);
      setBanner(null);
      return;
    }
    setShowErrors(false);
    setBanner(null);

    const proxyUrl = buildProxyUrl(parsed);
    const name = form.name.trim() === "" ? proxyDisplayName(parsed) : form.name.trim();
    try {
      if (proxy) {
        const data: ProxyUpdateRequest = {
          name,
          region_label: nullable(form.region_label),
          notes: nullable(form.notes),
        };
        if (endpointTouched) data.proxy_url = proxyUrl;
        await updateMutation.mutateAsync({ proxyId: proxy.id, data });
      } else {
        const data: ProxyCreateRequest = {
          proxy_url: proxyUrl,
          name,
          region_label: nullable(form.region_label),
          notes: nullable(form.notes),
        };
        await createMutation.mutateAsync(data);
      }
      clearLocalState();
      onOpenChange(false);
      toast.show(t(proxy ? "proxyUpdateSuccess" : "proxyCreateSuccess"));
    } catch (err) {
      setBanner(describeError(err));
    }
  };

  const errors = validate(
    form,
    parsed,
    linkError,
    endpointTouched,
    clearPassword,
    proxy,
  );
  const visibleErrors = showErrors ? errors : {};
  // The link error is shown immediately on invalid input (not only after
  // submit), mirroring the old paste-box behaviour.
  const urlErrorKey = linkError ? "proxyUrlInvalid" : visibleErrors.url;

  const fieldError = (key: FieldKey) => {
    const messageKey = key === "url" ? urlErrorKey : visibleErrors[key];
    if (!messageKey) return null;
    return (
      <p
        data-testid={`proxy-form-${key}-error`}
        className="font-ui text-label-sm text-danger"
      >
        {t(messageKey)}
      </p>
    );
  };

  const countryStatus =
    proxy?.observation_status === "pending" ? (
      <span className="font-ui text-body-sm text-on-surface">
        {t("proxyCountryProbing")}
      </span>
    ) : proxy?.country_code ? (
      <span className="flex flex-wrap items-center gap-sm">
        <RegionCode code={proxy.country_code} />
        {proxy.egress_ip && (
          <span className="font-ui text-body-sm text-on-surface">
            {proxy.egress_ip}
          </span>
        )}
      </span>
    ) : (
      <span className="font-ui text-body-sm text-on-surface">
        {t("proxyCountryUnknown")}
      </span>
    );

  return (
    <Dialog
      trigger={<span />}
      title={isEdit ? t("proxyEdit") : t("proxyAdd")}
      open={open}
      onOpenChange={(next) => {
        if (!next) clearLocalState();
        onOpenChange(next);
      }}
      contentClassName="max-h-dialog-height overflow-y-auto"
    >
      <div data-testid="proxy-form-dialog" className="flex flex-col gap-md">
        <form onSubmit={handleSubmit} className="flex flex-col gap-md" noValidate>
          <FieldRow label={t("proxyFormUrl")}>
            <Input
              data-testid="proxy-form-url"
              aria-label={t("proxyFormUrl")}
              placeholder="socks5://user:pass@host:1080"
              value={linkText}
              onChange={(event) => onLinkChange(event.target.value)}
              onFocus={onLinkFocus}
              onBlur={onLinkBlur}
            />
            {fieldError("url")}
          </FieldRow>

          <FieldRow label={t("proxyCountryStatus")}>
            <div data-testid="proxy-form-country-status">{countryStatus}</div>
          </FieldRow>

          <FieldRow label={t("proxyFormNotes")}>
            <Input
              data-testid="proxy-form-notes"
              aria-label={t("proxyFormNotes")}
              value={form.notes}
              onChange={(event) => setMetaField("notes", event.target.value)}
            />
          </FieldRow>

          <div className="flex flex-col gap-md">
            <Button
              data-testid="proxy-form-advanced-toggle"
              size="sm"
              variant="secondary"
              aria-expanded={advancedOpen}
              onClick={() => setAdvancedOpen((prev) => !prev)}
            >
              {t("proxyAdvancedSettings")}
            </Button>
            {advancedOpen && (
              <div
                data-testid="proxy-form-advanced"
                className="flex flex-col gap-md"
              >
                <FieldRow label={t("proxyFormName")}>
                  <Input
                    data-testid="proxy-form-name"
                    aria-label={t("proxyFormName")}
                    value={form.name}
                    onChange={(event) =>
                      setMetaField("name", event.target.value)
                    }
                  />
                  {fieldError("name")}
                </FieldRow>

                <FieldRow label={t("proxyFormScheme")}>
                  <div data-testid="proxy-form-scheme">
                    <Select
                      value={form.endpoint.scheme}
                      onValueChange={(value) =>
                        setEndpointField("scheme", value as ProxyScheme)
                      }
                      options={SCHEME_OPTIONS}
                      ariaLabel={t("proxyFormScheme")}
                    />
                  </div>
                </FieldRow>

                <FieldRow label={t("proxyFormHost")}>
                  <Input
                    data-testid="proxy-form-host"
                    aria-label={t("proxyFormHost")}
                    value={form.endpoint.host}
                    onChange={(event) =>
                      setEndpointField("host", event.target.value)
                    }
                  />
                  {fieldError("host")}
                </FieldRow>

                <FieldRow label={t("proxyFormPort")}>
                  <Input
                    data-testid="proxy-form-port"
                    aria-label={t("proxyFormPort")}
                    value={form.endpoint.port}
                    onChange={(event) =>
                      setEndpointField("port", event.target.value)
                    }
                  />
                  {fieldError("port")}
                </FieldRow>

                <FieldRow label={t("proxyFormUsername")}>
                  <Input
                    data-testid="proxy-form-username"
                    aria-label={t("proxyFormUsername")}
                    value={form.endpoint.username}
                    onChange={(event) =>
                      setEndpointField("username", event.target.value)
                    }
                  />
                  {fieldError("username")}
                </FieldRow>

                <FieldRow label={t("proxyFormPassword")}>
                  <Input
                    data-testid="proxy-form-password"
                    aria-label={t("proxyFormPassword")}
                    type="password"
                    value={form.endpoint.password}
                    placeholder={
                      isEdit && proxy?.has_password
                        ? t("proxyPasswordSet")
                        : undefined
                    }
                    onChange={(event) =>
                      setEndpointField("password", event.target.value)
                    }
                  />
                  {fieldError("password")}
                  {isEdit && proxy?.has_password && (
                    <Button
                      data-testid="proxy-form-clear-password"
                      size="sm"
                      variant={clearPassword ? "danger" : "secondary"}
                      aria-pressed={clearPassword}
                      onClick={() => {
                        setClearPassword(true);
                        const nextEndpoint = { ...form.endpoint, password: "" };
                        syncFromEndpoint(
                          nextEndpoint,
                          { ...form, endpoint: nextEndpoint },
                          true,
                        );
                      }}
                    >
                      {t("proxyClearPassword")}
                    </Button>
                  )}
                </FieldRow>

                <FieldRow label={t("proxyFormRegionLabel")}>
                  <Input
                    data-testid="proxy-form-region-label"
                    aria-label={t("proxyFormRegionLabel")}
                    value={form.region_label}
                    onChange={(event) =>
                      setMetaField("region_label", event.target.value)
                    }
                  />
                  {fieldError("region-label")}
                </FieldRow>
              </div>
            )}
          </div>

          {banner && (
            <Banner tone="danger" testId="proxy-form-banner">
              {banner}
            </Banner>
          )}

          {showErrors && Object.keys(errors).length > 0 && (
            <div
              data-testid="proxy-form-error"
              className="font-ui text-label-sm text-danger"
            >
              {t("proxyFormError")}
            </div>
          )}

          <div className="flex justify-end gap-sm">
            <Button
              data-testid="proxy-form-cancel"
              onClick={() => {
                clearLocalState();
                onOpenChange(false);
              }}
            >
              {t("proxyCancel")}
            </Button>
            <Button
              data-testid="proxy-form-submit"
              variant="primary"
              type="submit"
              disabled={createMutation.isPending || updateMutation.isPending}
            >
              {isEdit ? t("proxySave") : t("proxyCreate")}
            </Button>
          </div>
        </form>
      </div>
    </Dialog>
  );
}
