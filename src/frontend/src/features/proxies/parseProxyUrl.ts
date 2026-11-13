/**
 * Proxy-link parser (t052). Mirrors the backend value object in
 * `src/backend/cbrowser/domain/proxy_endpoint.py` — the four accepted
 * formats, error codes, host normalisation and percent-decoding rules
 * must stay in lock-step with it.
 *
 * Four formats:
 * 1. standard URL `scheme://user:pass@host:port`
 * 2. schemeless `host:port` (defaults to `http`)
 * 3. `host:port:user:pass`
 * 4. `user:pass@host:port`
 *
 * IPv6 hosts must be bracketed. The password is write-only: it never
 * appears in the redacted link or the display name.
 */

export type ProxyScheme = "http" | "https" | "socks5";

export type ParsedProxyFields = {
  scheme: ProxyScheme;
  host: string;
  port: number;
  username: string | null;
  password: string | null;
};

export type ParseProxyUrlResult =
  | { ok: true; fields: ParsedProxyFields }
  | { ok: false; error: string; code: string };

const SCHEMES: ProxyScheme[] = ["http", "https", "socks5"];

function isProxyScheme(value: string): value is ProxyScheme {
  return (SCHEMES as string[]).includes(value);
}

function fail(code: string, error: string): ParseProxyUrlResult {
  return { ok: false, error, code };
}

function percentDecode(value: string): string | null {
  if (/%(?![0-9A-Fa-f]{2})/.test(value)) return null;
  try {
    return decodeURIComponent(value);
  } catch {
    return null;
  }
}

/** Strict userinfo encoding: `encodeURIComponent` leaves `!'()*` raw. */
export function encodeUserinfo(value: string): string {
  return encodeURIComponent(value).replace(
    /[!'()*]/g,
    (char) => `%${char.charCodeAt(0).toString(16).toUpperCase().padStart(2, "0")}`,
  );
}

function formatHost(host: string): string {
  return host.includes(":") ? `[${host}]` : host;
}

/** Split a `::`-compressed literal into head/tail groups, or null on a
 * second `::`. Without `::` the whole literal is the head. */
function splitCompressedIpv6(
  raw: string,
): { head: string[]; tail: string[] } | null {
  const idx = raw.indexOf("::");
  if (idx === -1) return { head: raw.split(":"), tail: [] };
  const left = raw.slice(0, idx);
  const right = raw.slice(idx + 2);
  if (raw.indexOf("::", idx + 2) !== -1) return null;
  return {
    head: left === "" ? [] : left.split(":"),
    tail: right === "" ? [] : right.split(":"),
  };
}

/** Expand an embedded IPv4 dotted quad into two hex groups per part. */
function expandEmbeddedV4(parts: string[]): string[] | null {
  const out: string[] = [];
  for (const part of parts) {
    if (!part.includes(".")) {
      out.push(part);
      continue;
    }
    const octets = part.split(".");
    if (octets.length !== 4) return null;
    const nums = octets.map((o) => (/^\d+$/.test(o) ? Number(o) : -1));
    if (nums.some((n) => n < 0 || n > 255)) return null;
    out.push(
      ((nums[0]! << 8) + nums[1]!).toString(16),
      ((nums[2]! << 8) + nums[3]!).toString(16),
    );
  }
  return out;
}

/** Longest run of zeroes (length >= 2, first wins on ties). */
function longestZeroRun(full: number[]): { start: number; len: number } {
  let bestStart = -1;
  let bestLen = 0;
  let curStart = -1;
  let curLen = 0;
  for (let i = 0; i < full.length; i++) {
    if (full[i] === 0) {
      if (curStart === -1) {
        curStart = i;
        curLen = 1;
      } else {
        curLen += 1;
      }
      if (curLen > bestLen) {
        bestLen = curLen;
        bestStart = curStart;
      }
    } else {
      curStart = -1;
      curLen = 0;
    }
  }
  return { start: bestStart, len: bestLen };
}

/** Render 8 groups with `::` compression of the longest zero run. */
function renderCompressedIpv6(full: number[]): string {
  const hex = full.map((g) => g.toString(16));
  const { start, len } = longestZeroRun(full);
  if (len < 2) return hex.join(":");
  const left = hex.slice(0, start).join(":");
  const right = hex.slice(start + len).join(":");
  if (left === "" && right === "") return "::";
  if (left === "") return `::${right}`;
  if (right === "") return `${left}::`;
  return `${left}::${right}`;
}

/** Parse an IPv6 literal and return its compressed form, or null. */
export function compressIpv6(raw: string): string | null {
  const compressed = raw.includes("::");
  const split = splitCompressedIpv6(raw);
  if (split === null) return null;
  const headExpanded = expandEmbeddedV4(split.head);
  const tailExpanded = expandEmbeddedV4(split.tail);
  if (headExpanded === null || tailExpanded === null) return null;
  const all = [...headExpanded, ...tailExpanded];
  if (all.some((part) => !/^[0-9A-Fa-f]{1,4}$/.test(part))) return null;
  const groups = all.map((part) => parseInt(part, 16));
  let full: number[];
  if (compressed) {
    if (groups.length > 7) return null;
    const missing = 8 - groups.length;
    full = [
      ...groups.slice(0, headExpanded.length),
      ...new Array<number>(missing).fill(0),
      ...groups.slice(headExpanded.length),
    ];
  } else {
    if (groups.length !== 8) return null;
    full = groups;
  }
  return renderCompressedIpv6(full);
}

function isValidIpv4(raw: string): boolean {
  const parts = raw.split(".");
  if (parts.length !== 4) return false;
  return parts.every((part) => {
    if (!/^\d+$/.test(part)) return false;
    // ipaddress rejects leading zeroes.
    if (part.length > 1 && part.startsWith("0")) return false;
    return Number(part) <= 255;
  });
}

function normalizeHost(
  rawHost: string,
  bracketed: boolean,
): { ok: true; host: string } | { ok: false; code: string; error: string } {
  if (rawHost.length === 0) {
    return { ok: false, code: "missing_host", error: "missing host" };
  }
  const forbidden = [" ", "\t", "\n", "\r", "[", "]", "/", "?", "#", "@"];
  if (forbidden.some((char) => rawHost.includes(char))) {
    return { ok: false, code: "invalid_host", error: "invalid host" };
  }
  if (bracketed) {
    const compressed = compressIpv6(rawHost);
    if (compressed === null) {
      return { ok: false, code: "invalid_host", error: "invalid IPv6 host" };
    }
    return { ok: true, host: compressed };
  }
  if (rawHost.includes(":")) {
    return { ok: false, code: "invalid_host", error: "invalid host" };
  }
  if (isValidIpv4(rawHost)) return { ok: true, host: rawHost };
  return { ok: true, host: rawHost.toLowerCase() };
}

function parsePort(
  portText: string,
): { ok: true; port: number } | { ok: false; code: string; error: string } {
  if (!/^\d+$/.test(portText)) {
    return { ok: false, code: "invalid_port", error: "invalid port" };
  }
  const port = Number(portText);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    return { ok: false, code: "port_out_of_range", error: "port out of range" };
  }
  return { ok: true, port };
}

