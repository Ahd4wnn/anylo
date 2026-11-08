// Printer connection store, ported from PlantBill (frontend/src/store/bluetooth.ts).
// Transports: Web Bluetooth (BLE printers), Web Serial and WebUSB. Settings are per device.
import { create } from "zustand";
import { CUT, DOTS_58MM, DOTS_80MM, FEED, INIT, concat, testPage } from "./escpos";

/* Web Bluetooth / Serial / USB have no bundled TS types; these minimal shapes cover what we call. */
type Char = { properties: { write: boolean; writeWithoutResponse: boolean }; writeValue(d: Uint8Array): Promise<void>; writeValueWithoutResponse?(d: Uint8Array): Promise<void> };
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

async function findWritable(server: Gatt): Promise<Char> {
  const pick = (cs: Char[]) => cs.find((c) => c.properties.write || c.properties.writeWithoutResponse);
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
  connection: null,
  deviceName: null,
  error: null,
  paperDots: Number(store.get("paper")) === DOTS_80MM ? DOTS_80MM : DOTS_58MM,
  autoCut: store.get("autocut") !== "false",
  autoPrint: store.get("autoprint") === "true",
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
    const { connection, autoCut } = get();
    const data = concat([INIT, raster, FEED, autoCut ? CUT : FEED]);
    try {
      set({ error: null });
      if (connection === "bluetooth" && bt) {
        const c = bt.char;
        await writeChunks(data, 20, 15, (d) => (c.writeValueWithoutResponse ? c.writeValueWithoutResponse(d) : c.writeValue(d)));
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
