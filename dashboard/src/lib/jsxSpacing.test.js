// @vitest-environment node
/**
 * The build compiler (Next's SWC) drops the space after a `{value}` when the text that follows wraps onto the next
 * source line and contains an HTML entity such as &apos; ("From April {year} the pension ... OBR&apos;s" renders as
 * "From April 2030the pension"). Vitest's own transform does not have the bug, so the component tests cannot see it.
 *
 * This compiles every component with SWC twice, once as written and once with each entity replaced by the character
 * it stands for, and requires the two outputs to match. Where they differ, write the space as {" "}.
 */
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { beforeAll, describe, expect, it } from "vitest";

const ROOT = path.resolve(__dirname, "../..");
const DIRS = ["src/components", "app"];
const ENTITIES = { apos: "'", quot: '"', copy: "©", ldquo: "“", rdquo: "”", lsquo: "‘", rsquo: "’", ndash: "–",
  mdash: "—", pound: "£", plusmn: "±", nbsp: " ", hellip: "…", middot: "·", times: "×" };

const files = DIRS.flatMap((dir) =>
  readdirSync(path.join(ROOT, dir))
    .filter((f) => f.endsWith(".jsx") && !f.includes(".test."))
    .map((f) => path.join(dir, f)),
);

let swc;
beforeAll(async () => {
  swc = await import("next/dist/build/swc/index.js");
  await swc.loadBindings();
});

async function compile(source, filename) {
  const out = await swc.transform(source, {
    filename,
    jsc: { parser: { syntax: "ecmascript", jsx: true }, transform: { react: { runtime: "automatic" } } },
  });
  return out.code;
}

describe("JSX text compiles the same with and without HTML entities", () => {
  it("finds the components", () => {
    expect(files.length).toBeGreaterThan(10);
  });

  it.each(files)("%s", async (file) => {
    const source = readFileSync(path.join(ROOT, file), "utf8");
    const plain = source.replace(/&([a-z]+);/g, (m, name) => ENTITIES[name] ?? m);
    const [asWritten, decoded] = await Promise.all([compile(source, file), compile(plain, file)]);
    if (asWritten === decoded) return;
    const a = asWritten.split("\n");
    const b = decoded.split("\n");
    const diffs = a.map((line, i) => (line === b[i] ? null : `  as written: ${line.trim()}\n  expected:   ${b[i]?.trim()}`));
    expect.fail(`SWC drops a space in ${file}; write it as {" "}:\n${diffs.filter(Boolean).slice(0, 5).join("\n")}`);
  });

  it("catches the bug it guards against", async () => {
    const buggy = "export const A = ({ y }) => <p>\n  From April {y} the pension rises,\n  as the OBR&apos;s path.\n</p>;";
    const fixed = buggy.replace("{y} the", '{y}{" "}\n  the');
    const decode = (s) => s.replace("&apos;", "'");
    expect(await compile(buggy, "a.jsx")).not.toBe(await compile(decode(buggy), "a.jsx"));
    expect(await compile(fixed, "a.jsx")).toBe(await compile(decode(fixed), "a.jsx"));
  });
});
