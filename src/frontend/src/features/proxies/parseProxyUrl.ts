import type { ProxyCreateRequest } from "../../shared/api/types";

export type ProxyScheme = ProxyCreateRequest["scheme"];

export type ParsedProxyFields = {
  scheme: ProxyScheme;
  host: ProxyCreateRequest["host"];
  port: ProxyCreateRequest["port"];
  username: string;
  password: string;
};

export type ParseProxyUrlResult =
  | { ok: true; fields: ParsedProxyFields }
  | { ok: false; error: string };

function isProxyScheme(value: string): value is ProxyScheme {
  return value === "http" || value === "https" || value === "socks5";
}

export function parseProxyUrl(input: string): ParseProxyUrlResult {
  const fail = (error: string): ParseProxyUrlResult => ({ ok: false, error });

  if (typeof input !== "string" || input.trim().length === 0) {
    return fail("empty proxy url");
  }
  const raw = input.trim();

  const schemeMatch = /^([A-Za-z][A-Za-z0-9+.-]*):\/\//.exec(raw);
  if (!schemeMatch) return fail("missing scheme");
  const scheme = (schemeMatch[1] ?? "").toLowerCase();
  if (!isProxyScheme(scheme)) return fail(`unsupported scheme: ${scheme}`);

  const schemeToken = schemeMatch[0] ?? "";
  const rest = raw.slice(schemeToken.length);
  const authorityEnd = rest.search(/[/?#]/);
  const authority = authorityEnd === -1 ? rest : rest.slice(0, authorityEnd);
  if (authority.length === 0) return fail("missing host");

  const atCount = (authority.match(/@/g) ?? []).length;
  if (atCount > 1) return fail("multiple @ in authority");
  let userinfo = "";
  let hostport = authority;
  if (atCount === 1) {
    const at = authority.indexOf("@");
    userinfo = authority.slice(0, at);
    hostport = authority.slice(at + 1);
  }

  let username = "";
  let password = "";
  if (userinfo.length > 0) {
    const colon = userinfo.indexOf(":");
    const rawUsername = colon === -1 ? userinfo : userinfo.slice(0, colon);
    const rawPassword = colon === -1 ? "" : userinfo.slice(colon + 1);
    try {
      username = decodeURIComponent(rawUsername);
      password = decodeURIComponent(rawPassword);
    } catch {
      return fail("malformed percent-encoding in credentials");
    }
  }

  let host: string;
  let portText: string;
  const bracketed = hostport.startsWith("[");
  if (bracketed) {
    const close = hostport.indexOf("]");
    if (close === -1) return fail("unclosed IPv6 bracket");
    host = hostport.slice(1, close);
    const after = hostport.slice(close + 1);
    if (!after.startsWith(":")) return fail("missing port");
    portText = after.slice(1);
  } else {
    const colon = hostport.lastIndexOf(":");
    if (colon === -1) return fail("missing port");
    host = hostport.slice(0, colon);
    portText = hostport.slice(colon + 1);
  }

  if (!/^\d+$/.test(portText)) return fail("invalid port");
  const port = Number(portText);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    return fail("port out of range");
  }

  if (host.length === 0) return fail("missing host");
  const forbiddenHostChars = [" ", "\t", "\n", "\r", "[", "]", "/", "?", "#", "@"];
  if (forbiddenHostChars.some((char) => host.includes(char))) {
    return fail("invalid host");
  }
  if (!bracketed && host.includes(":")) return fail("invalid host");

  return {
    ok: true,
    fields: { scheme, host, port, username, password },
  };
}
