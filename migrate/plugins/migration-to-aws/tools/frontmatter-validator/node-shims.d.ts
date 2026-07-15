// node-shims.d.ts
//
// Minimal ambient declarations for the slice of Node's stdlib this validator uses.
// Runs under Node 24 (native type-stripping); this file exists ONLY so `tsc` can
// type-check without pulling @types/node — keeping the validator zero-dependency.

declare module "node:fs" {
  export function readFileSync(path: string, encoding: "utf8"): string;
  export function existsSync(path: string): boolean;
  export function readdirSync(path: string): string[];
  export function statSync(path: string): { isDirectory(): boolean };
  export function mkdtempSync(prefix: string): string;
  export function mkdirSync(path: string, options?: { recursive: boolean }): void;
  export function writeFileSync(path: string, data: string): void;
  export function rmSync(path: string, options?: { recursive: boolean; force: boolean }): void;
}

declare module "node:path" {
  export function join(...parts: string[]): string;
  export function resolve(...parts: string[]): string;
  export function dirname(p: string): string;
}

declare module "node:os" {
  export function tmpdir(): string;
}

declare module "node:test" {
  export function test(name: string, fn: () => void | Promise<void>): void;
  export function describe(name: string, fn: () => void): void;
  export function it(name: string, fn: () => void | Promise<void>): void;
}

declare module "node:assert/strict" {
  interface Assert {
    (value: unknown, message?: string): void;
    equal(actual: unknown, expected: unknown, message?: string): void;
    ok(value: unknown, message?: string): void;
    match(value: string, regex: RegExp, message?: string): void;
  }
  const assert: Assert;
  export default assert;
}

declare const process: {
  readonly argv: string[];
  exit(code: number): never;
};

declare const console: {
  log(...args: unknown[]): void;
  error(...args: unknown[]): void;
};

declare const import_meta_url: string;
