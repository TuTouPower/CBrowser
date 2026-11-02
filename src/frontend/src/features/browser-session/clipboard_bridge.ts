/** Read-only clipboard permission probe; never reads or writes clipboard data. */

export type ClipboardPermissionState =
  | "granted"
  | "denied"
  | "prompt"
  | "unsupported";

interface PermissionLike {
  state: string;
  addEventListener?: (type: "change", listener: () => void) => void;
  removeEventListener?: (type: "change", listener: () => void) => void;
}

interface PermissionsLike {
  query?: (descriptor: { name: string }) => Promise<PermissionLike>;
}

export async function readClipboardPermission(): Promise<ClipboardPermissionState> {
  const permissions = (navigator as Navigator & { permissions?: PermissionsLike })
    .permissions;
  if (!permissions?.query) return "unsupported";
  try {
    const states = await Promise.all(
      ["clipboard-read", "clipboard-write"].map(
        async (name) => (await permissions.query!({ name })).state,
      ),
    );
    if (states.some((state) => state === "denied")) return "denied";
    if (states.some((state) => state === "prompt")) return "prompt";
    return "granted";
  } catch {
    return "unsupported";
  }
}


export async function watchClipboardPermission(
  onChange: (state: ClipboardPermissionState) => void,
): Promise<() => void> {
  const permissions = (navigator as Navigator & { permissions?: PermissionsLike })
    .permissions;
  if (!permissions?.query) {
    onChange("unsupported");
    return () => undefined;
  }
  try {
    const results = await Promise.all(
      ["clipboard-read", "clipboard-write"].map(
        async (name) => (await permissions.query!({ name })),
      ),
    );
    const emit = () => {
      const states = results.map((result) => result.state);
      if (states.some((state) => state === "denied")) onChange("denied");
      else if (states.some((state) => state === "prompt")) onChange("prompt");
      else onChange("granted");
    };
    emit();
    results.forEach((result) => result.addEventListener?.("change", emit));
    return () => {
      results.forEach((result) => result.removeEventListener?.("change", emit));
    };
  } catch {
    onChange("unsupported");
    return () => undefined;
  }
}
