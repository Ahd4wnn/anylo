import { Camera, Mic, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

/**
 * USB/Bluetooth barcode scanners act as keyboards: a burst of keys < 50 ms apart ending in Enter.
 * Captured anywhere on the page except inside other text fields, so typing in a form isn't hijacked.
 */
export function useHidScanner(onCode: (code: string) => void, enabled = true) {
  const cb = useRef(onCode);
  cb.current = onCode;
  useEffect(() => {
    if (!enabled) return;
    let buf = "";
    let last = 0;
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      const inField = t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable;
      if (inField && !t.dataset.scanTarget) return;
      const now = performance.now();
      if (now - last > 50) buf = "";
      last = now;
      if (e.key === "Enter") {
        if (buf.length >= 4) { e.preventDefault(); cb.current(buf); }
        buf = "";
      } else if (e.key.length === 1) {
        buf += e.key;
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [enabled]);
}

type Detector = { detect(src: CanvasImageSource): Promise<{ rawValue: string }[]> };
const BarcodeDetectorCtor = (globalThis as unknown as { BarcodeDetector?: new (o: unknown) => Detector }).BarcodeDetector;
export const cameraScanSupported = !!BarcodeDetectorCtor;

/** Camera scanning with the browser's built-in BarcodeDetector (Chrome/Edge on Android, ChromeOS, macOS). */
export function CameraScanner({ onCode, onClose }: { onCode: (code: string) => void; onClose: () => void }) {
  const video = useRef<HTMLVideoElement>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let stream: MediaStream | null = null;
    let stop = false;
    (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
        if (!video.current) return;
        video.current.srcObject = stream;
        await video.current.play();
        const det = new BarcodeDetectorCtor!({ formats: ["ean_13", "ean_8", "upc_a", "upc_e", "code_128", "code_39", "qr_code"] });
        let lastCode = "";
        while (!stop) {
          const found = await det.detect(video.current).catch(() => []);
          const code = found[0]?.rawValue;
          if (code && code !== lastCode) { lastCode = code; onCode(code); navigator.vibrate?.(60); setTimeout(() => (lastCode = ""), 1500); }
          await new Promise((r) => setTimeout(r, 150));
        }
      } catch {
        setError("Couldn't open the camera. Allow camera access in the browser.");
      }
    })();
    return () => { stop = true; stream?.getTracks().forEach((t) => t.stop()); };
  }, [onCode]);
  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-black/90 p-4">
      <div className="flex items-center justify-between text-white">
        <p className="font-semibold">Point the camera at a barcode</p>
        <button onClick={onClose} className="grid h-11 w-11 place-items-center rounded-full bg-white/10" aria-label="Close scanner"><X className="h-6 w-6" /></button>
      </div>
      {error ? <p className="mt-8 text-center text-white">{error}</p> : (
        <div className="relative mx-auto mt-6 w-full max-w-md overflow-hidden rounded-xl">
          <video ref={video} className="w-full" muted playsInline />
          <div className="pointer-events-none absolute inset-x-8 top-1/2 h-0.5 bg-white/70" />
        </div>
      )}
      <p className="mt-4 text-center text-sm text-white/70">Keep scanning: each code adds one to the bill.</p>
    </div>
  );
}

export const CameraButton = ({ onClick }: { onClick: () => void }) => (
  <button type="button" onClick={onClick} className="grid h-11 w-11 shrink-0 place-items-center rounded-lg text-text-2 hover:bg-surface-2" aria-label="Scan barcode with camera" title="Scan with camera">
    <Camera className="h-5 w-5" />
  </button>
);

// --- voice search (PlantBill's phonetic matcher, generalised to any product name) ---

const norm = (s: string) => s.toLowerCase().normalize("NFKD").replace(/[^\p{L}\p{N} ]/gu, " ").replace(/\s+/g, " ").trim();
const phonetic = (s: string) =>
  norm(s).replace(/ph/g, "f").replace(/w/g, "v").replace(/z/g, "s").replace(/(.)\1+/g, "$1").replace(/[aeiou]/g, "");

function lev(a: string, b: string) {
  const d = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++) {
    let prev = d[0]++;
    for (let j = 1; j <= b.length; j++) {
      const cur = d[j];
      d[j] = Math.min(d[j] + 1, d[j - 1] + 1, prev + (a[i - 1] === b[j - 1] ? 0 : 1));
      prev = cur;
    }
  }
  return d[b.length];
}

/** Score 0..1 of how well a spoken phrase matches a product name. */
export function voiceScore(spoken: string, name: string): number {
  const s = norm(spoken), n = norm(name);
  if (!s || !n) return 0;
  if (n === s) return 1;
  if (n.includes(s) || s.includes(n)) return 0.9;
  const sw = new Set(s.split(" ")), nw = n.split(" ");
  const overlap = nw.filter((w) => sw.has(w)).length / Math.max(nw.length, sw.size);
  const ps = phonetic(s), pn = phonetic(n);
  const ph = ps && pn ? 1 - lev(ps, pn) / Math.max(ps.length, pn.length) : 0;
  return Math.max(overlap * 0.85, ph * 0.8, 1 - lev(s, n) / Math.max(s.length, n.length));
}

type Recognition = { lang: string; maxAlternatives: number; onresult: (e: { results: { 0: { transcript: string } }[] }) => void; onerror: () => void; onend: () => void; start(): void };
const SpeechCtor = (globalThis as unknown as { webkitSpeechRecognition?: new () => Recognition; SpeechRecognition?: new () => Recognition }).SpeechRecognition
  ?? (globalThis as unknown as { webkitSpeechRecognition?: new () => Recognition }).webkitSpeechRecognition;

export function VoiceButton({ onText }: { onText: (t: string) => void }) {
  const [listening, setListening] = useState(false);
  if (!SpeechCtor) return null;
  const start = () => {
    const r = new SpeechCtor();
    r.lang = "en-IN";
    r.maxAlternatives = 1;
    r.onresult = (e) => onText(e.results[0][0].transcript);
    r.onerror = () => setListening(false);
    r.onend = () => setListening(false);
    setListening(true);
    r.start();
  };
  return (
    <button type="button" onClick={start} aria-label="Search by voice" title="Search by voice"
      className={`grid h-11 w-11 shrink-0 place-items-center rounded-lg ${listening ? "bg-danger-soft text-danger" : "text-text-2 hover:bg-surface-2"}`}>
      <Mic className="h-5 w-5" />
    </button>
  );
}
