export function sanitizeNextPath(raw: string | null | undefined): string | null {
  if (!raw) return null;
  if (!raw.startsWith("/")) return null;
  if (raw.startsWith("//")) return null;
  if (raw[1] === "\\") return null;
  if (/[\u0000-\u001f\u007f]/.test(raw)) return null;

  const path = raw.split(/[?#]/, 1)[0];
  if (path === "/login") return null;

  return raw;
}

export function loginRedirectPath(location: {
  pathname: string;
  search: string;
}): string {
  const target = sanitizeNextPath(`${location.pathname}${location.search}`);
  if (!target) return "/login";
  return `/login?next=${encodeURIComponent(target)}`;
}
