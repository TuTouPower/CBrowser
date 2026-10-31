/**
 * Per-viewer audio control through the official Selkies pipelineControl message.
 *
 * The official client owns the audio element and data-channel commands; the host
 * never mutes the element or invents an audio channel itself.
 */

export interface AudioPipelineControlMessage {
  type: "pipelineControl";
  pipeline: "audio";
  enabled: boolean;
}

export function sendAudioPipelineControl(
  target: Window,
  origin: string,
  enabled: boolean
): void {
  const message: AudioPipelineControlMessage = {
    type: "pipelineControl",
    pipeline: "audio",
    enabled,
  };
  target.postMessage(message, origin);
}
