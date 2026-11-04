/**
 * Same-origin resolution for every outbound entry point (ApiClient
 * requests, the SSE events stream, artifact download URLs).
 *
 * The decision is always made on the FINAL URL resolved against the
 * document origin — never on the raw endpoint prefix — so absolute,
 * protocol-relative, backslash and mixed variants cannot smuggle a
 * cross-origin target past the check: the WHATWG URL parser normalizes
 * backslashes for special schemes, which turns `/\evil.example` into the
 * protocol-relative `//evil.example`. Returns null when the target is
 * cross-origin or unparseable; callers must refuse to send credentials
 * or CSRF tokens in that case.
 */
export function resolveSameOriginUrl(raw: string): URL | null {
  let url: URL;
  try {
    url = new URL(raw, window.location.origin);
  } catch {
    return null;
  }
  return url.origin === window.location.origin ? url : null;
}