function splitHostPort(
  text: string,
): { ok: true; host: string; port: number } | { ok: false; code: string; error: string } {
  if (text.startsWith("[")) {
    const close = text.indexOf("]");
    if (close === -1) {
      return {
        ok: false,
        code: "unclosed_ipv6_bracket",
        error: "unclosed IPv6 bracket",
      };
    }
    const host = normalizeHost(text.slice(1, close), true);
    if (!host.ok) return host;
    const after = text.slice(close + 1);
    if (!after.startsWith(":")) {
      return { ok: false, code: "missing_port", error: "missing port" };
    }
    const port = parsePort(after.slice(1));
    if (!port.ok) return port;
    return { ok: true, host: host.host, port: port.port };
  }
  const colon = text.lastIndexOf(":");
  if (colon === -1) {
    return { ok: false, code: "missing_port", error: "missing port" };
  }
  const host = normalizeHost(text.slice(0, colon), false);
  if (!host.ok) return host;
  const port = parsePort(text.slice(colon + 1));
  if (!port.ok) return port;
  return { ok: true, host: host.host, port: port.port };
}

function splitUserinfo(
  userinfo: string,
):
  | { ok: true; username: string | null; password: string | null }
  | { ok: false; code: string; error: string } {
  if (userinfo.length === 0) return { ok: true, username: null, password: null };
  const colon = userinfo.indexOf(":");
  const rawUsername = colon === -1 ? userinfo : userinfo.slice(0, colon);
  const rawPassword = colon === -1 ? "" : userinfo.slice(colon + 1);
  const username = percentDecode(rawUsername);
  if (username === null) {
    return {
      ok: false,
      code: "malformed_percent_encoding",
      error: "malformed percent-encoding in credentials",
    };
  }
  let password: string | null = null;
  if (colon !== -1) {
    password = percentDecode(rawPassword);
    if (password === null) {
      return {
        ok: false,
        code: "malformed_percent_encoding",
        error: "malformed percent-encoding in credentials",
      };
    }
  }
  return {
    ok: true,
    username: username === "" ? null : username,
    password: password === "" ? null : password,
  };
}

function buildFields(
  scheme: ProxyScheme,
  host: string,
  port: number,
  username: string | null,
  password: string | null,
): ParseProxyUrlResult {
  if (password !== null && username === null) {
    return fail("invalid_credentials", "password without username");
  }
  return { ok: true, fields: { scheme, host, port, username, password } };
}

