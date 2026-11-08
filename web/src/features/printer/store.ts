// Printer connection store, ported from PlantBill (frontend/src/store/bluetooth.ts).
// Transports: Web Bluetooth (BLE printers), Web Serial and WebUSB. Settings are per device.
import { create } from "zustand";
import { CUT, DOTS_58MM, DOTS_80MM, FEED, INIT, concat, testPage } from "./escpos";

/* Web Bluetooth / Serial / USB have no bundled TS types; these minimal shapes cover what we call. */
export type Char = { properties: { write: boolean; writeWithoutResponse: boolean }; writeValue(d: Uint8Array): Promise<void>; writeValueWithResponse?(d: Uint8Array): Promise<void>; writeValueWithoutResponse?(d: Uint8Array): Promise<void> };
type Gatt = { connected: boolean; connect(): Promise<Gatt>; disconnect(): void; getPrimaryService(u: string): Promise<{ getCharacteristics(): Promise<Char[]> }>; getPrimaryServices(): Promise<{ getCharacteristics(): Promise<Char[]> }[]> };
type BtDevice = { name?: string; gatt?: Gatt; addEventListener(t: string, f: () => void): void };
type SerialPort = { open(o: { baudRate: number }): Promise<void>; close(): Promise<void>; writable: { getWriter(): { write(d: Uint8Array): Promise<void>; releaseLock(): void } } };
type UsbEndpoint = { direction: string; type: string; endpointNumber: number };
type UsbDevice = {
  productName?: string; configuration?: { configurationValue: number };
  configurations: { interfaces: { interfaceNumber: number; alternates: { interfaceClass: number; endpoints: UsbEndpoint[] }[] }[] }[];
  open(): Promise<void>; close(): Promise<void>; selectConfiguration(n: number): Promise<void>;
  claimInterface(n: number): Promise<void>; releaseInterface(n: number): Promise<void>; transferOut(ep: number, d: Uint8Array): Promise<unknown>;
};
type Nav = Navigator & {
  bluetooth?: { requestDevice(o: unknown): Promise<BtDevice> };
  serial?: { requestPort(): Promise<SerialPort>; addEventListener(t: string, f: (e: { target: unknown }) => void): void };
  usb?: { requestDevice(o: unknown): Promise<UsbDevice>; addEventListener(t: string, f: (e: { device: unknown }) => void): void };
};
const nav = (typeof navigator !== "undefined" ? navigator : {}) as Nav;

export type Connection = "bluetooth" | "serial" | "usb";
const SERVICES = [
  "0000ffe0-0000-1000-8000-00805f9b34fb", "0000ffe1-0000-1000-8000-00805f9b34fb", "0000ff00-0000-1000-8000-00805f9b34fb",
  "000018f0-0000-1000-8000-00805f9b34fb", "e7e1a121-481d-11e5-885d-feff819cdc9f", "0000fee7-0000-1000-8000-00805f9b34fb",
];
const NAME_PREFIXES = ["Printer", "PRINTER", "printer", "MTP", "POS", "Thermal", "XT", "XP", "RT", "T9", "PT"];

// Live handles stay outside React state so renders never touch them.
let bt: { device: BtDevice; char: Char } | null = null;
let serial: SerialPort | null = null;
let usb: { device: UsbDevice; endpoint: number; iface: number } | null = null;

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function writeChunks(data: Uint8Array, size: number, delay: number, write: (c: Uint8Array) => Promise<unknown>) {
  for (let i = 0; i < data.length; i += size) {
    await write(data.slice(i, i + size));
    await sleep(delay); // cheap print boards need time to drain their buffer
  }
}

/**
 * Images are unforgiving: one lost byte shifts every following row (PlantBill printed text, where a lost
 * byte is one missing letter). So prefer acknowledged writes in large chunks: no loss, and ~9x faster
 * than PlantBill's 20-byte fire-and-forget packets. Falls back for printers that only accept
 * write-without-response or small packets. "Busy" errors are retried instead of dropping the chunk.
 */
