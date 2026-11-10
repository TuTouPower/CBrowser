import { describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import type { ProfileRuntimeResponse } from "../../shared/api/types";
import type { ProfileEventsClient } from "../../shared/api/sse";
import type { ProfileRuntimeEvent } from "../../shared/api/sse";
import {
  profileKeys,
  useProfileEventsSync,
} from "./useProfilesQuery";

type Listener = (event: ProfileRuntimeEvent) => void;

function makeFakeSse() {
  let listener: Listener | null = null;
  const client = {
    onEvent: (l: Listener) => {
      listener = l;
      return () => {
        listener = null;
      };
    },
    start: () => {},
    stop: () => {},
  };
  return {
    client: client as unknown as ProfileEventsClient,
    emit: (event: ProfileRuntimeEvent) => listener?.(event),
  };
}

function runtimeWithControl(control: Record<string, unknown>) {
  return {
    profile_id: "p1",
    display_number: 1,
    desired_state: "running",
    observed_state: "running",
    runtime_instance_id: "inst_1",
    config_version: 1,
    failure_count: 0,
    restart_blocked: false,
    last_exit_event_id: null,
    updated_at: "2026-11-04T00:00:00Z",
    control,
  } as unknown as ProfileRuntimeResponse;
}

function control(owner: string, generation: number) {
  return {
    profile_id: "p1",
    owner,
    generation,
    agent_instance_id: "tok_1",
    agent_session_id: "exec-1",
    handoff_reason: owner === "user" ? "human_input" : null,
    handoff_detail: null,
    agent_reclaim_allowed: owner === "agent",
    pending_supervisor_close: false,
    updated_at: "2026-11-04T00:00:00Z",
  };
}

function Probe({ sse }: { sse: ReturnType<typeof makeFakeSse> }) {
  useProfileEventsSync(sse.client);
  // Disabled query: observes the cache without refetching, so the
  // test sees exactly what the SSE merge wrote (no refetch masking).
  const q = useQuery({
    queryKey: profileKeys.runtime("p1"),
    queryFn: async () => runtimeWithControl(control("user", 4)),
    enabled: false,
  });
  const c = q.data?.control as unknown as
    | { owner: string; generation: number }
    | null
    | undefined;
  return (
    <div>
      <div data-testid="probe-owner">{c?.owner ?? "none"}</div>
      <div data-testid="probe-generation">{c?.generation ?? -1}</div>
    </div>
  );
}

describe("useProfileEventsSync control merge (t031)", () => {
  it("applies a newer-generation SSE control event to the cache (f007)", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    queryClient.setQueryData(
      profileKeys.runtime("p1"),
      runtimeWithControl(control("user", 4)),
    );
    const sse = makeFakeSse();
    render(
      <QueryClientProvider client={queryClient}>
        <Probe sse={sse} />
      </QueryClientProvider>,
    );
    expect(screen.getByTestId("probe-owner").textContent).toBe("user");
    sse.emit({
      profile_id: "p1",
      control: control("agent", 5),
      updated_at: "2026-11-04T00:00:01Z",
    } as unknown as ProfileRuntimeEvent);
    await waitFor(() =>
      expect(screen.getByTestId("probe-owner").textContent).toBe("agent"),
    );
    expect(screen.getByTestId("probe-generation").textContent).toBe("5");
  });

  it("ignores a stale-generation SSE control event (f006)", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    queryClient.setQueryData(
      profileKeys.runtime("p1"),
      runtimeWithControl(control("user", 4)),
    );
    const sse = makeFakeSse();
    render(
      <QueryClientProvider client={queryClient}>
        <Probe sse={sse} />
      </QueryClientProvider>,
    );
    // A delayed gen-3 event must not overwrite the gen-4 cache entry.
    sse.emit({
      profile_id: "p1",
      control: control("user", 3),
      updated_at: "2026-11-04T00:00:01Z",
    } as unknown as ProfileRuntimeEvent);
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.getByTestId("probe-owner").textContent).toBe("user");
    expect(screen.getByTestId("probe-generation").textContent).toBe("4");
  });
});
