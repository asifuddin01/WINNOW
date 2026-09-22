import { CheckIcon, CopyIcon, DownloadIcon } from "lucide-react";
import { useState } from "react";

import { FormAlert } from "@/components/forms/FormAlert";
import { Button } from "@/components/ui/button";

/** Shown once, right after the codes are made; the server keeps only their hashes. */
export function RecoveryCodes({ codes, onDone }: { codes: string[]; onDone: () => void }) {
  const [copied, setCopied] = useState(false);
  const text = `Winnow recovery codes\nEach code works once.\n\n${codes.join("\n")}\n`;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  const download = () => {
    const url = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "winnow-recovery-codes.txt";
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="grid gap-4">
      <FormAlert tone="success">
        Two-factor authentication is on. Save these recovery codes somewhere safe: each one signs
        you in once if you lose your phone. You will not see them again.
      </FormAlert>
      <ol
        aria-label="Recovery codes"
        className="grid grid-cols-2 gap-x-6 gap-y-1.5 rounded-lg border border-border bg-muted p-4 font-mono text-sm sm:max-w-sm"
      >
        {codes.map((code) => (
          <li key={code} className="select-all">
            {code}
          </li>
        ))}
      </ol>
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" onClick={() => void copy()}>
          {copied ? <CheckIcon aria-hidden="true" /> : <CopyIcon aria-hidden="true" />}
          {copied ? "Copied" : "Copy codes"}
        </Button>
        <Button variant="outline" onClick={download}>
          <DownloadIcon aria-hidden="true" />
          Download
        </Button>
        <Button onClick={onDone}>I have saved them</Button>
      </div>
    </div>
  );
}
