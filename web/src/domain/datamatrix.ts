// SPDX-License-Identifier: AGPL-3.0-or-later
// A six-digit number as a 10x10 Data Matrix ECC200 symbol (ADR 0001), ported
// from the server's encoder (server/src/squarepot_server/labels/datamatrix.py),
// so the header can draw the same scannable code the server prints. Only this
// one symbol size is needed: three data codewords (one per digit pair), five
// Reed-Solomon codewords, and the module placement of ISO/IEC 16022, Annex F.

const SIZE = 10;
const DATA_SIZE = SIZE - 2;
const ECC_CODEWORDS = 5;
const TAG = /^(?!000000)[0-9]{6}$/;

/** A label number the encoder accepts: six digits, not 000000. */
export const isTag = (value: string | undefined): value is string =>
  value !== undefined && TAG.test(value);

// GF(256) with the Data Matrix field polynomial x^8 + x^5 + x^3 + x^2 + 1.
const EXP = new Array<number>(255);
const LOG = new Array<number>(256);
{
  let value = 1;
  for (let power = 0; power < 255; power++) {
    EXP[power] = value;
    LOG[value] = power;
    value <<= 1;
    if (value & 0x100) value ^= 0x12d;
  }
}

function multiply(a: number, b: number): number {
  if (a === 0 || b === 0) return 0;
  return EXP[((LOG[a] ?? 0) + (LOG[b] ?? 0)) % 255] ?? 0;
}

/** Coefficients of (x + a^1)(x + a^2)...(x + a^degree), a = 2, highest power first. */
function generator(degree: number): number[] {
  const polynomial = [1];
  for (let power = 1; power <= degree; power++) {
    const root = EXP[power] ?? 0;
    polynomial.push(0);
    const previous = [...polynomial];
    polynomial[0] = previous[0] ?? 0;
    for (let index = 1; index < polynomial.length; index++) {
      polynomial[index] = (previous[index] ?? 0) ^ multiply(previous[index - 1] ?? 0, root);
    }
  }
  return polynomial;
}

function errorCorrection(data: number[], degree = ECC_CODEWORDS): number[] {
  const polynomial = generator(degree);
  const remainder = new Array<number>(degree).fill(0);
  for (const codeword of data) {
    const factor = codeword ^ (remainder[0] ?? 0);
    remainder.shift();
    remainder.push(0);
    for (let index = 0; index < degree; index++) {
      remainder[index] = (remainder[index] ?? 0) ^ multiply(polynomial[index + 1] ?? 0, factor);
    }
  }
  return remainder;
}

/** Data codewords: digit pairs 00-99 are encoded as 130-229, which fills the symbol. */
export function codewords(tag: string): number[] {
  const data = [0, 2, 4].map((index) => 130 + Number(tag.slice(index, index + 2)));
  return [...data, ...errorCorrection(data)];
}

/** Where each bit of each codeword goes in the data region (ISO/IEC 16022, Annex F). */
class Placement {
  private readonly rows: number;
  private readonly columns: number;
  // (codeword index, bit index with 0 as the most significant), or null until placed.
  private readonly cells: ([number, number] | null)[][];

  constructor(rows: number, columns: number) {
    this.rows = rows;
    this.columns = columns;
    this.cells = Array.from({ length: rows }, () =>
      Array.from({ length: columns }, (): [number, number] | null => null),
    );
    this.place();
  }

  private module(row: number, column: number, codeword: number, bit: number): void {
    if (row < 0) {
      row += this.rows;
      column += 4 - ((this.rows + 4) % 8);
    }
    if (column < 0) {
      column += this.columns;
      row += 4 - ((this.columns + 4) % 8);
    }
    this.cells[row][column] = [codeword, bit];
  }

  private utah(row: number, column: number, codeword: number): void {
    const offsets: readonly [number, number][] = [
      [-2, -2],
      [-2, -1],
      [-1, -2],
      [-1, -1],
      [-1, 0],
      [0, -2],
      [0, -1],
      [0, 0],
    ];
    for (const [bit, [dr, dc]] of offsets.entries()) {
      this.module(row + dr, column + dc, codeword, bit);
    }
  }

