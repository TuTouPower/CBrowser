import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const pkg = JSON.parse(
  readFileSync(join(here, "..", "package.json"), "utf8"),
);
const range = pkg.engines?.node;
if (!range) {
  console.error("package.json 缺少 engines.node 声明");
  process.exit(1);
}

// Only plain numeric major.minor.patch bounds are supported.  Unsupported
// range syntax must fail closed rather than silently accepting any Node.
const parse = (text) => {
  const parts = String(text).split(".");
  if (parts.length > 3 || parts.some((part) => !/^[0-9]+$/.test(part))) {
    return null;
  }
  const numbers = parts.map(Number);
  while (numbers.length < 3) numbers.push(0);
  return numbers;
};
const compare = (a, b) => {
  for (let i = 0; i < 3; i += 1) {
    if (a[i] !== b[i]) return a[i] < b[i] ? -1 : 1;
  }
  return 0;
};

const current = parse(process.versions.node);
if (current === null) {
  console.error(`无法解析当前 Node 版本：${process.versions.node}`);
  process.exit(1);
}

const min = />=?\s*([0-9]+(?:\.[0-9]+){0,2})/.exec(range);
const exclusiveMax = /<\s*([0-9]+(?:\.[0-9]+){0,2})/.exec(range);
const inclusiveMax = /<=\s*([0-9]+(?:\.[0-9]+){0,2})/.exec(range);
if (!min && !exclusiveMax && !inclusiveMax) {
  console.error(
    `engines.node="${range}" 不是受支持的数值范围（需 >=/>、< 或 <= 的纯数字边界）；拒绝放行`,
  );
  process.exit(1);
}

const bounds = [
  min && { op: ">=", value: parse(min[1]) },
  exclusiveMax && { op: "<", value: parse(exclusiveMax[1]) },
  inclusiveMax && { op: "<=", value: parse(inclusiveMax[1]) },
].filter(Boolean);
if (bounds.some((bound) => bound.value === null)) {
  console.error(`engines.node="${range}" 含无法解析的边界；拒绝放行`);
  process.exit(1);
}

const ok = bounds.every(({ op, value }) => {
  const cmp = compare(current, value);
  if (op === ">=") return cmp >= 0;
  if (op === "<") return cmp < 0;
  return cmp <= 0;
});

if (!ok) {
  console.error(
    `前端门禁 Node 版本不满足：当前 ${process.versions.node}，要求 engines.node="${range}"；` +
      `请切换到范围声明的 Node LTS（见 .mise.toml / mise install）。`,
  );
  process.exit(1);
}
console.log(`frontend node ok: ${process.versions.node} satisfies "${range}"`);
