// Drafts one schematic with copperhead's engine, for draw.py.
//
//   npx tsx draft.mts <copperhead checkout> <directory> <stem>
//
// The directory holds `schematic.intent.json`; the sheet is written beside it
// as `<stem>.kicad_sch`. Run from inside the copperhead checkout, so its own
// dependencies resolve. A refusal prints the engine's findings and exits 1.

import { writeFile } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

const [checkout, dir, stem] = process.argv.slice(2);
const { draftSchematicToText } = await import(
  pathToFileURL(path.join(checkout, "src", "kicad", "draft", "draft.ts")).href
);

const res = await draftSchematicToText({
  repoRoot: dir,
  schematic: `${stem}.kicad_sch`,
  intentPath: "schematic.intent.json",
  docsDir: null,
  symbolDirs: [process.env.KICAD_SYMBOL_DIR ?? "/usr/share/kicad/symbols"],
});
if (!res.ok) {
  console.error(res.findings.map((f: { detail: string }) => f.detail).join("\n"));
  process.exit(1);
}
await writeFile(path.join(dir, `${stem}.kicad_sch`), res.text, "utf8");
