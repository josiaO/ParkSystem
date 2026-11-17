export function money(amount: number | null | undefined, currency = "TZS"): string {
  const value = Number(amount || 0);
  const digits = currency === "TZS" ? 0 : 2;
  return `${currency} ${value.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
}

export function when(iso: string | null | undefined, timeZone = "Africa/Dar_es_Salaam"): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString("en-GB", {
    timeZone, day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
  });
}

/** Tanzanian mobile number -> 2557XXXXXXXX, or null when it cannot be one. */
export function normaliseTzPhone(raw: string): string | null {
  const digits = raw.replace(/[^\d+]/g, "").replace(/^\+/, "");
  let local = digits;
  if (local.startsWith("255")) local = local.slice(3);
  if (local.startsWith("0")) local = local.slice(1);
  if (!/^[67]\d{8}$/.test(local)) return null;
  return `255${local}`;
}

/** Display form: 0712 345 678 */
export function prettyPhone(raw: string): string {
  const n = normaliseTzPhone(raw);
  if (!n) return raw;
  const local = "0" + n.slice(3);
  return `${local.slice(0, 4)} ${local.slice(4, 7)} ${local.slice(7)}`;
}
