// Port of backend/app/services/gst/india.py GSTIN checks (docs/06-gst.md §8).
const CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ";
const PATTERN = /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/;
const STATES = new Set([
  "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12", "13", "14", "15", "16", "17", "18", "19",
  "20", "21", "22", "23", "24", "26", "27", "29", "30", "31", "32", "33", "34", "35", "36", "37", "38", "97", "25", "28",
]);

function checkChar(first14: string): string {
  let total = 0;
  for (let i = 0; i < 14; i++) {
    const p = CHARS.indexOf(first14[i]) * (i % 2 === 0 ? 1 : 2);
    total += Math.floor(p / 36) + (p % 36);
  }
  return CHARS[(36 - (total % 36)) % 36];
}

export function isValidGstin(value: string): boolean {
  return PATTERN.test(value) && STATES.has(value.slice(0, 2)) && checkChar(value) === value[14];
}

/** Plain-language feedback while typing. */
export function gstinHint(raw: string): string | undefined {
  const v = raw.trim().toUpperCase();
  if (!v) return undefined;
  if (v.length < 15) return `${15 - v.length} more character${v.length === 14 ? "" : "s"}`;
  if (v.length > 15) return "A GSTIN has exactly 15 characters.";
  return isValidGstin(v) ? undefined : "This GSTIN doesn't look right. Check each character.";
}
