// ESC/POS raster printing, ported from PlantBill (frontend/src/lib/escposRaster.ts + Android RasterEscPos).
// Everything prints as an image (GS v 0): cheap printers only have ASCII in ROM, so ₹ and Indic
// scripts must be drawn on a canvas and sent as dots (docs/07-pos-billing.md §7).

export const DOTS_58MM = 384;
export const DOTS_80MM = 576;
export const INIT = new Uint8Array([0x1b, 0x40]);
export const CUT = new Uint8Array([0x1d, 0x56, 0x42, 0x00]);
export const FEED = new Uint8Array([0x0a, 0x0a, 0x0a, 0x0a]);
const THRESHOLD = 128;

export function concat(parts: Uint8Array[]): Uint8Array {
  const out = new Uint8Array(parts.reduce((n, p) => n + p.length, 0));
  let o = 0;
  for (const p of parts) { out.set(p, o); o += p.length; }
  return out;
}

/** Pack 1-bit pixels (1 = burn) into GS v 0 commands, split into bands so no single command overflows the buffer. */
export function packRaster(mono: Uint8Array, width: number, height: number, bandRows = 128): Uint8Array {
  if (mono.length !== width * height) throw new Error("mono size mismatch");
  const bytesPerRow = (width + 7) >> 3;
  const parts: Uint8Array[] = [];
  for (let row = 0; row < height; row += bandRows) {
    const rows = Math.min(bandRows, height - row);
    const band = new Uint8Array(8 + bytesPerRow * rows);
    band.set([0x1d, 0x76, 0x30, 0x00, bytesPerRow & 0xff, (bytesPerRow >> 8) & 0xff, rows & 0xff, (rows >> 8) & 0xff]);
    for (let r = 0; r < rows; r++) {
      for (let x = 0; x < width; x++) {
        if (mono[(row + r) * width + x]) band[8 + r * bytesPerRow + (x >> 3)] |= 0x80 >> (x & 7);
      }
    }
    parts.push(band);
  }
  return concat(parts);
}

/** Floyd–Steinberg dither of RGBA (composited onto white) to 1-bit; keeps logos and gradients legible. */
export function ditherToMono(rgba: Uint8ClampedArray, width: number, height: number, dither = true): Uint8Array {
  const grey = new Float32Array(width * height);
  for (let i = 0; i < grey.length; i++) {
    const a = rgba[i * 4 + 3] / 255;
    grey[i] = (0.299 * rgba[i * 4] + 0.587 * rgba[i * 4 + 1] + 0.114 * rgba[i * 4 + 2]) * a + 255 * (1 - a);
  }
  const mono = new Uint8Array(width * height);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const i = y * width + x;
      const next = grey[i] < THRESHOLD ? 0 : 255;
      mono[i] = next === 0 ? 1 : 0;
      if (!dither) continue;
      const err = grey[i] - next;
      if (x + 1 < width) grey[i + 1] += (err * 7) / 16;
      if (y + 1 < height) {
        if (x > 0) grey[i + width - 1] += (err * 3) / 16;
        grey[i + width] += (err * 5) / 16;
        if (x + 1 < width) grey[i + width + 1] += err / 16;
      }
    }
  }
  return mono;
}

/** Text is thresholded (crisp), photos/logos are dithered. */
export function canvasToRaster(canvas: HTMLCanvasElement, dither = false): Uint8Array {
  const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
  const { data } = ctx.getImageData(0, 0, canvas.width, canvas.height);
  return packRaster(ditherToMono(data, canvas.width, canvas.height, dither), canvas.width, canvas.height);
}

/**
 * Draw a logo URL into `ctx` at (x, y) fitting maxW × maxH. Returns the height used, or 0 if it
 * can't load: a missing logo must never stop a bill from printing.
 */
export async function drawLogo(ctx: CanvasRenderingContext2D, url: string, x: number, y: number, maxW: number, maxH: number): Promise<number> {
  const img = await new Promise<HTMLImageElement | null>((resolve) => {
    const el = new Image();
    el.crossOrigin = "anonymous"; // the logo is served from the API host; avoids a tainted canvas
    el.onload = () => resolve(el);
    el.onerror = () => resolve(null);
    el.src = url + (url.includes("?") ? "&" : "?") + "cors=1"; // separate cache key from the on-screen <img>
  });
  if (!img?.width) return 0;
  const scale = Math.min(maxW / img.width, maxH / img.height, 1);
  const w = img.width * scale, h = img.height * scale;
  ctx.drawImage(img, x + (maxW - w) / 2, y, w, h);
  return h;
}

/** A test page that proves the printer, the paper width, the ₹ sign and Indic scripts all work. */
export async function testPage(dots: number, connection: string, logoUrl?: string | null): Promise<Uint8Array> {
  const canvas = document.createElement("canvas");
  canvas.width = dots;
  canvas.height = 420;
  const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, dots, canvas.height);
  ctx.fillStyle = "#000";
  ctx.textAlign = "center";
  let y = 8;
  if (logoUrl) y += (await drawLogo(ctx, logoUrl, 0, y, dots, 120)) + 8;
  const line = (text: string, size: number, weight = 400) => {
    ctx.font = `${weight} ${size}px Inter, "Noto Sans", "Noto Sans Devanagari", "Noto Sans Malayalam", sans-serif`;
    y += size + 6;
    ctx.fillText(text, dots / 2, y);
  };
  line("TEST PRINT", 36, 800);
  line("Anylo printer is working", 22);
  line(`Connection: ${connection}`, 20);
  line(`Paper: ${dots === DOTS_80MM ? "80 mm" : "58 mm"} (${dots} dots)`, 20);
  line("₹1,25,450.75", 30, 700);
  line("नमस्ते · നന്ദി · நன்றி · ಧನ್ಯವಾದ", 22);
  line(new Date().toLocaleString("en-IN"), 18);
  ctx.fillRect(0, y + 12, dots, 3); // full-width bar shows whether the width setting matches the head
  const cropped = document.createElement("canvas");
  cropped.width = dots;
  cropped.height = y + 24;
  cropped.getContext("2d")!.drawImage(canvas, 0, 0);
  return canvasToRaster(cropped);
}
