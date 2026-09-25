import { CheckIcon, CopyIcon, RotateCwIcon, TriangleAlertIcon } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { ApiError } from "@/api/client";
import { useInShell } from "@/components/layout/shell-context";
import { StandalonePage } from "@/components/layout/StandalonePage";
import { Button } from "@/components/ui/button";

function randomId(): string {
  // getRandomValues works on plain-HTTP LAN addresses too, unlike randomUUID.
  const bytes = crypto.getRandomValues(new Uint8Array(8));
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

/** The server's request id when the error came from the API, so both sides can be matched. */
function errorIdFor(error: unknown): string {
  return error instanceof ApiError ? (error.requestId ?? randomId()) : randomId();
}

function ErrorPanel({ error }: { error: unknown }) {
  const { t } = useTranslation();
  const errorId = useMemo(() => errorIdFor(error), [error]);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    console.error(`Winnow error ${errorId}`, error);
  }, [error, errorId]);

  const copy = async () => {
    try {
      // Missing on plain-HTTP origins; the id stays selectable below.
      await navigator.clipboard.writeText(errorId);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  return (
    <section
      aria-labelledby="error-title"
      className="mx-auto flex w-full max-w-lg flex-1 flex-col items-center justify-center px-4 py-16 text-center"
    >
      <span className="mb-4 flex size-12 items-center justify-center rounded-full bg-destructive/10 text-destructive">
        <TriangleAlertIcon className="size-6" aria-hidden="true" />
      </span>
      <h1 id="error-title" className="text-xl font-semibold tracking-tight">
        {t("error.title")}
      </h1>
      <p className="mt-2 text-muted-foreground">{t("error.body")}</p>
      <div className="mt-6 flex flex-wrap justify-center gap-2">
        <Button
          onClick={() => {
            window.location.reload();
          }}
        >
          <RotateCwIcon aria-hidden="true" />
          {t("error.reload")}
        </Button>
        <Button variant="outline" onClick={() => void copy()}>
          {copied ? <CheckIcon aria-hidden="true" /> : <CopyIcon aria-hidden="true" />}
          {copied ? t("error.copied") : t("error.copy")}
        </Button>
      </div>
      <p className="mt-4 text-xs text-muted-foreground">
        {t("error.id")} <code className="font-mono select-all">{errorId}</code>
      </p>
    </section>
  );
}

/** Global error page (guide 11.6). Inside the shell it replaces the page; elsewhere it stands alone. */
export function ErrorPage({ error }: { error: unknown }) {
  const panel = <ErrorPanel error={error} />;
  return useInShell() ? panel : <StandalonePage>{panel}</StandalonePage>;
}
