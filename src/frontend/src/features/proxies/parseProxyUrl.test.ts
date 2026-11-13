import { describe, expect, it } from "vitest";
import {
  buildProxyUrl,
  parseProxyUrl,
  proxyDisplayName,
  redactedProxyUrl,
  type ParsedProxyFields,
} from "./parseProxyUrl";

/** Mirrors the backend matrix in tests/unit/test_t052_proxy_link.py. */
const validCases: Array<[input: string, expected: ParsedProxyFields]> = [
  [
    "http://user:p%40ss@proxy.example.com:8080",
    {
      scheme: "http",
      host: "proxy.example.com",
      port: 8080,
      username: "user",
      password: "p@ss",
    },
  ],
  [
    "socks5://proxy.example.com:1080",
    {
      scheme: "socks5",
      host: "proxy.example.com",
      port: 1080,
      username: null,
      password: null,
    },
  ],
  [
    "https://user@proxy.example.com:8443",
    {
      scheme: "https",
      host: "proxy.example.com",
      port: 8443,
      username: "user",
      password: null,
    },
  ],
  [
    "HTTP://PROXY.EXAMPLE.COM:8080",
    {
      scheme: "http",
      host: "proxy.example.com",
      port: 8080,
      username: null,
      password: null,
    },
  ],
  // Format 2: schemeless host:port defaults to http.
  [
    "proxy.example.com:8080",
    {
      scheme: "http",
      host: "proxy.example.com",
      port: 8080,
      username: null,
      password: null,
    },
  ],
  // Format 3: host:port:user:pass.
  [
    "proxy.example.com:8080:user:p:ss",
    {
      scheme: "http",
      host: "proxy.example.com",
      port: 8080,
      username: "user",
      password: "p:ss",
    },
  ],
  [
    "proxy.example.com:8080:user:p@ss",
    {
      scheme: "http",
      host: "proxy.example.com",
      port: 8080,
      username: "user",
      password: "p@ss",
    },
  ],
  // Format 4: user:pass@host:port.
  [
    "user@proxy.example.com:8080",
    {
      scheme: "http",
      host: "proxy.example.com",
      port: 8080,
      username: "user",
      password: null,
    },
  ],
  // test f006: format 4 with a percent-encoded password — mirrors the
  // backend matrix row `user:p%40ss@proxy.example.com:8080`.
  [
    "user:p%40ss@proxy.example.com:8080",
    {
      scheme: "http",
      host: "proxy.example.com",
      port: 8080,
      username: "user",
      password: "p@ss",
    },
  ],
  [
    "http://user:pass@[2001:db8::1]:8080",
    {
      scheme: "http",
      host: "2001:db8::1",
      port: 8080,
      username: "user",
      password: "pass",
    },
  ],
  [
    "[2001:db8::1]:8080",
    {
      scheme: "http",
      host: "2001:db8::1",
      port: 8080,
      username: null,
      password: null,
    },
  ],
  [
    "[2001:db8::1]:8080:user:pass",
    {
      scheme: "http",
      host: "2001:db8::1",
      port: 8080,
      username: "user",
      password: "pass",
    },
  ],
  [
    "user:pass@[2001:db8::1]:8080",
    {
      scheme: "http",
      host: "2001:db8::1",
      port: 8080,
      username: "user",
      password: "pass",
    },
  ],
  [
    "http://127.0.0.1:7890",
    {
      scheme: "http",
      host: "127.0.0.1",
      port: 7890,
      username: null,
      password: null,
    },
  ],
  [
    "http://user:pass@localhost:7890",
    {
      scheme: "http",
      host: "localhost",
      port: 7890,
      username: "user",
      password: "pass",
    },
  ],
  [
    "http://user:pass@[::1]:7890",
    {
      scheme: "http",
      host: "::1",
      port: 7890,
      username: "user",
      password: "pass",
    },
  ],
  [
    "http://host:8080/some/path?q=1#frag",
    {
      scheme: "http",
      host: "host",
      port: 8080,
      username: null,
      password: null,
    },
  ],
  [
    "http://u:p:q@host:8080",
    {
      scheme: "http",
      host: "host",
      port: 8080,
      username: "u",
      password: "p:q",
    },
  ],
  [
    "SOCKS5://U:P@HOST:1080",
    {
      scheme: "socks5",
      host: "host",
      port: 1080,
      username: "U",
      password: "P",
    },
  ],
  [
    "proxy.example.com:1",
    {
      scheme: "http",
      host: "proxy.example.com",
      port: 1,
      username: null,
      password: null,
    },
  ],
  [
    "proxy.example.com:65535",
    {
      scheme: "http",
      host: "proxy.example.com",
      port: 65535,
      username: null,
      password: null,
    },
  ],
  [
    "socks5://user%40domain:p%3Ass@host:1080",
    {
      scheme: "socks5",
      host: "host",
      port: 1080,
      username: "user@domain",
      password: "p:ss",
    },
  ],
  [
    "http://u%20x:p%3Az@host:1",
    {
      scheme: "http",
      host: "host",
      port: 1,
      username: "u x",
      password: "p:z",
    },
  ],
  [
    "socks5://user@[::1]:65535",
    {
      scheme: "socks5",
      host: "::1",
      port: 65535,
      username: "user",
      password: null,
    },
  ],
];

