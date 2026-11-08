import { describe, expect, it } from "vitest";
import { CUT, INIT, ditherToMono, packRaster } from "./escpos";

// Same cases as PlantBill's Android RasterEscPosTest, so web and Android raster output agree.
describe("ESC/POS raster", () => {
  it("has init and cut commands", () => {
    expect([...INIT]).toEqual([0x1b, 0x40]);
    expect([...CUT]).toEqual([0x1d, 0x56, 0x42, 0x00]);
  });

  it("encodes header width bytes and height", () => {
    const b = packRaster(new Uint8Array(16).fill(1), 16, 1);
    expect([...b]).toEqual([0x1d, 0x76, 0x30, 0x00, 2, 0, 1, 0, 0xff, 0xff]);
  });

  it("sets the most significant bit first and pads to whole bytes", () => {
    expect(packRaster(Uint8Array.from([1, 0, 0, 0, 0, 0, 0, 0]), 8, 1)[8]).toBe(0x80);
    const nine = packRaster(Uint8Array.from([0, 0, 0, 0, 0, 0, 0, 0, 1]), 9, 1);
    expect([nine[4], nine[8], nine[9]]).toEqual([2, 0x00, 0x80]);
  });

  it("splits tall images into bands", () => {
    const b = packRaster(new Uint8Array(8 * 200), 8, 200, 128);
    let headers = 0;
    for (let i = 0; i + 2 < b.length; i++) if (b[i] === 0x1d && b[i + 1] === 0x76 && b[i + 2] === 0x30) headers++;
    expect(headers).toBe(2);
  });

  it("thresholds dark pixels to burn and composites transparency onto white", () => {
    const rgba = Uint8ClampedArray.from([0, 0, 0, 255, 255, 255, 255, 255, 0, 0, 0, 0]);
    expect([...ditherToMono(rgba, 3, 1, false)]).toEqual([1, 0, 0]);
  });
});
