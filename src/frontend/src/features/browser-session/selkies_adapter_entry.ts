import { installSelkiesClientAdapter } from "./adapter";
import { resolveSelkiesProfileId } from "./selkies_profile_id";

// The viewer's identity comes from resolveSelkiesProfileId (strict
// single channel, t069); this entry only wires it into the adapter.
installSelkiesClientAdapter(
  window,
  resolveSelkiesProfileId(window.location.search)
);
