import { describe, expect, it } from "vitest";
import {
  classifyProfileField,
  diffProfileValues,
  hasRuntimeConfigChange,
} from "./profile_field_diff";
import {
  DEFAULT_PROFILE_CREATE_VALUES,
  type ProfileCreateRequest,
} from "../../shared/api/types";

// t058 A24: edit submits only the fields that differ from the initial
// values, and the field classification comes from the backend-generated
// module — `capture_preview` is instant, not runtime.
function baseValues(
  overrides: Partial<ProfileCreateRequest> = {},
): ProfileCreateRequest {
  return {
    name: "Original",
    ...DEFAULT_PROFILE_CREATE_VALUES,
    ...overrides,
  };
}

describe("profile_field_diff (t058 A24)", () => {
  it("classifies capture_preview as instant, matching the backend", () => {
    expect(classifyProfileField("capture_preview")).toBe("instant");
    expect(classifyProfileField("name")).toBe("metadata");
    expect(classifyProfileField("timezone")).toBe("runtime");
    expect(classifyProfileField("group_id")).toBe("metadata");
    expect(classifyProfileField("no_such_field")).toBeNull();
  });

  it("returns an empty diff when nothing changed", () => {
    expect(diffProfileValues(baseValues(), baseValues())).toEqual({});
  });

  it("returns only the changed timezone when only the timezone changes", () => {
    const diff = diffProfileValues(
      baseValues({ timezone: "America/New_York" }),
      baseValues({ timezone: "Europe/London" }),
    );
    expect(diff).toEqual({ timezone: "America/New_York" });
  });

  it("keeps linked fields together: timezone plus its locale change", () => {
    const diff = diffProfileValues(
      baseValues({ timezone: "Asia/Shanghai", locale: "zh-CN" }),
      baseValues({ timezone: "Europe/London", locale: "en-US" }),
    );
    expect(diff).toEqual({ timezone: "Asia/Shanghai", locale: "zh-CN" });
  });

  it("compares array fields by value, not by identity", () => {
    expect(
      diffProfileValues(
        baseValues({ launch_args: ["--a"] }),
        baseValues({ launch_args: ["--a"] }),
      ),
    ).toEqual({});
    expect(
      diffProfileValues(
        baseValues({ launch_args: ["--a", "--b"] }),
        baseValues({ launch_args: ["--a"] }),
      ),
    ).toEqual({ launch_args: ["--a", "--b"] });
  });

  it("does not count a metadata-only change as a runtime change", () => {
    expect(
      hasRuntimeConfigChange(
        baseValues({ notes: "a note" }),
        baseValues(),
      ),
    ).toBe(false);
  });

  it("counts a runtime field change as a runtime change", () => {
    expect(
      hasRuntimeConfigChange(
        baseValues({ timezone: "Asia/Shanghai" }),
        baseValues({ timezone: "Europe/London" }),
      ),
    ).toBe(true);
  });

  it("does not count an instant-only change as a runtime change", () => {
    expect(
      hasRuntimeConfigChange(
        baseValues({ capture_preview: false }),
        baseValues({ capture_preview: true }),
      ),
    ).toBe(false);
  });
});
