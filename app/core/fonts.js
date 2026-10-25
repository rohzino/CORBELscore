// Fonts that ship with CORBELscore, so a graphic looks the same on every
// computer and in every browser source. The window, the designer and the
// on-air pages all load them from /fonts/.

export const BUNDLED_FONTS = [
  { family: "Red Hat Display", file: "RedHatDisplay.ttf", italic: "RedHatDisplay-Italic.ttf", weights: "300 900", note: "Headlines and numbers" },
  { family: "Red Hat Text", file: "RedHatText.ttf", italic: "RedHatText-Italic.ttf", weights: "300 700", note: "Names and small text" },
  { family: "Red Hat Mono", file: "RedHatMono.ttf", weights: "300 700", note: "Even-width digits" },
  { family: "Archivo", file: "Archivo.ttf", italic: "Archivo-Italic.ttf", weights: "100 900", stretch: "62% 125%", note: "TeleScore's original face" },
];

// The default face for new graphics.
export const DISPLAY_FONT = "Red Hat Display";

export function fontFaceCss(base = "/fonts/") {
  return BUNDLED_FONTS.flatMap((f) => [
    `@font-face{font-family:"${f.family}";src:url(${base}${f.file}) format("truetype");font-weight:${f.weights};${f.stretch ? `font-stretch:${f.stretch};` : ""}font-display:block}`,
    f.italic ? `@font-face{font-family:"${f.family}";src:url(${base}${f.italic}) format("truetype");font-weight:${f.weights};font-style:italic;font-display:block}` : "",
  ]).filter(Boolean).join("\n");
}

// A CSS font stack that always ends in a face we ship.
export const fontStack = (family) => `"${String(family || DISPLAY_FONT).replace(/"/g, "")}", "${DISPLAY_FONT}", "Helvetica Neue", Arial, sans-serif`;
