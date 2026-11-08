import { useSyncExternalStore } from "react";
import type { JSX } from "react";
import {
  SessionDiagnosticsSource,
  type SessionDiagnosticsStoreSnapshot,
} from "./diagnostics_source";
import {
  SessionStagePanel,
  type SessionStagePanelProps,
} from "./SessionStagePanel";
import type { SessionDiagnosticsData } from "./types";

export interface SessionStagePanelConnectedProps
  extends Omit<SessionStagePanelProps, "diagnostics"> {
  diagnostics: SessionDiagnosticsData;
  source?: SessionDiagnosticsSource | null;
}

const EMPTY_SNAPSHOT: SessionDiagnosticsStoreSnapshot = {
  connection: {
    connected: false,
    hasFrames: false,
    connectionState: null,
    iceConnectionState: null,
    signalingState: null,
  },
  diagnostics: {},
};
const idleSubscribe = (_listener: () => void): (() => void) => () => {};
const idleGetSnapshot = (): SessionDiagnosticsStoreSnapshot => EMPTY_SNAPSHOT;

export function SessionStagePanelConnected(
  props: SessionStagePanelConnectedProps
): JSX.Element {
  const { source, diagnostics, ...panelProps } = props;
  const snapshot = useSyncExternalStore(
    source?.subscribe ?? idleSubscribe,
    source?.getSnapshot ?? idleGetSnapshot
  );
  const { connection, diagnostics: sample } = snapshot;
  const merged: SessionDiagnosticsData = {
    ...diagnostics,
    connectionState: connection.connectionState ?? undefined,
    iceConnectionState: connection.iceConnectionState ?? undefined,
    signalingState: connection.signalingState ?? undefined,
    framesDecoded: sample.framesDecoded,
    keyFramesDecoded: sample.keyFramesDecoded,
    packetsLost: sample.packetsLost,
    packetsReceived: sample.packetsReceived,
    roundTripTime: sample.roundTripTime,
    audioStatus: sample.audioStatus,
    selectedPair: sample.selectedPair ?? null,
  };
  return <SessionStagePanel {...panelProps} diagnostics={merged} />;
}
