import React from "react";
import ReactDOM from "react-dom/client";
import type { JSX } from "react";
import { I18nProvider } from "../../../src/frontend/src/i18n";
import { ThemeProvider } from "../../../src/frontend/src/theme";
import { ToastProvider } from "../../../src/frontend/src/shared/ui";
import { defaultApiClient } from "../../../src/frontend/src/shared/api/client";
import { useBrowserSession } from "../../../src/frontend/src/features/browser-session/useBrowserSession";
import { SessionStagePanel } from "../../../src/frontend/src/features/browser-session/SessionStagePanel";

const params = new URLSearchParams(window.location.search);
const sessionPath = window.location.pathname.match(/\/session\/([^/]+)/);
const profileId =
  params.get("profileId") || params.get("profile_id") || sessionPath?.[1] || "default";

(window as any).__cbrowserHostLoaded = true;

// t039 D16 test-only host shell. The product SessionPage needs an
// authenticated profile/runtime query before it renders the iframe, but this
// fixture page is opened without a login session (the E2E drives the API with
// its own httpx client). Mount the real session hook + stage panel directly
// so the Selkies iframe and its WebRTC/datachannel probes stay testable.
function HostSessionView({ id }: { id: string }): JSX.Element {
  const iframeRef = React.useRef<HTMLIFrameElement>(null);
  const session = useBrowserSession(id, iframeRef, {
    apiClient: defaultApiClient,
  });
  return React.createElement(
    "div",
    {
      "data-testid": "sess-page",
      "data-stage": session.stage,
      style: { position: "relative", width: "100%", height: "100%" },
    },
    React.createElement("iframe", {
      ref: iframeRef,
      "data-testid": "sess-iframe",
      "data-stage": session.stage,
      src: `/selkies/index.html?profileId=${encodeURIComponent(id)}&_k=${session.reloadKey}`,
      allow: "autoplay; fullscreen; clipboard-read; clipboard-write",
      style: {
        position: "absolute",
        inset: 0,
        width: "100%",
        height: "100%",
        border: 0,
      },
    }),
    React.createElement(
      "div",
      {
        "data-testid": "sess-diag-overlay",
        style: { position: "absolute", inset: 0, pointerEvents: "none" },
      },
      session.stage !== "connected"
        ? React.createElement(SessionStagePanel, {
            stage: session.stage,
            diagnostics: session.diagnostics,
            onReconnect: session.reconnect,
            onViewStatus: () => undefined,
            onLaunch: () => undefined,
          })
        : null,
      React.createElement(
        "button",
        {
          "data-testid": "sess-audio-toggle",
          "data-audio-muted": session.audioMuted ? "true" : "false",
          "aria-pressed": session.audioMuted ? "true" : "false",
          onClick: session.toggleAudio,
          style: { position: "absolute", top: 4, right: 4, pointerEvents: "auto" },
        },
        "audio",
      ),
    ),
  );
}

const container = document.getElementById("root");
if (container) {
  // t039 D16: the host fixture's diagnostic assertions are written against
  // the zh locale, but Playwright's default navigator.language is en-US.
  // Pin the fixture locale so the shared SessionStagePanel renders the
  // expected zh stage text; product locale detection is untouched.
  localStorage.setItem("cbrowser.locale", "zh");
  const root = ReactDOM.createRoot(container);
  root.render(
    React.createElement(
      I18nProvider,
      null,
      React.createElement(
        ThemeProvider,
        null,
        React.createElement(
          ToastProvider,
          null,
          React.createElement(HostSessionView, { id: profileId }),
        ),
      ),
    ),
  );
}
