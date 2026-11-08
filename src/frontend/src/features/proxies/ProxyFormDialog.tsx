import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";
import type { JSX } from "react";
import {
  Banner,
  Button,
  Dialog,
  FieldLabel,
  Input,
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
import { parseProxyUrl } from "./parseProxyUrl";

export interface ProxyFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  proxy: ProxyResponse | null;
}

type Scheme = ProxyCreateRequest["scheme"];

interface FormFields {
  name: string;
  scheme: Scheme;
  host: string;
  port: string;
  username: string;
  password: string;
  country_code: string;
  region_label: string;
  notes: string;
}

type FieldKey =
  | "name"
  | "host"
  | "port"
  | "country-code"
  | "scheme"
  | "username"
  | "region-label";

const SCHEMES: Scheme[] = ["http", "https", "socks5"];

const SCHEME_OPTIONS: SelectOption[] = SCHEMES.map((scheme) => ({
  value: scheme,
  label: scheme.toUpperCase(),
}));

const EMPTY_FIELDS: FormFields = {
  name: "",
  scheme: "http",
  host: "",
  port: "",
  username: "",
  password: "",
  country_code: "",
  region_label: "",
  notes: "",
};

function toFields(proxy: ProxyResponse | null): FormFields {
  if (!proxy) return { ...EMPTY_FIELDS };
  return {
    name: proxy.name,
    scheme: proxy.scheme,
    host: proxy.host,
    port: String(proxy.port),
    username: proxy.username ?? "",
    password: "",
    country_code: proxy.country_code ?? "",
    region_label: proxy.region_label ?? "",
    notes: proxy.notes ?? "",
  };
}

function validate(fields: FormFields): Partial<Record<FieldKey, TranslationKey>> {
  const errors: Partial<Record<FieldKey, TranslationKey>> = {};
  const name = fields.name.trim();
  if (name.length < 1 || name.length > 255) errors.name = "proxyNameRequired";
  const host = fields.host.trim();
  if (host.length < 1 || host.length > 512) errors.host = "proxyHostRequired";
  const port = fields.port.trim();
  const portNumber = Number(port);
  if (
    !/^\d+$/.test(port) ||
    !Number.isInteger(portNumber) ||
    portNumber < 1 ||
    portNumber > 65535
  ) {
    errors.port = "proxyPortInvalid";
  }
  const country = fields.country_code.trim();
  if (country !== "" && !/^[A-Za-z]{2}$/.test(country)) {
    errors["country-code"] = "proxyCountryCodeInvalid";
  }
  if (fields.username.trim().length > 255) {
    errors.username = "proxyValidationError";
  }
  if (fields.region_label.trim().length > 255) {
    errors["region-label"] = "proxyValidationError";
  }
  if (!SCHEMES.includes(fields.scheme)) errors.scheme = "proxyValidationError";
  return errors;
}

function nullable(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}

function nullableUpper(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed.toUpperCase();
}

