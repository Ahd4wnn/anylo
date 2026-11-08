import { describe, expect, it, vi } from "vitest";

vi.stubGlobal("navigator", {}); // store.ts reads navigator at import
const { bleWrite } = await import("./store");
type Char = Parameters<typeof bleWrite>[0];

const fakeChar = (opts: { write: boolean; maxLen?: number; busyOnce?: boolean }) => {
  const got: number[] = [];
  let busy = opts.busyOnce;
  const send = async (d: Uint8Array) => {
    if (busy) { busy = false; throw new Error("NetworkError: GATT operation already in progress."); }
    if (opts.maxLen && d.length > opts.maxLen) throw new Error("NotSupportedError: Value too long");
    got.push(...d);
  };
  const c: Char = { properties: { write: opts.write, writeWithoutResponse: true }, writeValue: send, writeValueWithResponse: send, writeValueWithoutResponse: send };
  return { c, got };
};
const data = Uint8Array.from({ length: 1000 }, (_, i) => i % 251);

describe("bleWrite never loses or reorders bytes", () => {
  it("uses acknowledged writes and retries when the printer is busy", async () => {
    const { c, got } = fakeChar({ write: true, busyOnce: true });
    await bleWrite(c, data);
    expect(got).toEqual([...data]);
  });

  it("drops to small packets when the printer rejects big ones", async () => {
    const { c, got } = fakeChar({ write: true, maxLen: 20 });
    await bleWrite(c, data);
    expect(got).toEqual([...data]);
  });

  it("works with write-without-response printers", async () => {
    const { c, got } = fakeChar({ write: false });
    await bleWrite(c, data.slice(0, 100));
    expect(got).toEqual([...data.slice(0, 100)]);
  });
});
