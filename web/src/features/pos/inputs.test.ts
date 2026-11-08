import { describe, expect, it } from "vitest";
import { voiceScore } from "./inputs";

describe("voice matching", () => {
  const names = ["Basmati Rice 5kg", "Sunflower Oil", "Toor Dal", "Phenyl Cleaner", "Biscuits"];
  const best = (spoken: string) => [...names].sort((a, b) => voiceScore(spoken, b) - voiceScore(spoken, a))[0];

  it("finds exact and partial names", () => {
    expect(best("basmati rice")).toBe("Basmati Rice 5kg");
    expect(best("oil")).toBe("Sunflower Oil");
  });

  it("tolerates Indian-English pronunciation and recogniser spelling", () => {
    expect(best("fenyl cleaner")).toBe("Phenyl Cleaner");
    expect(best("tur daal")).toBe("Toor Dal");
    expect(best("biskets")).toBe("Biscuits");
  });

  it("scores unrelated words low", () => {
    expect(voiceScore("hammer", "Sunflower Oil")).toBeLessThan(0.5);
  });
});