export async function bleWrite(c: Char, data: Uint8Array) {
  const acked = c.properties.write && (c.writeValueWithResponse || c.writeValue);
  let size = acked ? 180 : 20;
  for (let i = 0; i < data.length; ) {
    const chunk = data.slice(i, i + size);
    for (let attempt = 0; ; attempt++) {
      try {
        if (acked) await (c.writeValueWithResponse ?? c.writeValue).call(c, chunk);
        else await c.writeValueWithoutResponse!.call(c, chunk);
        break;
      } catch (e) {
        const msg = String(e);
        if (/in progress|busy/i.test(msg) && attempt < 20) { await sleep(30); continue; }
        if (size > 20 && /length|too long|NotSupported|invalid/i.test(msg)) { size = 20; break; } // retry this chunk smaller
        throw e;
      }
    }
    if (chunk.length > size) continue; // chunk shrank: resend from the same offset
    i += chunk.length;
    if (!acked) await sleep(12); // no acknowledgements: pace so the printer's radio buffer keeps up
  }
}

async function findWritable(server: Gatt): Promise<Char> {
  // Prefer a characteristic that acknowledges writes (reliable for images); else any writable one.
  const pick = (cs: Char[]) => cs.find((c) => c.properties.write) ?? cs.find((c) => c.properties.writeWithoutResponse);
  for (const uuid of SERVICES) {
    try { const c = pick(await (await server.getPrimaryService(uuid)).getCharacteristics()); if (c) return c; } catch { /* try next */ }
  }
  for (const s of await server.getPrimaryServices()) {
    try { const c = pick(await s.getCharacteristics()); if (c) return c; } catch { /* try next */ }
  }
  throw new Error("This Bluetooth device doesn't accept print data.");
}

const store = {
  get: (k: string) => { try { return localStorage.getItem(`anylo.printer.${k}`); } catch { return null; } },
  set: (k: string, v: string) => { try { localStorage.setItem(`anylo.printer.${k}`, v); } catch { /* storage blocked */ } },
};
const cancelled = (e: unknown) => /cancel|No device selected/i.test(String(e));

interface PrinterState {
  status: "disconnected" | "connecting" | "connected";
  printing: boolean;
  connection: Connection | null;
  deviceName: string | null;
  error: string | null;
  paperDots: number;
  autoCut: boolean;
  autoPrint: boolean;
  baudRate: number;
  supported: Record<Connection, boolean>;
  setPaper: (dots: number) => void;
  setAutoCut: (v: boolean) => void;
  setAutoPrint: (v: boolean) => void;
  setBaudRate: (v: number) => void;
  connect: (type: Connection) => Promise<void>;
  disconnect: () => void;
  /** Sends already-rendered raster bytes; wraps them with init/feed/cut. */
  print: (raster: Uint8Array) => Promise<void>;
  printTest: (logoUrl?: string | null) => Promise<void>;
}

