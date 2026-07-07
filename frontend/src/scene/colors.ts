// Package identity lives on a single hue — the violet token (--violet: #a78bfa,
// ~hsl(255, 92%, 76%)). Packages are told apart by tint/shade (saturation and
// lightness steps around that anchor), never by a different hue, so cyan stays
// reserved for primary/selection and red for parse errors.
const VIOLET_HUE = 255;
const SATURATIONS = [45, 60, 75, 90];
const LIGHTNESSES = [50, 58, 66, 74, 82];

export function packageColor(pkg: string): string {
  let hash = 0;
  for (const ch of pkg) hash = (hash * 31 + ch.charCodeAt(0)) | 0;
  const h = Math.abs(hash);
  const s = SATURATIONS[h % SATURATIONS.length];
  const l = LIGHTNESSES[Math.floor(h / SATURATIONS.length) % LIGHTNESSES.length];
  // Comma syntax on purpose: THREE.Color.setStyle() only parses comma-separated
  // hsl(), and CSS accepts it too, so one string serves both surfaces.
  return `hsl(${VIOLET_HUE}, ${s}%, ${l}%)`;
}

// Same red as the --destructive token used by the PARSE ERROR badge and the
// analyze-screen error alert, so "red = parse error" is one literal app-wide.
export const ERROR_COLOR = '#f87171';
