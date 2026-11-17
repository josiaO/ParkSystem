#!/usr/bin/env node
// npm run check: create .env.local from .env.example if missing, then check
// that the Zirp API answers. Usage: npm run check [-- --api http://host:8760]
import { existsSync, readFileSync, writeFileSync, copyFileSync } from "node:fs";

const file = ".env.local";
if (!existsSync(file)) {
  copyFileSync(".env.example", file);
  console.log(`created ${file} from .env.example`);
}

const argApi = process.argv.indexOf("--api");
if (argApi > 0 && process.argv[argApi + 1]) {
  const value = process.argv[argApi + 1].replace(/\/+$/, "");
  const lines = readFileSync(file, "utf8").split(/\r?\n/);
  const at = lines.findIndex((l) => l.startsWith("ZIRP_API_URL="));
  if (at >= 0) lines[at] = `ZIRP_API_URL=${value}`;
  else lines.push(`ZIRP_API_URL=${value}`);
  writeFileSync(file, lines.join("\n"));
  console.log(`set ZIRP_API_URL=${value}`);
}

const env = Object.fromEntries(
  readFileSync(file, "utf8")
    .split(/\r?\n/)
    .filter((l) => l && !l.startsWith("#") && l.includes("="))
    .map((l) => [l.slice(0, l.indexOf("=")).trim(), l.slice(l.indexOf("=") + 1).trim()]),
);
const api = (process.env.ZIRP_API_URL || env.ZIRP_API_URL || "http://127.0.0.1:8760").replace(/\/+$/, "");
try {
  const res = await fetch(`${api}/health/live`, { signal: AbortSignal.timeout(5000) });
  console.log(res.ok ? `OK  Zirp API answers at ${api}` : `WARN Zirp API at ${api} returned HTTP ${res.status}`);
} catch (err) {
  console.log(`FAIL Zirp API not reachable at ${api}: ${err.message}`);
  process.exitCode = 1;
}
