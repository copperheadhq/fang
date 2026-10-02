// Expressive Code's settings that are code, not data: its plugins. Expressive
// Code passes the settings in astro.config.mjs on as serialised data, which a
// plugin, being functions, does not survive, so it reads plugins from here.
//
// Astro caches rendered pages in node_modules/.astro and does not notice a
// change to this file: after changing it, delete that folder before building,
// or the pages keep their old code blocks.
import { defineEcConfig } from "@astrojs/starlight/expressive-code";
import {
  pluginCollapsibleSections,
  pluginCollapsibleSectionsTexts,
} from "@expressive-code/plugin-collapsible-sections";

// A code block longer than this shows its first lines and folds the rest
// under a button that unrolls it: an example page quotes whole outputs, and a
// reader should not have to scroll past them to go on.
const SHOWN_LINES = 20;

// A docstring longer than this many lines keeps its first, the summary, and
// folds the rest.
const DOCSTRING_SHOWN = 1;

// The line ranges of a Python block's docstrings: every string that opens
// with triple quotes at the start of a line, to the line that closes it.
function docstrings(lines) {
  const found = [];
  for (let i = 0; i < lines.length; i++) {
    const text = lines[i].trim();
    const quote = text.match(/^[rRbBuU]?("""|\'\'\')/)?.[1];
    if (!quote) continue;
    const rest = text.slice(text.indexOf(quote) + 3);
    if (rest.includes(quote)) continue; // opens and closes on one line
    let end = i + 1;
    while (end < lines.length && !lines[end].includes(quote)) end++;
    found.push([i + 1, Math.min(end, lines.length - 1) + 1]); // 1-based
    i = end;
  }
  return found;
}

// Expressive Code's own collapsible sections do the folding; this only says
// which lines of each block to fold, so no page has to say so block by block.
// It runs before the plugin, which then reads the ranges as if the block's
// fence had given them.
//
// Python is quoted for its code, so its code is never folded: what folds is
// each long docstring, after its summary line. Any other long block shows its
// first SHOWN_LINES and folds the rest. A fold of only a few lines is not
// made: a button that hides two lines costs more than the two lines.
const foldLongBlocks = {
  name: "fold-long-blocks",
  hooks: {
    preprocessMetadata: ({ codeBlock }) => {
      if (codeBlock.props.collapse !== undefined) return;
      const lines = codeBlock.getLines().map((line) => line.text);
      if (codeBlock.language === "python" || codeBlock.language === "py") {
        const folds = docstrings(lines)
          .map(([start, end]) => [start + DOCSTRING_SHOWN, end])
          .filter(([from, to]) => to - from + 1 > 3);
        if (folds.length) codeBlock.props.collapse = folds.map(([f, t]) => `${f}-${t}`);
      } else if (lines.length > SHOWN_LINES + 3) {
        codeBlock.props.collapse = [`${SHOWN_LINES + 1}-${lines.length}`];
      }
    },
  },
};

// The fold's button says what pressing it does: "Show 98 more lines", not
// "98 collapsed lines".
pluginCollapsibleSectionsTexts.overrideTexts("en", {
  collapsedLines: "Show {lineCount} more {lineCount;1=line;lines}",
});

export default defineEcConfig({
  plugins: [foldLongBlocks, pluginCollapsibleSections()],
  // A fold at the end of a block is a bar at its foot; one in the middle, as
  // a docstring's is, is a bar where the lines were.
  defaultProps: { collapseStyle: "collapsible-auto" },
});
