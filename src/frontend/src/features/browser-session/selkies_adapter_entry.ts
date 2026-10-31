import { installSelkiesClientAdapter } from "./adapter";

const params = new URLSearchParams(window.location.search);
const profileId =
  params.get("profileId") || params.get("profile_id") || "default";

installSelkiesClientAdapter(window, profileId);
