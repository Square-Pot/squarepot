// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from "vitest";
import { codewords, encode, isTag } from "./datamatrix";

/** Full symbols straight from the server's encoder, module by module. */
const SYMBOLS: Record<string, string> = {
  "000001": "1010101010110011001110000000001010101101100111100010011110111101101100111101101110100001001111111111",
  "004217": "1010101010110011010111010001101100010101100100100010101000111100100000111100110111101010101111111111",
  "003118": "1010101010110100010111001100001001011101101001000010000110111000010110100101001110101011101111111111",
  "100000": "1010101010110010000110001001001010000101111000100010001111011010100110100101110111100011101111111111",
  "123456": "1010101010110010110111000001001100011101110000100010000011111110110000111101100110011101001111111111",
  "555555": "1010101010110001010111111011001001001101110001011011010000011001110110110100110110011111001111111111",
  "654321": "1010101010110111010111010110001101001111100011100011010110111010000010110101000111101010101111111111",
  "999999": "1010101010111101111111000110001101111111101101010011010111011000010010100110001110010011001111111111",
};

const toLine = (matrix: boolean[][]): string =>
  matrix.map((row) => row.map((dark) => (dark ? "1" : "0")).join("")).join("");

describe("codewords", () => {
  it("encodes digit pairs as 130-229 with five check codewords", () => {
    expect(codewords("000001")).toEqual([130, 130, 131, 72, 47, 91, 121, 222]);
    expect(codewords("123456")).toEqual([142, 164, 186, 114, 25, 5, 88, 102]);
    expect(codewords("999999")).toEqual([229, 229, 229, 252, 122, 208, 160, 224]);
  });
});

describe("encode", () => {
  it("matches the server's symbols module for module", () => {
    for (const [tag, line] of Object.entries(SYMBOLS)) {
      expect(toLine(encode(tag))).toBe(line);
    }
  });
  it("always draws the finder and timing pattern", () => {
    for (const tag of Object.keys(SYMBOLS)) {
      const matrix = encode(tag);
      expect(matrix[0]?.map((dark) => (dark ? "1" : "0")).join("")).toBe("1010101010");
      expect(matrix[9]?.map((dark) => (dark ? "1" : "0")).join("")).toBe("1111111111");
      expect(matrix.every((row) => row[0] === true)).toBe(true);
      expect(matrix.map((row) => (row[9] ? "1" : "0")).join("")).toBe("0101010101");
    }
  });
  it("refuses anything but a six-digit number that is not 000000", () => {
    expect(() => encode("000000")).toThrow();
    expect(() => encode("12345")).toThrow();
    expect(() => encode("1234567")).toThrow();
    expect(() => encode("12345a")).toThrow();
  });
});

describe("isTag", () => {
  it("accepts six digits except 000000", () => {
    expect(isTag("004217")).toBe(true);
    expect(isTag("000000")).toBe(false);
    expect(isTag("12345")).toBe(false);
    expect(isTag(undefined)).toBe(false);
  });
});
