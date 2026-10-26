import { useEffect, useState } from "react";
import { Loader2, X } from "lucide-react";
import { api, type ManagerSettings, type SystemStatus } from "../lib/api";
import { useI18n } from "../i18n";
import { LanguageToggle } from "./LanguageToggle";

interface SettingsPanelProps {
  onClose: () => void;
  onSaved: (status: SystemStatus) => void;
}

export function SettingsPanel({ onClose, onSaved }: SettingsPanelProps) {
  const { t } = useI18n();
  const [current, setCurrent] = useState<ManagerSettings | null>(null);
  const [licenseKey, setLicenseKey] = useState("");
  const [channel, setChannel] = useState<"stable" | "preview">("stable");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getSettings()
      .then((s) => {
        setCurrent(s);
        setChannel(s.release_channel === "preview" ? "preview" : "stable");
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : t("failedToLoadSettings")),
      );
  }, [t]);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const payload: { license_key?: string; release_channel: string } = {
        release_channel: channel,
      };
      if (licenseKey.trim()) payload.license_key = licenseKey.trim();
      const status = await api.updateSettings(payload);
      onSaved(status);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("failedToSaveSettings"));
    } finally {
      setSaving(false);
    }
  };

  const handleClearKey = async () => {
    setSaving(true);
    setError(null);
    try {
      const status = await api.updateSettings({ license_key: "" });
      onSaved(status);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("failedToClearKey"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-lg border border-border bg-surface-1 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h2 className="text-sm font-semibold">{t("settings")}</h2>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-300"
            title={t("close")}
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-4 p-4">
          <div>
            <label className="label">{t("language")}</label>
            <div className="flex items-center gap-2">
              <LanguageToggle />
              <span className="text-xs text-gray-500">
                {t("languageEn")} / {t("languageZh")}
              </span>
            </div>
          </div>

          <div>
            <label className="label">{t("licenseKey")}</label>
            <input
              className="input font-mono"
              type="password"
              autoComplete="off"
              spellCheck={false}
              value={licenseKey}
              onChange={(e) => setLicenseKey(e.target.value)}
              placeholder={
                current?.license_key_set
                  ? t("licenseKeyPlaceholderSet", {
                      masked: current.license_key_masked ?? "set",
                    })
                  : t("licenseKeyPlaceholderEmpty")
              }
            />
            <p className="mt-1 text-xs text-gray-500">
              {t("licenseKeyHelp")}{" "}
              <a
                href="https://cloakbrowser.dev/free"
                target="_blank"
                rel="noreferrer"
                className="text-accent hover:underline"
              >
                {t("getFreeKey")}
              </a>
              .
            </p>
          </div>

          <div>
            <label className="label">{t("releaseChannel")}</label>
            <select
              className="input"
              value={channel}
              onChange={(e) =>
                setChannel(e.target.value === "preview" ? "preview" : "stable")
              }
            >
              <option value="stable">{t("channelStable")}</option>
              <option value="preview">{t("channelPreview")}</option>
            </select>
          </div>

          {error && <p className="text-xs text-red-400">{error}</p>}
        </div>

        <div className="flex items-center justify-between gap-2 border-t border-border px-4 py-3">
          {current?.license_key_set ? (
            <button
              onClick={handleClearKey}
              disabled={saving}
              className="text-xs text-gray-500 hover:text-red-400 disabled:opacity-50"
            >
              {t("removeKey")}
            </button>
          ) : (
            <span />
          )}
          <div className="flex items-center gap-2">
            <button onClick={onClose} disabled={saving} className="btn-secondary">
              {t("cancel")}
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              className="btn-primary flex items-center gap-1.5"
            >
              {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              <span>{saving ? t("applying") : t("save")}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
