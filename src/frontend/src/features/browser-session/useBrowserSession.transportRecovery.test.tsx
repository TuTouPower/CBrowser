import { describe, it, expect, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import React from "react";
import { useBrowserSession } from "./useBrowserSession";
import { I18nProvider, en } from "../../i18n";
import type { ApiClient } from "../../shared/api/client";

// t026 AC-011: a first-connection signaling drop (e.g. WS 1006 while the
// Gateway/Stream pair is being replaced) is a recovery presentation
// while the transport layer reports "recovering"; only an explicit
// transport failure or an exhausted recovery window is signaling_failed.

function setup(transportState: string, windowMs = 60000) {
  const getRuntime = vi.fn(async () => ({
    profile_id: "p1",
    display_number: 1,
    desired_state: "running",
    observed_state: "running",
    transport: {
      profile_id: "p1",
      runtime_instance_id: "inst_1",
      browser_state: "running",
      stream_state: "running",
      transport_state: transportState,
    },
  }));
  const apiClient = {
    profiles: { getRuntime },
  } as unknown as ApiClient;
  const iframe = document.createElement("iframe");
  document.body.appendChild(iframe);
  const ref = { current: iframe } as React.RefObject<HTMLIFrameElement | null>;
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <I18nProvider>{children}</I18nProvider>
  );
  const rendered = renderHook(
    () =>
      useBrowserSession("p1", ref, {
        apiClient,
        runtimeState: "running",
        transportRecoveryWindowMs: windowMs,
      }),
    { wrapper },
  );
  return { ...rendered, iframe, getRuntime };
}

async function dispatchWsClose(iframe: HTMLIFrameElement, code: number) {
  const event = new MessageEvent("message", {
    data: { type: "CBROWSER_WS_CLOSE", code },
    origin: window.location.origin,
    source: iframe.contentWindow,
  } as MessageEventInit);
  await act(async () => {
    window.dispatchEvent(event);
  });
}

describe("useBrowserSession transport recovery (t026 AC-011)", () => {
  it("presents reconnecting while transport is recovering", async () => {
    const { result, iframe } = setup("recovering");
    await waitFor(() =>
      expect(result.current.stage).toBe("connecting_signaling"),
    );
    await dispatchWsClose(iframe, 1006);
    await waitFor(() => expect(result.current.stage).toBe("reconnecting"));
    // No reload yet: the session is waiting out the recovery window.
    expect(result.current.reloadKey).toBe(0);
  });

  it("fails immediately when transport is explicitly failed", async () => {
    const { result, iframe } = setup("failed");
    await waitFor(() =>
      expect(result.current.stage).toBe("connecting_signaling"),
    );
    await dispatchWsClose(iframe, 1006);
    await waitFor(() => expect(result.current.stage).toBe("signaling_failed"));
  });

  it("fails when the recovery window is already exhausted", async () => {
    const { result, iframe } = setup("recovering", 0);
    await waitFor(() =>
      expect(result.current.stage).toBe("connecting_signaling"),
    );
    await dispatchWsClose(iframe, 1006);
    await waitFor(() => expect(result.current.stage).toBe("signaling_failed"));
  });

  it("reconnects when transport becomes ready", async () => {
    const { result, iframe } = setup("ready");
    await waitFor(() =>
      expect(result.current.stage).toBe("connecting_signaling"),
    );
    await dispatchWsClose(iframe, 1006);
    await waitFor(() => expect(result.current.reloadKey).toBe(1));
    // The reload re-runs the runtime check, which lands on signaling again.
    await waitFor(() =>
      expect(result.current.stage).toBe("connecting_signaling"),
    );
  });

  it("AC-007: 信令失败只以固定 i18n 文案加关闭码呈现，忽略含凭据的关闭原因", async () => {
    const { result, iframe } = setup("failed");
    await waitFor(() =>
      expect(result.current.stage).toBe("connecting_signaling"),
    );
    const sensitiveReason =
      "auth token=SECRET-123 password=hunter2 session=sess-9 resume_key=rk-1";
    await act(async () => {
      window.dispatchEvent(
        new MessageEvent("message", {
          data: {
            type: "CBROWSER_WS_CLOSE",
            code: 1006,
            reason: sensitiveReason,
          },
          origin: window.location.origin,
          source: iframe.contentWindow,
        } as MessageEventInit),
      );
    });
    await waitFor(() => expect(result.current.stage).toBe("signaling_failed"));

    const message = result.current.errorMessage ?? "";
    expect(message).toBe(
      en.signalingDisconnected.replace("{code}", "1006"),
    );
    expect(message).toContain("1006");
    expect(message).not.toMatch(
      /token|password|session|secret|credential|resume_key|bearer|auth/i,
    );
    expect(message).not.toContain(sensitiveReason);
    expect(message).not.toContain("SECRET-123");
    expect(message).not.toContain("hunter2");
  });
});
