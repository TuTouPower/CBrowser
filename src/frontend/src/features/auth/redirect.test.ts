import { describe, expect, it } from "vitest";
import { loginRedirectPath, sanitizeNextPath } from "./redirect";

describe("sanitizeNextPath login loop variants", () => {
  it.each([
    "/login",
    "/LOGIN",
    "/Login",
    "/lOgIn",
    "/login/",
    "/login//",
    "/LOGIN/",
    "/login?next=/settings",
    "/login?next=%2Fsettings",
    "/login#section",
    "/login/?next=/settings#top",
  ])("rejects login variant %s", (target) => {
    expect(sanitizeNextPath(target)).toBeNull();
  });

  it.each([
    "/",
    "/settings",
    "/?profileId=p1",
    "/profiles/p1",
    "/profiles/p1/files",
    "/loginx",
    "/logins",
    "/foo/login",
  ])("allows legitimate target %s", (target) => {
    expect(sanitizeNextPath(target)).toBe(target);
  });

  it("still rejects open-redirect shapes", () => {
    for (const target of [
      "//evil.example",
      "///evil.example",
      "/\\evil.example",
      "\\\\evil.example",
      "https://evil.example",
      "javascript:alert(1)",
      "",
      "settings",
    ]) {
      expect(sanitizeNextPath(target)).toBeNull();
    }
    expect(sanitizeNextPath(null)).toBeNull();
    expect(sanitizeNextPath(undefined)).toBeNull();
  });
});

describe("loginRedirectPath", () => {
  it("never builds a self-referential next for login variants", () => {
    for (const pathname of ["/login", "/LOGIN", "/login/"]) {
      expect(loginRedirectPath({ pathname, search: "" })).toBe("/login");
      expect(loginRedirectPath({ pathname, search: "?next=/settings" })).toBe(
        "/login",
      );
    }
  });

  it("preserves legitimate targets", () => {
    expect(loginRedirectPath({ pathname: "/", search: "?profileId=p1" })).toBe(
      "/login?next=%2F%3FprofileId%3Dp1",
    );
    expect(loginRedirectPath({ pathname: "/settings", search: "" })).toBe(
      "/login?next=%2Fsettings",
    );
  });
});