function readableDetail(value: unknown): string | null {
  if (typeof value === "string" && value.length > 0) return value;
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    for (const key of ["message", "detail", "error", "reason"]) {
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
    readableDetail(err.detail) ?? readableDetail(err.data) ?? err.message;
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

  const [fields, setFields] = useState<FormFields>(() => toFields(proxy));
  const [clearPassword, setClearPassword] = useState(false);
  const [pasteUrl, setPasteUrl] = useState("");
  const [pasteError, setPasteError] = useState(false);
  const [showErrors, setShowErrors] = useState(false);
  const [banner, setBanner] = useState<string | null>(null);

  const clearLocalState = useCallback(() => {
    setFields({ ...EMPTY_FIELDS });
    setClearPassword(false);
    setPasteUrl("");
    setPasteError(false);
    setShowErrors(false);
    setBanner(null);
  }, []);

  useEffect(() => {
    setFields(open ? toFields(proxy) : { ...EMPTY_FIELDS });
    setClearPassword(false);
    setPasteUrl("");
    setPasteError(false);
    setShowErrors(false);
    setBanner(null);
  }, [open, proxy]);

  const setField = <K extends keyof FormFields>(key: K, value: FormFields[K]) => {
    setFields((prev) => ({ ...prev, [key]: value }));
    if (key === "password") setClearPassword(false);
  };

  const applyPasteUrl = () => {
    const result = parseProxyUrl(pasteUrl);
    if (!result.ok) {
      setPasteError(true);
      return;
    }
    const parsed = result.fields;
    setFields((prev) => ({
      ...prev,
      scheme: parsed.scheme,
      host: parsed.host,
      port: String(parsed.port),
      username: parsed.username,
      password: parsed.password,
    }));
    setClearPassword(false);
    setPasteError(false);
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const errors = validate(fields);
    if (Object.keys(errors).length > 0) {
      setShowErrors(true);
      setBanner(null);
      return;
    }
    setShowErrors(false);
    setBanner(null);

    const base = {
      name: fields.name.trim(),
      scheme: fields.scheme,
      host: fields.host.trim(),
      port: Number(fields.port.trim()),
      username: nullable(fields.username),
      country_code: nullableUpper(fields.country_code),
      region_label: nullable(fields.region_label),
      notes: nullable(fields.notes),
    };

    try {
      if (proxy) {
        const data: ProxyUpdateRequest = { ...base };
        if (clearPassword) data.password = null;
        else if (fields.password !== "") data.password = fields.password;
        await updateMutation.mutateAsync({ proxyId: proxy.id, data });
      } else {
        const data: ProxyCreateRequest = { ...base };
        if (fields.password !== "") data.password = fields.password;
        await createMutation.mutateAsync(data);
      }
      clearLocalState();
      onOpenChange(false);
      toast.show(t(proxy ? "proxyUpdateSuccess" : "proxyCreateSuccess"));
    } catch (err) {
      setBanner(describeError(err));
    }
  };

  const errors = validate(fields);
  const visibleErrors = showErrors ? errors : {};

  const fieldError = (key: FieldKey) => {
    const messageKey = visibleErrors[key];
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
          <div className="flex flex-col gap-xs">
            <FieldLabel>{t("proxyPasteUrlLabel")}</FieldLabel>
            <div className="flex items-center gap-sm">
              <Input
                data-testid="proxy-paste-url-input"
                aria-label={t("proxyPasteUrlLabel")}
                placeholder={t("proxyPasteUrlLabel")}
                value={pasteUrl}
                onChange={(event) => {
                  setPasteUrl(event.target.value);
                  setPasteError(false);
                }}
              />
              <Button
                data-testid="proxy-paste-url-apply"
                size="sm"
                onClick={applyPasteUrl}
              >
                {t("proxyPasteFromUrl")}
              </Button>
            </div>
            {pasteError && (
              <p
                data-testid="proxy-paste-url-error"
                className="font-ui text-label-sm text-danger"
              >
                {t("proxyPasteUrlInvalid")}
              </p>
            )}
          </div>

          <FieldRow label={t("proxyFormName")}>
            <Input
              data-testid="proxy-form-name"
              aria-label={t("proxyFormName")}
              value={fields.name}
              onChange={(event) => setField("name", event.target.value)}
            />
            {fieldError("name")}
          </FieldRow>

          <FieldRow label={t("proxyFormScheme")}>
            <div data-testid="proxy-form-scheme">
              <Select
                value={fields.scheme}
                onValueChange={(value) => setField("scheme", value as Scheme)}
                options={SCHEME_OPTIONS}
                ariaLabel={t("proxyFormScheme")}
              />
            </div>
            {fieldError("scheme")}
          </FieldRow>

          <FieldRow label={t("proxyFormHost")}>
            <Input
              data-testid="proxy-form-host"
              aria-label={t("proxyFormHost")}
              value={fields.host}
              onChange={(event) => setField("host", event.target.value)}
            />
            {fieldError("host")}
          </FieldRow>

          <FieldRow label={t("proxyFormPort")}>
            <Input
              data-testid="proxy-form-port"
              aria-label={t("proxyFormPort")}
              value={fields.port}
              onChange={(event) => setField("port", event.target.value)}
            />
            {fieldError("port")}
          </FieldRow>

          <FieldRow label={t("proxyFormUsername")}>
            <Input
              data-testid="proxy-form-username"
              aria-label={t("proxyFormUsername")}
              value={fields.username}
              onChange={(event) => setField("username", event.target.value)}
            />
            {fieldError("username")}
          </FieldRow>

          <FieldRow label={t("proxyFormPassword")}>
            <Input
              data-testid="proxy-form-password"
              aria-label={t("proxyFormPassword")}
              type="password"
              value={fields.password}
              placeholder={
                isEdit && proxy?.has_password ? t("proxyPasswordSet") : undefined
              }
              onChange={(event) => setField("password", event.target.value)}
            />
            {isEdit && proxy?.has_password && (
              <Button
                data-testid="proxy-form-clear-password"
                size="sm"
                variant={clearPassword ? "danger" : "secondary"}
                aria-pressed={clearPassword}
                onClick={() => {
                  setClearPassword(true);
                  setFields((prev) => ({ ...prev, password: "" }));
                }}
              >
                {t("proxyClearPassword")}
              </Button>
            )}
          </FieldRow>

          <FieldRow label={t("proxyFormCountryCode")}>
            <Input
              data-testid="proxy-form-country-code"
              aria-label={t("proxyFormCountryCode")}
              value={fields.country_code}
              onChange={(event) =>
                setField("country_code", event.target.value)
              }
            />
            {fieldError("country-code")}
          </FieldRow>

          <FieldRow label={t("proxyFormRegionLabel")}>
            <Input
              data-testid="proxy-form-region-label"
              aria-label={t("proxyFormRegionLabel")}
              value={fields.region_label}
              onChange={(event) =>
                setField("region_label", event.target.value)
              }
            />
            {fieldError("region-label")}
          </FieldRow>

          <FieldRow label={t("proxyFormNotes")}>
            <Input
              data-testid="proxy-form-notes"
              aria-label={t("proxyFormNotes")}
              value={fields.notes}
              onChange={(event) => setField("notes", event.target.value)}
            />
          </FieldRow>

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
            >
              {isEdit ? t("proxySave") : t("proxyCreate")}
            </Button>
          </div>
        </form>
      </div>
    </Dialog>
  );
}
