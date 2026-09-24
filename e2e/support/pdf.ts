/**
 * Small PDFs and ZIPs for the full-text tests, built in memory with Node alone.
 *
 * The EICAR test string is put together at run time so that no file in the repository is
 * itself flagged by a virus scanner.
 */
import { crc32, deflateRawSync } from "node:zlib";

export const EICAR = Buffer.from(
  ["X5O!P%@AP[4\\PZX54(P^)7CC)7}$", "EICAR-STANDARD-ANTIVIRUS-TEST-FILE!", "$H+H*"].join(""),
);

function pdfString(text: string): string {
  return `(${text.replace(/\\/g, "\\\\").replace(/\(/g, "\\(").replace(/\)/g, "\\)")})`;
}

/** Objects numbered from 1, with a correct cross-reference table. */
function assemble(objects: Buffer[], root = 1): Buffer {
  const parts: Buffer[] = [Buffer.from("%PDF-1.4\n")];
  const offsets: number[] = [];
  let length = parts[0]!.length;
  objects.forEach((body, index) => {
    offsets.push(length);
    const chunk = Buffer.concat([
      Buffer.from(`${index + 1} 0 obj\n`),
      body,
      Buffer.from("\nendobj\n"),
    ]);
    parts.push(chunk);
    length += chunk.length;
  });
  const xref = [
    "xref",
    `0 ${objects.length + 1}`,
    "0000000000 65535 f ",
    ...offsets.map((offset) => `${String(offset).padStart(10, "0")} 00000 n `),
    "trailer",
    `<< /Size ${objects.length + 1} /Root ${root} 0 R >>`,
    "startxref",
    String(length),
    "%%EOF",
    "",
  ].join("\n");
  return Buffer.concat([...parts, Buffer.from(xref)]);
}

function stream(content: Buffer, extra = ""): Buffer {
  return Buffer.concat([
    Buffer.from(`<< /Length ${content.length}${extra} >>\nstream\n`),
    content,
    Buffer.from("\nendstream"),
  ]);
}

/** A PDF with the given lines of text on each page; readable by pypdf and pdf.js. */
export function tinyPdf(pages: string[][], attachment?: { name: string; data: Buffer }): Buffer {
  // 1 catalog, 2 page tree, 3 font, then per page a content stream and the page itself.
  const objects: Buffer[] = [
    Buffer.alloc(0),
    Buffer.alloc(0),
    Buffer.from("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"),
  ];
  const kids: number[] = [];
  for (const lines of pages) {
    const text = lines
      .map((line, index) => `BT /F1 14 Tf 72 ${720 - index * 22} Td ${pdfString(line)} Tj ET`)
      .join("\n");
    objects.push(stream(Buffer.from(text)));
    const content = objects.length;
    objects.push(
      Buffer.from(
        `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] ` +
          `/Resources << /Font << /F1 3 0 R >> >> /Contents ${content} 0 R >>`,
      ),
    );
    kids.push(objects.length);
  }
  objects[1] = Buffer.from(
    `<< /Type /Pages /Kids [${kids.map((kid) => `${kid} 0 R`).join(" ")}] /Count ${kids.length} >>`,
  );
  let names = "";
  if (attachment) {
    objects.push(stream(attachment.data, " /Type /EmbeddedFile"));
    const file = objects.length;
    objects.push(
      Buffer.from(
        `<< /Type /Filespec /F ${pdfString(attachment.name)} /EF << /F ${file} 0 R >> >>`,
      ),
    );
    names = ` /Names << /EmbeddedFiles << /Names [${pdfString(attachment.name)} ${objects.length} 0 R] >> >>`;
  }
  objects[0] = Buffer.from(`<< /Type /Catalog /Pages 2 0 R${names} >>`);
  return assemble(objects);
}

/** A real PDF carrying the EICAR test file as an attachment: guide 12.10's malicious PDF. */
export function eicarPdf(): Buffer {
  return tinyPdf([["A paper with something attached"]], { name: "eicar.com", data: EICAR });
}

/** A ZIP of the given files, deflated, written by hand (no zip64: entries under 4 GB). */
export function makeZip(files: Record<string, Buffer>): Buffer {
  const locals: Buffer[] = [];
  const central: Buffer[] = [];
  let offset = 0;
  for (const [name, data] of Object.entries(files)) {
    const packed = deflateRawSync(data, { level: 9 });
    const nameBytes = Buffer.from(name);
    const crc = crc32(data);
    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50, 0);
    local.writeUInt16LE(20, 4);
    local.writeUInt16LE(0x0800, 6); // UTF-8 names
    local.writeUInt16LE(8, 8); // deflate
    local.writeUInt32LE(crc, 14);
    local.writeUInt32LE(packed.length, 18);
    local.writeUInt32LE(data.length, 22);
    local.writeUInt16LE(nameBytes.length, 26);
    locals.push(local, nameBytes, packed);
    const entry = Buffer.alloc(46);
    entry.writeUInt32LE(0x02014b50, 0);
    entry.writeUInt16LE(20, 4);
    entry.writeUInt16LE(20, 6);
    entry.writeUInt16LE(0x0800, 8);
    entry.writeUInt16LE(8, 10);
    entry.writeUInt32LE(crc, 16);
    entry.writeUInt32LE(packed.length, 20);
    entry.writeUInt32LE(data.length, 24);
    entry.writeUInt16LE(nameBytes.length, 28);
    entry.writeUInt32LE(offset, 42);
    central.push(entry, nameBytes);
    offset += local.length + nameBytes.length + packed.length;
  }
  const directory = Buffer.concat(central);
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0);
  end.writeUInt16LE(Object.keys(files).length, 8);
  end.writeUInt16LE(Object.keys(files).length, 10);
  end.writeUInt32LE(directory.length, 12);
  end.writeUInt32LE(offset, 16);
  return Buffer.concat([...locals, directory, end]);
}

/** One "PDF" of zeros: about 60 KB packed, 64 MB unpacked. */
export function zipBomb(): Buffer {
  return makeZip({ "paper.pdf": Buffer.alloc(64 * 1024 * 1024) });
}
