// Greps frontend/src for patterns DESIGN.md forbids. Run: npm run lint:design
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const root = new URL("../src/", import.meta.url).pathname;

/** [pattern, why, optional predicate that exempts a matching line] */
const rules = [
  [/border-l-4/, "colored left stripe"],
  [/\bshadow-(sm|md)\b|hover:shadow/, "shadow on a non-floating element"],
  [/uppercase tracking/, "uppercase letter-spaced label"],
  [/\btext-\[/, "arbitrary text size; use the type scale"],
  [/\bfont-bold\b/, "700 weight isn't loaded; use font-semibold"],
  [/\b(blue|purple|indigo|violet|sky|cyan|green)-\d/, "hue outside the palette"],
  [/#[0-9a-fA-F]{6}\b/, "hex color in a component; use a token"],
  [/\brounded-(xl|2xl|3xl|md|sm)\b/, "radius outside the scale"],
  [/\boutline-none\b/, "focus outline removed", (line) => /focus:ring/.test(line)],
  [/[▼▶▲✓✕⚠☀☾◐]|&times;/, "Unicode symbol used as an icon"],
];

function* files(dir) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) yield* files(path);
    else if (/\.(tsx?|css)$/.test(name)) yield path;
  }
}

let problems = 0;
for (const path of files(root)) {
  // Tokens are defined in global.css, so literal values are expected there.
  if (path.endsWith("global.css")) continue;
  readFileSync(path, "utf8").split("\n").forEach((line, i) => {
    for (const [pattern, why, exempt] of rules) {
      if (pattern.test(line) && !exempt?.(line)) {
        console.log(`${relative(root, path)}:${i + 1}  ${why}\n    ${line.trim()}`);
        problems++;
      }
    }
  });
}

if (problems) {
  console.log(`\n${problems} design problem${problems === 1 ? "" : "s"} (see src/olly/dashboard/DESIGN.md)`);
  process.exit(1);
}
console.log("design lint: clean");
