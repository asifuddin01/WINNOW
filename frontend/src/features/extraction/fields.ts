import type { EntryData, FieldType, Row } from "@/api/extraction";

export const FIELD_TYPES: { value: FieldType; label: string }[] = [
  { value: "section", label: "Section heading" },
  { value: "short_text", label: "Short text" },
  { value: "long_text", label: "Long text" },
  { value: "number", label: "Number" },
  { value: "select", label: "Choice" },
  { value: "multi_select", label: "Several choices" },
  { value: "yes_no_unclear", label: "Yes / no / unclear" },
  { value: "date", label: "Date" },
  { value: "table", label: "Table" },
];

/** What a table's columns may be: one value per cell. */
export const SCALAR_TYPES: FieldType[] = [
  "short_text",
  "long_text",
  "number",
  "select",
  "multi_select",
  "yes_no_unclear",
  "date",
];

/**
 * A field's key from its label, as the server accepts them: lowercase letters, digits
 * and underscores, starting with a letter, 40 at most, and not one already `taken`.
 */
export function keyFrom(label: string, taken: string[]): string {
  const plain = label
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  const stem = (/^[a-z]/.test(plain) ? plain : `field_${plain}`).slice(0, 36).replace(/_+$/, "");
  let key = stem || "field";
  for (let n = 2; taken.includes(key); n += 1) key = `${stem}_${n}`;
  return key;
}

/** `data` with the value at `path` ("n", or "arms[2].mean") set. */
export function withValue(data: EntryData, path: string, value: unknown): EntryData {
  const match = /^([a-z][a-z0-9_]*)\[(\d+)\]\.([a-z][a-z0-9_]*)$/.exec(path);
  if (!match) return { ...data, [path]: value };
  const [, key = "", row = "1", column = ""] = match;
  const rows: Row[] = [...((data[key] as Row[] | undefined) ?? [])];
  const index = Number(row) - 1;
  while (rows.length <= index) rows.push({});
  rows[index] = { ...rows[index], [column]: value };
  return { ...data, [key]: rows };
}
