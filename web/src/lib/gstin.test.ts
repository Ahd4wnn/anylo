import { readFileSync } from "node:fs";
import { expect, it } from "vitest";
import { isValidGstin } from "./gstin";

const data = JSON.parse(readFileSync(new URL("../../../backend/tests/fixtures/gst_cases.json", import.meta.url), "utf8"));

it.each(data.gstin as { gstin: string; valid: boolean }[])("GSTIN $gstin valid=$valid", ({ gstin, valid }) => {
  expect(isValidGstin(gstin)).toBe(valid);
});
