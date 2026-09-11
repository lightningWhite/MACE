/**
 * Converting a reading, and remembering the reader's preference.
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { convert, formatTemperature, setUnitPreference, unitPreference } from "./units";

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  window.localStorage.clear();
});

describe("convert", () => {
  it("leaves a reading alone when it is already the target scale", () => {
    expect(convert(20, "celsius", "celsius")).toBe(20);
  });

  it("converts celsius to fahrenheit", () => {
    expect(convert(0, "celsius", "fahrenheit")).toBe(32);
    expect(convert(100, "celsius", "fahrenheit")).toBe(212);
  });

  it("converts fahrenheit to celsius", () => {
    expect(convert(32, "fahrenheit", "celsius")).toBe(0);
    expect(convert(212, "fahrenheit", "celsius")).toBe(100);
  });
});

describe("formatTemperature", () => {
  it("rounds and suffixes the converted reading", () => {
    expect(formatTemperature(6, "celsius", "fahrenheit")).toBe("43°F");
    expect(formatTemperature(6, "celsius", "celsius")).toBe("6°C");
  });
});

describe("unitPreference", () => {
  it("defaults to fahrenheit, matching the CLI's own default", () => {
    expect(unitPreference()).toBe("fahrenheit");
  });

  it("remembers what the player chose", () => {
    setUnitPreference("celsius");
    expect(unitPreference()).toBe("celsius");
  });

  it("ignores anything that isn't a scale it knows", () => {
    window.localStorage.setItem("mace.units", "kelvin");
    expect(unitPreference()).toBe("fahrenheit");
  });
});
