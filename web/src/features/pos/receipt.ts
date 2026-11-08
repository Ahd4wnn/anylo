// Draws the server's receipt model onto a canvas sized to the printer head, then encodes it as raster ESC/POS.
// Same model as Android/iOS, so receipts look identical everywhere (docs/07-pos-billing.md §7).
import { canvasToRaster, drawLogo } from "@/features/printer/escpos";
import type { Receipt } from "./api";

const FONT = 'Inter, "Noto Sans", "Noto Sans Devanagari", "Noto Sans Malayalam", "Noto Sans Tamil", "Noto Sans Kannada", sans-serif';
const money = (v: string | number) => Number(v).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const qty = (v: string) => Number(v).toLocaleString("en-IN", { maximumFractionDigits: 3 });

export async function receiptRaster(r: Receipt, dots: number): Promise<Uint8Array> {
  const scale = dots / 384; // design for 58 mm, scale up for 80 mm
  const canvas = document.createElement("canvas");
  canvas.width = dots;
  canvas.height = 4000;
  const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, dots, canvas.height);
  ctx.fillStyle = "#000";
  const pad = Math.round(6 * scale);
  let y = pad;
  const font = (px: number, weight = 400) => { ctx.font = `${weight} ${Math.round(px * scale)}px ${FONT}`; return Math.round(px * scale); };
  const text = (s: string, px: number, opts: { weight?: number; align?: CanvasTextAlign; x?: number } = {}) => {
    const h = font(px, opts.weight);
    ctx.textAlign = opts.align ?? "left";
    const x = opts.x ?? (opts.align === "center" ? dots / 2 : opts.align === "right" ? dots - pad : pad);
    y += h + Math.round(4 * scale);
    ctx.fillText(s, x, y);
  };
  const wrap = (s: string, px: number, weight = 400, maxW = dots - 2 * pad) => {
    font(px, weight);
    const words = s.split(" ");
    let line = "";
    for (const w of words) {
      if (ctx.measureText(`${line} ${w}`).width > maxW && line) { text(line, px, { weight, align: "center" }); line = w; }
      else line = line ? `${line} ${w}` : w;
    }
    if (line) text(line, px, { weight, align: "center" });
  };
  const row = (left: string, right: string, px = 20, weight = 400) => {
    const h = font(px, weight);
    y += h + Math.round(4 * scale);
    ctx.textAlign = "left"; ctx.fillText(left, pad, y);
    ctx.textAlign = "right"; ctx.fillText(right, dots - pad, y);
  };
  const rule = () => { y += Math.round(6 * scale); ctx.fillRect(pad, y, dots - 2 * pad, Math.max(1, Math.round(2 * scale))); y += Math.round(2 * scale); };

  if (r.shop.logo_url) y += (await drawLogo(ctx, r.shop.logo_url, 0, y, dots, Math.round(90 * scale))) + pad;
  wrap(r.shop.name, 28, 800);
  if (r.shop.address) wrap(r.shop.address, 18);
  if (r.shop.gstin) text(`GSTIN: ${r.shop.gstin}`, 18, { align: "center" });
  if (r.shop.phone) text(`Ph: ${r.shop.phone}`, 18, { align: "center" });
  if (r.composition_note) wrap(r.composition_note, 16);
  text(r.status === "cancelled" ? `${r.title} · CANCELLED` : r.title, 22, { weight: 700, align: "center" });
  row(r.number, new Date(r.issued_at).toLocaleString("en-IN", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }), 18);
  if (r.buyer) {
    row(`Bill to: ${r.buyer.name ?? "Customer"}`, r.buyer.phone ?? "", 18);
    if (r.buyer.gstin) text(`GSTIN: ${r.buyer.gstin}`, 18);
  }
  if (r.tax_summary.length) row(`POS: ${r.place_of_supply}`, `Rev. charge: ${r.reverse_charge}`, 16);
  rule();
  row("Item", "Amount", 18, 700);
  for (const l of r.lines) {
    font(20, 600);
    const name = l.variant_name ? `${l.name} (${l.variant_name})` : l.name;
    text(name, 20, { weight: 600 });
    row(`  ${qty(l.qty)} ${l.unit} × ${money(l.unit_price)}${l.hsn ? `  HSN ${l.hsn}` : ""}${r.tax_summary.length ? `  ${Number(l.tax_rate)}%` : ""}`, money(l.line_total), 18);
    if (Number(l.discount) > 0) row("  Discount", `−${money(l.discount)}`, 16);
  }
  rule();
  const t = r.totals;
  if (Number(t.discount_total) > 0) row("Discount", `−${money(t.discount_total)}`);
  if (r.tax_summary.length) {
    row("Taxable value", money(t.taxable_total));
    if (r.supply_type === "inter") row("IGST", money(t.igst_total));
    else { row("CGST", money(t.cgst_total)); row(r.state_tax_label, money(t.sgst_total)); }
    if (Number(t.cess_total)) row("Cess", money(t.cess_total));
  }
  if (Number(t.round_off)) row("Round off", money(t.round_off));
  row("TOTAL", `₹${money(t.grand_total)}`, 30, 800);
  wrap(r.amount_in_words, 16);
  for (const p of r.payments) row(`Paid · ${p.method.toUpperCase()}`, money(p.amount), 18);
  if (Number(t.due_total) > 0) row("Balance due", `₹${money(t.due_total)}`, 22, 700);
  if (r.tax_summary.length > 0) {
    rule();
    row("GST%  Taxable", r.supply_type === "inter" ? "IGST" : `CGST / ${r.state_tax_label}`, 16, 700);
    for (const s of r.tax_summary) {
      row(`${Number(s.rate)}%  ${money(s.taxable)}`, r.supply_type === "inter" ? money(s.igst) : `${money(s.cgst)} / ${money(s.sgst)}`, 16);
    }
  }
  if (r.remarks) { rule(); wrap(`Note: ${r.remarks}`, 16); }
  rule();
  wrap(r.footer, 18, 600);
  text("Computer generated · Bill anything. Sell anything.", 14, { align: "center" });
  const out = document.createElement("canvas");
  out.width = dots;
  out.height = y + pad * 2;
  out.getContext("2d")!.drawImage(canvas, 0, 0);
  return canvasToRaster(out);
}