export const usePrinter = create<PrinterState>((set, get) => ({
  status: "disconnected",
  printing: false,
  connection: null,
  deviceName: null,
  error: null,
  paperDots: Number(store.get("paper")) === DOTS_80MM ? DOTS_80MM : DOTS_58MM,
  autoCut: store.get("autocut") !== "false",
  autoPrint: store.get("autoprint") !== "false", // on by default: paying ends with a printed bill
  baudRate: Number(store.get("baud")) || 9600,
  supported: { bluetooth: !!nav.bluetooth, serial: !!nav.serial, usb: !!nav.usb },

  setPaper: (dots) => { store.set("paper", String(dots)); set({ paperDots: dots }); },
  setAutoCut: (v) => { store.set("autocut", String(v)); set({ autoCut: v }); },
  setAutoPrint: (v) => { store.set("autoprint", String(v)); set({ autoPrint: v }); },
  setBaudRate: (v) => { store.set("baud", String(v)); set({ baudRate: v }); },

  async connect(type) {
    get().disconnect();
    set({ status: "connecting", error: null });
    try {
      if (type === "bluetooth") {
        if (!nav.bluetooth) throw new Error("This browser can't use Bluetooth printers. Use Chrome or Edge.");
        const device = await nav.bluetooth.requestDevice({
          filters: [...SERVICES.slice(0, 4).map((s) => ({ services: [s] })), ...NAME_PREFIXES.map((namePrefix) => ({ namePrefix }))],
          optionalServices: SERVICES,
        });
        device.addEventListener("gattserverdisconnected", () => { bt = null; set({ status: "disconnected", connection: null, deviceName: null }); });
        const server = await device.gatt?.connect();
        if (!server) throw new Error("Couldn't open the Bluetooth connection.");
        bt = { device, char: await findWritable(server) };
        set({ deviceName: device.name || "Bluetooth printer" });
      } else if (type === "serial") {
        if (!nav.serial) throw new Error("This browser can't use Serial printers. Use Chrome or Edge.");
        const port = await nav.serial.requestPort();
        await port.open({ baudRate: get().baudRate });
        serial = port;
        set({ deviceName: `Serial / COM port (${get().baudRate} baud)` });
      } else {
        if (!nav.usb) throw new Error("This browser can't use USB printers. Use Chrome or Edge.");
        const device = await nav.usb.requestDevice({ filters: [{ classCode: 7 }, { classCode: 255 }] });
        await device.open();
        if (device.configuration?.configurationValue !== 1) await device.selectConfiguration(1).catch(() => undefined);
        // Prefer printer-class interfaces (7/255); fall back to any bulk OUT endpoint.
        const all = device.configurations.flatMap((c) => c.interfaces.flatMap((i) => i.alternates.map((a) => ({ i, a }))));
        const hit = [...all.filter(({ a }) => a.interfaceClass === 7 || a.interfaceClass === 255), ...all]
          .map(({ i, a }) => ({ iface: i.interfaceNumber, ep: a.endpoints.find((e) => e.direction === "out" && e.type === "bulk") }))
          .find((x) => x.ep);
        if (!hit?.ep) throw new Error("This USB device has no print output.");
        await device.claimInterface(hit.iface);
        usb = { device, endpoint: hit.ep.endpointNumber, iface: hit.iface };
        set({ deviceName: device.productName || "USB printer" });
      }
      store.set("connection", type);
      set({ status: "connected", connection: type });
    } catch (e) {
      bt = null; serial = null; usb = null;
      set({ status: "disconnected", connection: null, error: cancelled(e) ? null : e instanceof Error ? e.message : String(e) });
    }
  },

  disconnect() {
    try { serial?.close(); } catch { /* already closed */ }
    try { if (usb) { void usb.device.releaseInterface(usb.iface); void usb.device.close(); } } catch { /* already closed */ }
    if (bt?.device.gatt?.connected) bt.device.gatt.disconnect();
    bt = null; serial = null; usb = null;
    set({ status: "disconnected", connection: null, deviceName: null });
  },

  async print(raster) {
    // One job at a time: two jobs interleaving on the wire is what garbled the first test print.
    if (get().printing) throw new Error("Still printing the previous job.");
    const { connection, autoCut } = get();
    const data = concat([INIT, raster, FEED, autoCut ? CUT : FEED]);
    set({ printing: true, error: null });
    try {
      if (connection === "bluetooth" && bt) {
        await bleWrite(bt.char, data);
      } else if (connection === "serial" && serial) {
        const w = serial.writable.getWriter();
        try { await writeChunks(data, 64, 5, (d) => w.write(d)); } finally { w.releaseLock(); }
      } else if (connection === "usb" && usb) {
        const u = usb;
        await writeChunks(data, 512, 2, (d) => u.device.transferOut(u.endpoint, d));
      } else {
        throw new Error("No printer connected. Connect one in Settings → Printing.");
      }
    } catch (e) {
      set({ error: `Printing failed: ${e instanceof Error ? e.message : String(e)}` });
      throw e;
    } finally {
      set({ printing: false });
    }
  },

  async printTest(logoUrl) {
    const labels = { bluetooth: "Bluetooth", serial: "Serial / COM", usb: "USB" } as const;
    await get().print(await testPage(get().paperDots, labels[get().connection ?? "bluetooth"], logoUrl));
  },
}));

// Cable pulled out: reflect it immediately.
nav.serial?.addEventListener("disconnect", (e) => { if (e.target === serial) { serial = null; usePrinter.setState({ status: "disconnected", connection: null, deviceName: null }); } });
nav.usb?.addEventListener("disconnect", (e) => { if (usb && e.device === usb.device) { usb = null; usePrinter.setState({ status: "disconnected", connection: null, deviceName: null }); } });
