// POS cart. Persisted to localStorage so a refresh or crash never loses a bill in progress.
import { create } from "zustand";

export interface CartLine {
  key: string;
  variantId?: string;
  custom?: { name: string; tax_rate_id?: string | null; hsn_code?: string | null; unit_code: string };
  name: string;
  variantName?: string | null;
  unit: string;
  qty: string;
  unitPrice: string;
  salePrice: string;
  mrp?: string | null;
  rate: string;
  inclusive: boolean;
}

export interface CartCustomer { name: string; phone: string; gstin: string; address: string }

interface CartState {
  lines: CartLine[];
  customer: CartCustomer;
  b2b: boolean;
  discountType: "flat" | "percent";
  discountValue: string;
  deliveryMode: "counter" | "dispatched";
  deliveryState: string;
  remarks: string;
  idempotencyKey: string | null;
  add: (l: Omit<CartLine, "key" | "qty"> & { qty?: string }) => void;
  setLine: (key: string, patch: Partial<CartLine>) => void;
  remove: (key: string) => void;
  set: (patch: Partial<Omit<CartState, "add" | "setLine" | "remove" | "set" | "clear" | "load" | "snapshot">>) => void;
  clear: () => void;
  load: (snapshot: unknown) => void;
  snapshot: () => Record<string, unknown>;
}

const KEY = "anylo.pos.cart";
const empty = { lines: [] as CartLine[], customer: { name: "", phone: "", gstin: "", address: "" }, b2b: false,
  discountType: "flat" as const, discountValue: "", deliveryMode: "counter" as const, deliveryState: "", remarks: "", idempotencyKey: null };
const restore = () => { try { return { ...empty, ...JSON.parse(localStorage.getItem(KEY) ?? "{}") }; } catch { return empty; } };
let seq = 0;

export const useCart = create<CartState>((set, get) => ({
  ...restore(),
  add(l) {
    // Scanning or tapping the same item again adds to its quantity instead of a new line.
    const existing = l.variantId ? get().lines.find((x) => x.variantId === l.variantId && x.unitPrice === l.unitPrice) : undefined;
    if (existing) return get().setLine(existing.key, { qty: String(Number(existing.qty) + Number(l.qty ?? 1)) });
    set((s) => ({ lines: [...s.lines, { ...l, qty: l.qty ?? "1", key: `${Date.now()}-${++seq}` }] }));
  },
  setLine: (key, patch) => set((s) => ({ lines: s.lines.map((l) => (l.key === key ? { ...l, ...patch } : l)) })),
  remove: (key) => set((s) => ({ lines: s.lines.filter((l) => l.key !== key) })),
  set: (patch) => set(patch),
  clear: () => set({ ...empty, customer: { ...empty.customer } }),
  load: (snap) => set({ ...empty, ...(snap as object), idempotencyKey: null }),
  snapshot: () => {
    const { lines, customer, b2b, discountType, discountValue, deliveryMode, deliveryState, remarks } = get();
    return { lines, customer, b2b, discountType, discountValue, deliveryMode, deliveryState, remarks };
  },
}));

useCart.subscribe((s) => { try { localStorage.setItem(KEY, JSON.stringify(s.snapshot())); } catch { /* storage blocked */ } });
