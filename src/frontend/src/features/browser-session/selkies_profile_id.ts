// Strict viewer identity (t069): the host page (SessionPage) passes the
// target through exactly one documented channel, the ?profileId= query
// parameter of the selkies iframe URL. An undocumented profile_id
// parameter, or a missing/empty profileId, is rejected instead of
// falling back to another identity source or a "default" profile.
export function resolveSelkiesProfileId(search: string): string {
  const params = new URLSearchParams(search);
  if (params.has("profile_id")) {
    throw new Error(
      "selkies adapter: the undocumented profile_id query parameter is not accepted; the host page passes profileId"
    );
  }
  const profileId = params.get("profileId");
  if (!profileId) {
    throw new Error(
      "selkies adapter: the profileId query parameter is required (set by the host page)"
    );
  }
  return profileId;
}
