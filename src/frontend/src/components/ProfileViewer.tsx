import { useEffect, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, ClipboardCopy, Loader2, Maximize2, Minimize2, RotateCcw, Send, X } from "lucide-react";
import { api } from "../lib/api";
import { CdpEndpointButton } from "./CdpEndpointButton";
import { ProfileFilesButton, useProfileFiles } from "./ProfileFiles";
import { useI18n } from "../i18n";

interface ProfileViewerProps {
  profileId: string;
  cdpUrl: string | null;
  clipboardSync: boolean;
  profileName: string;
  onClipboardSyncChange: (enabled: boolean) => Promise<void>;
  onDisconnect: () => void;
}

// X11 keysym for V key (Ctrl is already held in VNC by the time we intercept)
const XK_v = 0x0076;

async function writeHostClipboard(text: string): Promise<boolean> {
  if (!text) return false;
  if (navigator.clipboard?.writeText && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // Fall through to execCommand
    }
  }
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.top = "-9999px";
    ta.style.left = "-9999px";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    const success = document.execCommand("copy");
    document.body.removeChild(ta);
    return success;
  } catch (err) {
    console.warn("[clipboard] fallback copy failed:", err);
    return false;
  }
}

export function ProfileViewer({
  profileId,
  cdpUrl,
  clipboardSync: initialClipboardSync,
  profileName,
  onClipboardSyncChange,
  onDisconnect,
}: ProfileViewerProps) {
  const { t } = useI18n();
  const containerRef = useRef<HTMLDivElement>(null);
  // The canvas plus the drop overlay and transfer feedback; fullscreening the bare canvas
  // would hide every sign that a file is being uploaded.
  const stageRef = useRef<HTMLDivElement>(null);
  const rfbRef = useRef<any>(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fullscreen, setFullscreen] = useState(false);
  const [clipboardSync, setClipboardSync] = useState(initialClipboardSync);
  const [dragging, setDragging] = useState(false);
  const dragDepth = useRef(0);
  const files = useProfileFiles(profileId);
  const pasteTrapRef = useRef<HTMLTextAreaElement>(null);
  const [showClipboardInput, setShowClipboardInput] = useState(false);
  const [manualClipText, setManualClipText] = useState("");

  // A drop onto the canvas is caught HERE, in the Manager's own page — the VNC protocol
  // carries no files. The bytes go up over HTTP and land in this profile's file store.
  const hasFiles = (e: React.DragEvent) => e.dataTransfer?.types?.includes("Files");
  const onDragEnter = (e: React.DragEvent) => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    dragDepth.current += 1;
    setDragging(true);
  };
  const onDragOver = (e: React.DragEvent) => {
    if (hasFiles(e)) e.preventDefault();
  };
  const onDragLeave = (e: React.DragEvent) => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    dragDepth.current = Math.max(0, dragDepth.current - 1);
    if (dragDepth.current === 0) setDragging(false);
  };
  const onDrop = async (e: React.DragEvent) => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    dragDepth.current = 0;
    setDragging(false);
    // Every dropped file, not just the first: silently keeping one and discarding the rest
    // looks identical to success.
    const dropped = Array.from(e.dataTransfer.files ?? []);
    if (dropped.length) await files.uploadFiles(dropped);
  };

  useEffect(() => setClipboardSync(initialClipboardSync), [initialClipboardSync]);

  useEffect(() => {
    let rfb: any = null;
    let cancelled = false;

    async function connect() {
      try {
        // Import noVNC dynamically
        const { default: RFB } = await import("@novnc/novnc/core/rfb.js");

        if (cancelled) return;

        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        const wsUrl = `${protocol}//${window.location.host}/api/profiles/${profileId}/vnc`;

        rfb = new RFB(containerRef.current!, wsUrl, {
          wsProtocols: ["binary"],
        });
        rfbRef.current = rfb;

        rfb.scaleViewport = true;
        rfb.resizeSession = false;
        rfb.showDotCursor = true;

        rfb.addEventListener("connect", () => {
          if (!cancelled) setConnected(true);
        });

        rfb.addEventListener("disconnect", () => {
          if (!cancelled) {
            setConnected(false);
            onDisconnect();
          }
        });

        rfb.addEventListener("securityfailure", (e: any) => {
          setError(`Security failure: ${e.detail.reason}`);
        });
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : t("failedToConnect"));
        }
      }
    }

    connect();

    return () => {
      cancelled = true;
      if (rfb) {
        try {
          rfb.disconnect();
        } catch (err) {
          console.debug("[vnc] disconnect cleanup failed:", err);
        }
      }
      rfbRef.current = null;
    };
  }, [profileId, onDisconnect]);

  // Host→VNC: handle paste into VNC session
  useEffect(() => {
    if (!clipboardSync || !connected) return;

    const sendPasteToVnc = async (text: string) => {
      if (!text) return;
      try {
        console.log("[clipboard] pushing text to VNC clipboard via API...");
        await api.setClipboard(profileId, text);
        const rfb = rfbRef.current;
        if (rfb) {
          console.log("[clipboard] injecting Ctrl+V to VNC");
          rfb.sendKey(0xffe3, "ControlLeft", true);
          rfb.sendKey(XK_v, "KeyV", true);
          rfb.sendKey(XK_v, "KeyV", false);
          rfb.sendKey(0xffe3, "ControlLeft", false);
        }
      } catch (err) {
        console.warn("[clipboard] setClipboard API failed:", err);
      }
    };

    // 1. Native paste: works in non-secure HTTP / LAN contexts
    const handlePaste = (e: ClipboardEvent) => {
      const active = document.activeElement;
      if (active && (active.tagName === "INPUT" || active.tagName === "TEXTAREA")) {
        return; // Don't steal paste if user is typing in manager's own form
      }
      const text = e.clipboardData?.getData("text/plain");
      if (text) {
        e.preventDefault();
        e.stopPropagation();
        sendPasteToVnc(text);
      }
    };

    // 2. Keyboard shortcut: Cmd+V / Ctrl+V
    const handleKeyDown = async (e: KeyboardEvent) => {
      const active = document.activeElement;
      if (active && (active.tagName === "INPUT" || active.tagName === "TEXTAREA")) {
        return;
      }
      const isPaste =
        (e.key === "v" || e.key === "V") &&
        (e.ctrlKey || e.metaKey) &&
        !e.altKey &&
        !e.shiftKey;
      if (!isPaste) return;

      if (pasteTrapRef.current) {
        pasteTrapRef.current.value = "";
        pasteTrapRef.current.focus();
        pasteTrapRef.current.select();
      }

      if (navigator.clipboard?.readText && window.isSecureContext) {
        try {
          const text = await navigator.clipboard.readText();
          if (text) {
            e.preventDefault();
            e.stopPropagation();
            await sendPasteToVnc(text);
          }
        } catch (err) {
          console.debug("[clipboard] readText fallback:", err);
        }
      }
    };

    window.addEventListener("paste", handlePaste, true);
    window.addEventListener("keydown", handleKeyDown, true);
    return () => {
      window.removeEventListener("paste", handlePaste, true);
      window.removeEventListener("keydown", handleKeyDown, true);
    };
  }, [profileId, clipboardSync, connected]);

  // VNC→Host: listen for noVNC "clipboard" event
  useEffect(() => {
    const rfb = rfbRef.current;
    if (!rfb || !clipboardSync || !connected) return;

    const handleClipboard = (e: any) => {
      const text = e.detail?.text;
      if (text) {
        writeHostClipboard(text);
      }
    };

    rfb.addEventListener("clipboard", handleClipboard);
    return () => {
      rfb.removeEventListener("clipboard", handleClipboard);
    };
  }, [clipboardSync, connected]);

  // VNC→Host polling via Playwright CDP
  useEffect(() => {
    if (!clipboardSync || !connected) return;

    let cancelled = false;
    let lastText = "";

    const poll = async () => {
      if (cancelled) return;
      try {
        const { text } = await api.getClipboard(profileId);
        if (text && text !== lastText) {
          lastText = text;
          console.log("[clipboard] poll: new text from VNC:", text.substring(0, 30));
          await writeHostClipboard(text);
        }
      } catch (err) {
        console.debug("[clipboard] poll temporary error:", err);
      }
      if (!cancelled) {
        timer = setTimeout(poll, 1500);
      }
    };

    // Start polling after a short delay
    let timer = setTimeout(poll, 2000);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [profileId, clipboardSync, connected]);

  const toggleClipboardSync = async () => {
    const previous = clipboardSync;
    const next = !previous;
    setClipboardSync(next);
    try {
      await onClipboardSyncChange(next);
    } catch (err) {
      console.warn("[clipboard] failed to persist preference:", err);
      setClipboardSync(previous);
    }
  };

  const toggleFullscreen = () => {
    if (!stageRef.current) return;
    if (!document.fullscreenElement) {
      stageRef.current.requestFullscreen();
      setFullscreen(true);
    } else {
      document.exitFullscreen();
      setFullscreen(false);
    }
  };

  useEffect(() => {
    const handleFsChange = () => {
      setFullscreen(!!document.fullscreenElement);
    };
    document.addEventListener("fullscreenchange", handleFsChange);
    return () => document.removeEventListener("fullscreenchange", handleFsChange);
  }, []);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const handleWheel = (e: WheelEvent) => {
      e.preventDefault();
    };

    container.addEventListener("wheel", handleWheel, { passive: false });
    return () => container.removeEventListener("wheel", handleWheel);
  }, []);

  if (error) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <p className="text-red-400 text-sm mb-2">{t("connectionFailed")}</p>
          <p className="text-gray-500 text-xs">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="relative h-full flex flex-col">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-3 py-1.5 bg-surface-1 border-b border-border">
        <div className="flex items-center gap-2">
          <span className={`h-2 w-2 rounded-full ${connected ? "bg-emerald-400" : "bg-yellow-400 animate-pulse"}`} />
          <span className="text-xs text-gray-400">
            {connected ? t("connected") : t("connecting")}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <CdpEndpointButton cdpUrl={cdpUrl} />
          <ProfileFilesButton
            profileId={profileId}
            profileName={profileName}
            files={files.files}
            uploading={files.uploading}
            error={files.error}
            onUpload={files.uploadFiles}
            onRemove={files.remove}
            onRefresh={files.refresh}
            onClearError={files.clearError}
          />
          <button
            onClick={toggleClipboardSync}
            className={`p-1 ${clipboardSync ? "text-accent" : "text-gray-500 hover:text-gray-300"}`}
            title={clipboardSync ? t("disableClipboardSync") : t("enableClipboardSync")}
          >
            <ClipboardCopy className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={() => setShowClipboardInput(!showClipboardInput)}
            className={`p-1 ${showClipboardInput ? "text-accent bg-surface-3 rounded" : "text-gray-500 hover:text-gray-300"}`}
            title={t("sendToBrowser")}
          >
            <Send className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={toggleFullscreen}
            className="text-gray-500 hover:text-gray-300 p-1"
            title={fullscreen ? t("exitFullscreen") : t("fullscreen")}
          >
            {fullscreen ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
          </button>
          <button
            onClick={async () => {
              try {
                await api.centerWindow(profileId);
              } catch (e) {
                console.warn("Failed to center window:", e);
              }
            }}
            className="text-gray-500 hover:text-gray-300 p-1"
            title={t("centerWindow")}
          >
            <RotateCcw className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {showClipboardInput && (
        <div className="flex items-center gap-2 px-3 py-1.5 bg-surface-2 border-b border-border z-30">
          <input
            type="text"
            value={manualClipText}
            onChange={(e) => setManualClipText(e.target.value)}
            onKeyDown={async (e) => {
              if (e.key === "Enter" && manualClipText) {
                await api.setClipboard(profileId, manualClipText);
                const rfb = rfbRef.current;
                if (rfb) {
                  rfb.sendKey(0xffe3, "ControlLeft", true);
                  rfb.sendKey(XK_v, "KeyV", true);
                  rfb.sendKey(XK_v, "KeyV", false);
                  rfb.sendKey(0xffe3, "ControlLeft", false);
                }
                setManualClipText("");
                setShowClipboardInput(false);
              }
            }}
            placeholder={t("sendTextPlaceholder")}
            className="input flex-1 text-xs py-1 px-2"
            autoFocus
          />
          <button
            onClick={async () => {
              if (manualClipText) {
                await api.setClipboard(profileId, manualClipText);
                const rfb = rfbRef.current;
                if (rfb) {
                  rfb.sendKey(0xffe3, "ControlLeft", true);
                  rfb.sendKey(XK_v, "KeyV", true);
                  rfb.sendKey(XK_v, "KeyV", false);
                  rfb.sendKey(0xffe3, "ControlLeft", false);
                }
                setManualClipText("");
                setShowClipboardInput(false);
              }
            }}
            className="btn btn-primary text-xs px-2.5 py-1 whitespace-nowrap"
          >
            {t("send")}
          </button>
          <button
            onClick={() => setShowClipboardInput(false)}
            className="p-1 text-gray-400 hover:text-gray-200"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {/* VNC canvas container, doubling as a drop target for file uploads */}
      <div
        ref={stageRef}
        className="relative flex-1 bg-black"
        style={{ minHeight: 0 }}
        onDragEnter={onDragEnter}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
      >
        <textarea
          ref={pasteTrapRef}
          tabIndex={-1}
          aria-hidden="true"
          className="fixed -top-96 left-0 opacity-0 pointer-events-none w-1 h-1"
          onPaste={async (e) => {
            const text = e.clipboardData.getData("text/plain");
            if (text) {
              e.preventDefault();
              await api.setClipboard(profileId, text);
              const rfb = rfbRef.current;
              if (rfb) {
                rfb.sendKey(0xffe3, "ControlLeft", true);
                rfb.sendKey(XK_v, "KeyV", true);
                rfb.sendKey(XK_v, "KeyV", false);
                rfb.sendKey(0xffe3, "ControlLeft", false);
              }
              const canvas = containerRef.current?.querySelector("canvas");
              if (canvas) (canvas as HTMLElement).focus();
            }
          }}
          onInput={async (e) => {
            const text = e.currentTarget.value;
            if (text) {
              e.currentTarget.value = "";
              await api.setClipboard(profileId, text);
              const rfb = rfbRef.current;
              if (rfb) {
                rfb.sendKey(0xffe3, "ControlLeft", true);
                rfb.sendKey(XK_v, "KeyV", true);
                rfb.sendKey(XK_v, "KeyV", false);
                rfb.sendKey(0xffe3, "ControlLeft", false);
              }
              const canvas = containerRef.current?.querySelector("canvas");
              if (canvas) (canvas as HTMLElement).focus();
            }
          }}
        />
        <div ref={containerRef} className="absolute inset-0 bg-black overflow-hidden" />
        {/* Transfer feedback lives here, not in the panel: a drop must not look like it
            reached the web page just because the panel happens to be closed. */}
        {files.transfers.length > 0 && (
          <div className="absolute bottom-3 left-3 z-20 w-80 space-y-1.5">
            {files.transfers.map((transfer) => (
              <div
                key={transfer.id}
                role={transfer.state === "failed" ? "alert" : "status"}
                className="flex items-start gap-2 rounded-md border border-border bg-surface-2/95 px-3 py-2 shadow-lg"
              >
                {transfer.state === "uploading" ? (
                  <Loader2 className="mt-0.5 h-3.5 w-3.5 shrink-0 animate-spin text-accent" />
                ) : transfer.state === "done" ? (
                  <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-400" />
                ) : (
                  <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-red-400" />
                )}
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm text-gray-200" title={transfer.name}>
                    {transfer.name}
                  </div>
                  <div className="text-xs text-gray-400">
                    {transfer.state === "uploading"
                      ? t("uploadingToProfile")
                      : transfer.state === "done"
                        ? t("inProfileFilesHint", { name: profileName })
                        : transfer.error}
                  </div>
                  {transfer.state === "failed" && (
                    <button
                      type="button"
                      onClick={() => void files.retryTransfer(transfer.id)}
                      className="mt-1 text-xs text-accent hover:underline"
                    >
                      {t("retry")}
                    </button>
                  )}
                </div>
                {transfer.state !== "uploading" && (
                  <button
                    type="button"
                    onClick={() => files.dismissTransfer(transfer.id)}
                    className="p-0.5 text-gray-500 hover:text-gray-300"
                    aria-label={`Dismiss ${transfer.name}`}
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            ))}
          </div>
        )}

        {dragging && (
          <div className="pointer-events-none absolute inset-0 z-10 m-2 flex items-center justify-center rounded-md border-2 border-dashed border-accent bg-black/70">
            <div className="text-center">
              <p className="text-sm font-medium text-gray-100">{t("dropToUpload")}</p>
              <p className="mt-1 text-xs text-gray-400">
                {t("dropToUploadHint", { name: profileName })}
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