function parseUrlForm(raw: string): ParseProxyUrlResult {
  const match = /^([A-Za-z][A-Za-z0-9+.-]*):\/\/(.*)$/s.exec(raw);
  if (!match) return fail("missing_host", "missing host");
  const scheme = (match[1] ?? "").toLowerCase();
  if (!isProxyScheme(scheme)) {
    return fail("unsupported_scheme", `unsupported scheme: ${scheme}`);
  }
  const rest = match[2] ?? "";
  let authorityEnd = rest.length;
  for (const sep of ["/", "?", "#"]) {
    const idx = rest.indexOf(sep);
    if (idx !== -1) authorityEnd = Math.min(authorityEnd, idx);
  }
  const authority = rest.slice(0, authorityEnd);
  if (authority.length === 0) return fail("missing_host", "missing host");
  const atCount = (authority.match(/@/g) ?? []).length;
  if (atCount > 1) return fail("multiple_at_signs", "multiple @ in authority");
  let userinfo = "";
  let hostport = authority;
  if (atCount === 1) {
    const at = authority.indexOf("@");
    userinfo = authority.slice(0, at);
    hostport = authority.slice(at + 1);
  }
  const credentials = splitUserinfo(userinfo);
  if (!credentials.ok) return credentials;
  const endpoint = splitHostPort(hostport);
  if (!endpoint.ok) return endpoint;
  return buildFields(
    scheme,
    endpoint.host,
    endpoint.port,
    credentials.username,
    credentials.password,
  );
}

function parseSchemeless(raw: string): ParseProxyUrlResult {
  // Format 4 (user:pass@host:port): the part after the last "@" must itself
  // parse as host:port, otherwise fall through to formats 2/3.
  if (raw.includes("@")) {
    const at = raw.lastIndexOf("@");
    const left = raw.slice(0, at);
    const right = raw.slice(at + 1);
    if (right.includes(":") && !left.includes("@")) {
      const endpoint = splitHostPort(right);
      if (endpoint.ok) {
        const credentials = splitUserinfo(left);
        if (!credentials.ok) return credentials;
        return buildFields(
          "http",
          endpoint.host,
          endpoint.port,
          credentials.username,
          credentials.password,
        );
      }
    }
  }
  if (raw.startsWith("[")) {
    const close = raw.indexOf("]");
    if (close === -1) {
      return fail("unclosed_ipv6_bracket", "unclosed IPv6 bracket");
    }
    const host = normalizeHost(raw.slice(1, close), true);
    if (!host.ok) return host;
    const after = raw.slice(close + 1);
    if (!after.startsWith(":")) {
      return fail("missing_port", "missing port");
    }
    const rest = after.slice(1);
    const sep = rest.indexOf(":");
    const port = parsePort(sep === -1 ? rest : rest.slice(0, sep));
    if (!port.ok) return port;
    if (sep === -1) {
      return buildFields("http", host.host, port.port, null, null);
    }
    const credentials = splitUserinfo(rest.slice(sep + 1));
    if (!credentials.ok) return credentials;
    return buildFields(
      "http",
      host.host,
      port.port,
      credentials.username,
      credentials.password,
    );
  }
  const parts = raw.split(":");
  if (parts.length === 2) {
    const endpoint = splitHostPort(raw);
    if (!endpoint.ok) return endpoint;
    return buildFields("http", endpoint.host, endpoint.port, null, null);
  }
  if (parts.length >= 4 && /^\d+$/.test(parts[1] ?? "")) {
    const host = normalizeHost(parts[0] ?? "", false);
    if (!host.ok) return host;
    const port = parsePort(parts[1] ?? "");
    if (!port.ok) return port;
    const credentials = splitUserinfo(parts.slice(2).join(":"));
    if (!credentials.ok) return credentials;
    return buildFields(
      "http",
      host.host,
      port.port,
      credentials.username,
      credentials.password,
    );
  }
  return fail("ambiguous_format", "unrecognised proxy link format");
}

export function parseProxyUrl(input: string): ParseProxyUrlResult {
  if (typeof input !== "string" || input.trim().length === 0) {
    return fail("empty_input", "empty proxy url");
  }
  const raw = input.trim();
  if (raw.includes("://")) return parseUrlForm(raw);
  return parseSchemeless(raw);
}

/** Default proxy name: `host:port` (IPv6 bracketed). */
export function proxyDisplayName(fields: ParsedProxyFields): string {
  return `${formatHost(fields.host)}:${fields.port}`;
}

/** Link safe for display and state: no password, ever. */
export function redactedProxyUrl(fields: ParsedProxyFields): string {
  const host = formatHost(fields.host);
  if (fields.username !== null) {
    return `${fields.scheme}://${encodeUserinfo(fields.username)}@${host}:${fields.port}`;
  }
  return `${fields.scheme}://${host}:${fields.port}`;
}

/** Full link with percent-encoded credentials, for submit only. */
export function buildProxyUrl(fields: ParsedProxyFields): string {
  const host = formatHost(fields.host);
  if (fields.username !== null) {
    let userinfo = encodeUserinfo(fields.username);
    if (fields.password !== null) {
      userinfo += `:${encodeUserinfo(fields.password)}`;
    }
    return `${fields.scheme}://${userinfo}@${host}:${fields.port}`;
  }
  return `${fields.scheme}://${host}:${fields.port}`;
}