  private corner(codeword: number, positions: readonly [number, number][]): void {
    for (const [bit, [row, column]] of positions.entries()) {
      this.module(row, column, codeword, bit);
    }
  }

  private place(): void {
    const { rows, columns } = this;
    let codeword = 0;
    let row = 4;
    let column = 0;
    for (;;) {
      if (row === rows && column === 0) {
        this.corner(codeword, [
          [rows - 1, 0],
          [rows - 1, 1],
          [rows - 1, 2],
          [0, columns - 2],
          [0, columns - 1],
          [1, columns - 1],
          [2, columns - 1],
          [3, columns - 1],
        ]);
        codeword += 1;
      }
      if (row === rows - 2 && column === 0 && columns % 4) {
        this.corner(codeword, [
          [rows - 3, 0],
          [rows - 2, 0],
          [rows - 1, 0],
          [0, columns - 4],
          [0, columns - 3],
          [0, columns - 2],
          [0, columns - 1],
          [1, columns - 1],
        ]);
        codeword += 1;
      }
      if (row === rows - 2 && column === 0 && columns % 8 === 4) {
        this.corner(codeword, [
          [rows - 3, 0],
          [rows - 2, 0],
          [rows - 1, 0],
          [0, columns - 2],
          [0, columns - 1],
          [1, columns - 1],
          [2, columns - 1],
          [3, columns - 1],
        ]);
        codeword += 1;
      }
      if (row === rows + 4 && column === 2 && columns % 8 === 0) {
        this.corner(codeword, [
          [rows - 1, 0],
          [rows - 1, columns - 1],
          [0, columns - 3],
          [0, columns - 2],
          [0, columns - 1],
          [1, columns - 3],
          [1, columns - 2],
          [1, columns - 1],
        ]);
        codeword += 1;
      }
      // Sweep up and to the right, then down and to the left.
      for (;;) {
        if (row < rows && column >= 0 && this.cells[row]?.[column] === null) {
          this.utah(row, column, codeword);
          codeword += 1;
        }
        row -= 2;
        column += 2;
        if (!(row >= 0 && column < columns)) break;
      }
      row += 1;
      column += 3;
      for (;;) {
        if (row >= 0 && column < columns && this.cells[row]?.[column] === null) {
          this.utah(row, column, codeword);
          codeword += 1;
        }
        row += 2;
        column -= 2;
        if (!(row < rows && column >= 0)) break;
      }
      row += 3;
      column += 1;
      if (!(row < rows || column < columns)) break;
    }
  }

  private cell(row: number, column: number): [number, number] {
    const cell = this.cells[row]?.[column];
    if (cell === null || cell === undefined) throw new Error(`cell ${row},${column} was never placed`);
    return cell;
  }
}

const PLACEMENT = new Placement(DATA_SIZE, DATA_SIZE);

/** The symbol's modules, row by row from the top; true is dark. */
export function encode(tag: string): boolean[][] {
  if (!TAG.test(tag)) throw new Error(`not a label number: ${tag}`);
  const words = codewords(tag);
  const matrix = Array.from({ length: SIZE }, () => Array.from({ length: SIZE }, () => false));
  // The finder pattern is the solid left column and bottom row; the timing
  // pattern alternates along the top row and the right column.
  for (let row = 0; row < SIZE; row++) {
    matrix[row][0] = true;
    matrix[row][SIZE - 1] = row % 2 === 1;
  }
  for (let column = 0; column < SIZE; column++) {
    matrix[SIZE - 1][column] = true;
    matrix[0][column] = column % 2 === 0;
  }
  for (let row = 0; row < DATA_SIZE; row++) {
    for (let column = 0; column < DATA_SIZE; column++) {
      // Every module of a 10x10 symbol's data region carries a codeword bit.
      const [codeword, bit] = PLACEMENT.cell(row, column);
      matrix[row + 1][column + 1] = ((words[codeword] ?? 0) & (0x80 >> bit)) !== 0;
    }
  }
  return matrix;
}
