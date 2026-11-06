import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserSessionView } from "../../../src/frontend/src/features/browser-session/BrowserSessionView";
import { I18nProvider } from "../../../src/frontend/src/i18n";

const params = new URLSearchParams(window.location.search);
const sessionPath = window.location.pathname.match(/\/session\/([^/]+)/);
const profileId =
  params.get("profileId") || params.get("profile_id") || sessionPath?.[1] || "default";

(window as any).__cbrowserHostLoaded = true;

const container = document.getElementById("root");
if (container) {
  const root = ReactDOM.createRoot(container);
  root.render(
    React.createElement(
      I18nProvider,
      null,
      React.createElement(BrowserSessionView, {
        profileId,
        onCheckRuntimeStatus: () => {
          (window as any).__statusBtnClicked = true;
        },
      })
    )
  );
}
