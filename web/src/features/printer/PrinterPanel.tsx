import { Bluetooth, Cable, CheckCircle2, Printer, Usb } from "lucide-react";
import { useShop } from "@/features/shop/api";
import { Button } from "@/ui/Button";
import { FormError } from "@/features/auth/AuthShell";
import { Section, Toggle, useToast } from "@/ui/primitives";
import { DOTS_58MM, DOTS_80MM } from "./escpos";
import { usePrinter, type Connection } from "./store";

const OPTIONS: { type: Connection; label: string; hint: string; icon: typeof Bluetooth }[] = [
  { type: "bluetooth", label: "Bluetooth", hint: "BLE thermal printers", icon: Bluetooth },
  { type: "usb", label: "USB", hint: "Printer plugged into this computer", icon: Usb },
  { type: "serial", label: "Serial / COM", hint: "USB-serial and COM-port printers", icon: Cable },
];

/** Thermal printer setup for this device (settings live in this browser, like PlantBill). */
export function PrinterPanel() {
  const p = usePrinter();
  const { data: shop } = useShop();
  const toast = useToast((s) => s.show);
  const anySupported = Object.values(p.supported).some(Boolean);

  async function test() {
    try { await p.printTest(shop?.logo_url); toast("Test page sent"); } catch { /* error shown in panel */ }
  }

  return (
    <div className="space-y-6">
      <Section title="Receipt printer" description="Connect a thermal printer to this device. Each counter device remembers its own printer.">
        {!anySupported && (
          <p className="rounded-lg bg-warning-soft px-4 py-3 text-sm text-warning">
            This browser can't talk to printers. Use Chrome or Edge on a computer or Android phone. On iPhone, use the Anylo app.
          </p>
        )}
        <FormError message={p.error} />
        {p.status === "connected" ? (
          <div className="flex flex-wrap items-center gap-4 rounded-lg bg-success-soft p-4">
            <CheckCircle2 className="h-6 w-6 text-success" aria-hidden />
            <div className="flex-1">
              <p className="font-semibold text-text">{p.deviceName}</p>
              <p className="text-sm text-text-2">Connected. Bills will print here.</p>
            </div>
            <Button variant="secondary" size="md" onClick={test} loading={p.printing}><Printer className="h-4 w-4" aria-hidden />{p.printing ? "Printing…" : "Test print"}</Button>
            <Button variant="ghost" size="md" onClick={p.disconnect}>Disconnect</Button>
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-3">
            {OPTIONS.map(({ type, label, hint, icon: Icon }) => (
              <button key={type} disabled={!p.supported[type] || p.status === "connecting"} onClick={() => void p.connect(type)}
                className="rounded-lg border border-border p-4 text-left transition-colors hover:border-primary hover:bg-primary-soft disabled:cursor-not-allowed disabled:opacity-50">
                <Icon className="h-5 w-5 text-brand" aria-hidden />
                <span className="mt-2 block font-semibold">{p.status === "connecting" ? "Connecting…" : `Connect ${label}`}</span>
                <span className="block text-sm text-text-2">{p.supported[type] ? hint : "Not available in this browser"}</span>
              </button>
            ))}
          </div>
        )}
      </Section>

      <Section title="Paper and printing">
        <div>
          <p className="mb-2 font-medium">Paper width</p>
          <div className="grid grid-cols-2 gap-3 sm:max-w-sm" role="radiogroup">
            {[{ dots: DOTS_58MM, label: "58 mm (2 inch)" }, { dots: DOTS_80MM, label: "80 mm (3 inch)" }].map((o) => (
              <button key={o.dots} role="radio" aria-checked={p.paperDots === o.dots} onClick={() => p.setPaper(o.dots)}
                className={`rounded-lg border px-4 py-3 font-medium ${p.paperDots === o.dots ? "border-primary bg-primary-soft text-on-primary-soft" : "border-border hover:bg-surface-2"}`}>
                {o.label}
              </button>
            ))}
          </div>
        </div>
        <Toggle checked={p.autoCut} onChange={p.setAutoCut} label="Cut paper after each bill" hint="Turn off if your printer has no cutter." />
        <Toggle checked={p.autoPrint} onChange={p.setAutoPrint} label="Print automatically after saving a bill" />
        <label className="block max-w-xs">
          <span className="mb-1.5 block text-sm font-semibold">Serial speed (baud)</span>
          <select value={p.baudRate} onChange={(e) => p.setBaudRate(Number(e.target.value))}
            className="h-12 w-full rounded-md border border-border-strong bg-surface px-3 text-text">
            {[9600, 19200, 38400, 57600, 115200].map((b) => <option key={b} value={b}>{b}</option>)}
          </select>
          <span className="mt-1 block text-sm text-text-2">Only for Serial / COM printers. 9600 works for most.</span>
        </label>
      </Section>
    </div>
  );
}
