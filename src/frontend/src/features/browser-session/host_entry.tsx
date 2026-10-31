import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserSessionView } from "./BrowserSessionView";
import { I18nProvider } from "../../i18n";

const params = new URLSearchParams(window.location.search);
const profileId =
  params.get("profileId") || params.get("profile_id") || "default";

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
