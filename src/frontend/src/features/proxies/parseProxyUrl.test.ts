import { describe, expect, it } from "vitest";
import { parseProxyUrl, type ParsedProxyFields } from "./parseProxyUrl";

const validCases: Array<[url: string, expected: ParsedProxyFields]> = [
  [
    "http://user:pass@proxy.example.com:8080",
    {
      scheme: "http",
      host: "proxy.example.com",
      port: 8080,
      username: "user",
      password: "pass",
    },
  ],
  [
    "socks5://u:p@[2001:db8::1]:1080",
    {
      scheme: "socks5",
      host: "2001:db8::1",
      port: 1080,
      username: "u",
      password: "p",
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
    "https://host:443",
    {
      scheme: "https",
      host: "host",
      port: 443,
      username: "",
      password: "",
    },
  ],
  [
    "HTTP://user:pass@proxy.example.com:8080",
    {
      scheme: "http",
      host: "proxy.example.com",
      port: 8080,
      username: "user",
      password: "pass",
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
      password: "",
    },
  ],
  [
    "http://host:8080/some/path?q=1#frag",
    {
      scheme: "http",
      host: "host",
      port: 8080,
      username: "",
      password: "",
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
      host: "HOST",
      port: 1080,
      username: "U",
      password: "P",
    },
  ],
];

const invalidUrls: string[] = [
  "",
  "   ",
  "proxy.example.com:8080",
  "http://",
  "http://:8080",
  "http://host",
  "http://user:pass@host",
  "http://host:0",
  "http://host:65536",
  "http://host:99999",
  "http://host:abc",
  "http://host:80a",
  "http://host:-1",
  "ftp://host:8080",
  "socks5://user%ZZ@host:1080",
  "http://u%@host:8080",
  "http://a@b@host:8080",
  "http://u@@host:8080",
  "http://[2001:db8::1:8080",
  "http://[::1]",
  "http://ho st:8080",
  "http://2001:db8::1:8080",
];

describe("parseProxyUrl", () => {
  it.each(validCases)("parses %s", (url, expected) => {
    expect(parseProxyUrl(url)).toEqual({ ok: true, fields: expected });
  });

  it("strips IPv6 brackets so host matches the plain form field value", () => {
    const result = parseProxyUrl("socks5://u:p@[2001:db8::1]:1080");
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.fields.host).toBe("2001:db8::1");
      expect(result.fields.host.startsWith("[")).toBe(false);
    }
  });

  it.each(invalidUrls)("rejects %s", (url) => {
    const result = parseProxyUrl(url);
    expect(result.ok).toBe(false);
    expect("fields" in result).toBe(false);
    expect(Object.keys(result).sort()).toEqual(["error", "ok"]);
    if (!result.ok) {
      expect(typeof result.error).toBe("string");
      expect(result.error.length).toBeGreaterThan(0);
    }
  });
});