const invalidCases: Array<[input: string, code: string]> = [
  ["", "empty_input"],
  ["   ", "empty_input"],
  ["http://", "missing_host"],
  ["http://:8080", "missing_host"],
  ["http://host", "missing_port"],
  ["http://user:pass@host", "missing_port"],
  ["http://host:0", "port_out_of_range"],
  ["http://host:65536", "port_out_of_range"],
  ["http://host:99999", "port_out_of_range"],
  ["http://host:abc", "invalid_port"],
  ["http://host:80a", "invalid_port"],
  ["http://host:-1", "invalid_port"],
  ["ftp://host:8080", "unsupported_scheme"],
  ["socks5://user%ZZ@host:1080", "malformed_percent_encoding"],
  ["http://u%@host:8080", "malformed_percent_encoding"],
  ["http://a@b@host:8080", "multiple_at_signs"],
  ["http://u@@host:8080", "multiple_at_signs"],
  ["http://[2001:db8::1:8080", "unclosed_ipv6_bracket"],
  ["http://[::1]", "missing_port"],
  ["http://ho st:8080", "invalid_host"],
  ["http://2001:db8::1:8080", "invalid_host"],
  ["2001:db8::1:8080", "ambiguous_format"],
  ["a:b:c", "ambiguous_format"],
  ["host:8080:user", "ambiguous_format"],
  ["http://:pass@host:8080", "invalid_credentials"],
  ["host:8080::pass", "invalid_credentials"],
];

describe("parseProxyUrl", () => {
  it.each(validCases)("parses %s", (input, expected) => {
    expect(parseProxyUrl(input)).toEqual({ ok: true, fields: expected });
  });

  it.each(invalidCases)("rejects %s with %s", (input, code) => {
    const result = parseProxyUrl(input);
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.code).toBe(code);
      expect(typeof result.error).toBe("string");
      expect(result.error.length).toBeGreaterThan(0);
    }
  });

  it("strips IPv6 brackets so host matches the plain form field value", () => {
    const result = parseProxyUrl("socks5://u:p@[2001:db8::1]:1080");
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.fields.host).toBe("2001:db8::1");
      expect(result.fields.host.startsWith("[")).toBe(false);
    }
  });

  it("compresses a non-canonical IPv6 host like the backend", () => {
    const result = parseProxyUrl(
      "http://user:pass@[2001:0DB8:0000:0000:0000:0000:0000:0001]:8080",
    );
    expect(result.ok).toBe(true);
    if (result.ok) expect(result.fields.host).toBe("2001:db8::1");
  });

  it("round-trips a full link through buildProxyUrl", () => {
    const result = parseProxyUrl("socks5://user:p%40ss:word@[2001:db8::1]:1080");
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(buildProxyUrl(result.fields)).toBe(
        "socks5://user:p%40ss%3Aword@[2001:db8::1]:1080",
      );
      expect(redactedProxyUrl(result.fields)).toBe(
        "socks5://user@[2001:db8::1]:1080",
      );
      expect(proxyDisplayName(result.fields)).toBe("[2001:db8::1]:1080");
    }
  });

  it("redacted link never contains the password", () => {
    const result = parseProxyUrl("http://user:s3cret@proxy.example.com:8080");
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(redactedProxyUrl(result.fields)).toBe(
        "http://user@proxy.example.com:8080",
      );
      expect(redactedProxyUrl(result.fields)).not.toContain("s3cret");
      expect(proxyDisplayName(result.fields)).toBe("proxy.example.com:8080");
    }
  });

  it("builds a schemeless link with the http default", () => {
    const result = parseProxyUrl("proxy.example.com:8080");
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(buildProxyUrl(result.fields)).toBe("http://proxy.example.com:8080");
    }
  });
});
