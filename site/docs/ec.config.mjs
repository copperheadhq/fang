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
// under a button that unrolls it: an example page quotes whole programs and
// whole outputs, and a reader should not have to scroll past them to go on.
const SHOWN_LINES = 20;

// Expressive Code's own collapsible sections do the folding; this only says
// which lines of each long block to fold, the ones after the first
// SHOWN_LINES, so no page has to say so block by block. It runs before the
// plugin, which then reads the range as if the block's fence had given it. A
// block only a few lines over is left whole: a button that hides two lines
// costs more than the two lines.
const foldLongBlocks = {
  name: "fold-long-blocks",
  hooks: {
    preprocessMetadata: ({ codeBlock }) => {
      const lines = codeBlock.getLines().length;
      if (lines > SHOWN_LINES + 3 && codeBlock.props.collapse === undefined) {
        codeBlock.props.collapse = [`${SHOWN_LINES + 1}-${lines}`];
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
  defaultProps: { collapseStyle: "collapsible-end" },
});
