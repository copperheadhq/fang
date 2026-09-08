import type { AstroIntegration } from "astro";
import type { StarlightPlugin } from "@astrojs/starlight/types";

/**
 * The copperhead theme for Starlight.
 *
 * Carries the whole identity, not only the palette: the token overrides, the
 * self-hosted faces, the component overrides the stylesheet expects, and the
 * code-block styling. A consuming site states what is its own — title, sidebar,
 * links — and nothing about how it looks.
 */

export interface CopperheadThemeOptions {
  /**
   * Repository URL behind the sidebar's release pill. Defaults to the `github`
   * entry in the site's `social` config, so most sites need not set it.
   * Pass `false` to drop the pill.
   */
  repo?: string | false;

  /**
   * Version shown in the pill, without a leading `v`. Omit it and the pill
   * links to the latest release and reads "releases" instead — which is the
   * right choice for a project whose version has a single source of truth
   * elsewhere, since a literal here would be a second one.
   */
  version?: string;

  /** SPDX identifier shown beside the version. Defaults to `Apache-2.0`. */
  license?: string;

  /**
   * Set `false` to keep your own components and take only the stylesheet.
   * The theme styles these components by name, so expect it to look wrong.
   */
  components?: boolean;

  /** Set `false` to leave `expressiveCode` alone. */
  codeBlocks?: boolean;
}

/**
 * The faces the theme sets. They are peer dependencies rather than
 * dependencies: Starlight resolves `customCss` specifiers from the consuming
 * site's root, so that is where they have to be installed. npm 7+ does it
 * automatically.
 */
const FACES = [
  "@fontsource-variable/inter",
  "@fontsource/ibm-plex-mono/400.css",
  "@fontsource/ibm-plex-mono/500.css",
];

/** The components the stylesheet expects to exist. */
const THEME_COMPONENTS = {
  Header: "@copperhead/starlight-theme/components/Header.astro",
  Sidebar: "@copperhead/starlight-theme/components/Sidebar.astro",
  PageTitle: "@copperhead/starlight-theme/components/PageTitle.astro",
  ThemeSelect: "@copperhead/starlight-theme/components/ThemeSelect.astro",
  Footer: "@copperhead/starlight-theme/components/Footer.astro",
} as const;

/** Starlight fills unset overrides with paths under this prefix. */
const STARLIGHT_DEFAULT = "@astrojs/starlight/components/";

const VIRTUAL_ID = "virtual:copperhead-theme/options";
const RESOLVED_ID = `\0${VIRTUAL_ID}`;

interface ResolvedOptions {
  repo: string | null;
  version: string | null;
  license: string;
}

/**
 * Publishes the resolved options to the components as a virtual module. A
 * Starlight plugin runs at config time and components render later, so a
 * module is how a value reaches them.
 */
function optionsModule(options: ResolvedOptions): AstroIntegration {
  const source = `export default ${JSON.stringify(options)};`;
  return {
    name: "@copperhead/starlight-theme/options",
    hooks: {
      "astro:config:setup": ({ updateConfig }) => {
        updateConfig({
          vite: {
            plugins: [
              {
                name: "copperhead-theme-options",
                resolveId: (id: string) =>
                  id === VIRTUAL_ID ? RESOLVED_ID : undefined,
                load: (id: string) => (id === RESOLVED_ID ? source : undefined),
              },
            ],
          },
        });
      },
    },
  };
}

export default function copperheadTheme(
  options: CopperheadThemeOptions = {},
): StarlightPlugin {
  return {
    name: "@copperhead/starlight-theme",
    hooks: {
      "config:setup"({ config, updateConfig, addIntegration, logger }) {
        const github = config.social?.find((link) => link.icon === "github");
        const repo =
          options.repo === false ? null : (options.repo ?? github?.href ?? null);

        if (options.repo === undefined && !github) {
          logger.info(
            "No `github` social link found, so the sidebar release pill is " +
              "hidden. Pass `repo` to show it.",
          );
        }

        addIntegration(
          optionsModule({
            repo,
            version: options.version ?? null,
            license: options.license ?? "Apache-2.0",
          }),
        );

        // The site's own stylesheets load last, so a site can still override a
        // token without editing the theme.
        const customCss = [
          ...FACES,
          "@copperhead/starlight-theme/styles/theme.css",
          ...(config.customCss ?? []),
        ];

        // Claim a component only where the site has not overridden it: an
        // explicit override in the consuming site should win over the theme's.
        const components = { ...config.components };
        if (options.components !== false) {
          for (const [name, path] of Object.entries(THEME_COMPONENTS)) {
            const current = components[name as keyof typeof components];
            if (!current || current.startsWith(STARLIGHT_DEFAULT)) {
              components[name as keyof typeof components] = path;
            } else {
              logger.info(`Keeping the site's own ${name} override.`);
            }
          }
        }

        updateConfig({
          customCss,
          components,
          ...(options.codeBlocks === false
            ? {}
            : { expressiveCode: mergeCodeBlocks(config.expressiveCode) }),
        });
      },
    },
  };
}

/** Code-block styling, without discarding what the site set itself. */
function mergeCodeBlocks(existing: unknown) {
  const theme = {
    // Long lines wrap rather than scroll: commands and prompts are prose-like
    // and were being cut off on phones.
    defaultProps: { wrap: true, preserveIndent: true },
    styleOverrides: {
      borderRadius: "0.75rem",
      codeFontFamily:
        "'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
      codeFontSize: "0.875rem",
      codeLineHeight: "1.65",
      codePaddingBlock: "0.875rem",
      codePaddingInline: "1rem",
      frames: { shadowColor: "transparent", frameBoxShadowCssValue: "none" },
    },
  };

  if (existing === false) return false;
  if (!existing || existing === true) return theme;

  const site = existing as Record<string, any>;
  return {
    ...site,
    defaultProps: { ...theme.defaultProps, ...(site.defaultProps ?? {}) },
    styleOverrides: {
      ...theme.styleOverrides,
      ...(site.styleOverrides ?? {}),
      frames: {
        ...theme.styleOverrides.frames,
        ...(site.styleOverrides?.frames ?? {}),
      },
    },
  };
}
