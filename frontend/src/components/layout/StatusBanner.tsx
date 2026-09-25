import { useQuery } from "@tanstack/react-query";
import { CloudOffIcon, ServerCrashIcon } from "lucide-react";
import { useSyncExternalStore } from "react";
import { useTranslation } from "react-i18next";

import { readinessQuery } from "@/api/health";

function subscribeOnline(onChange: () => void) {
  window.addEventListener("online", onChange);
  window.addEventListener("offline", onChange);
  return () => {
    window.removeEventListener("online", onChange);
    window.removeEventListener("offline", onChange);
  };
}

function useOnline(): boolean {
  return useSyncExternalStore(subscribeOnline, () => navigator.onLine);
}

/**
 * Shown only when something is wrong (guide 11.6): the browser is offline, or the
 * server cannot reach its database or Redis. Silent while everything works.
 */
export function StatusBanner() {
  const { t } = useTranslation();
  const online = useOnline();
  const readiness = useQuery({ ...readinessQuery, enabled: online });

  let message: { icon: typeof CloudOffIcon; text: string } | null = null;
  if (!online) {
    message = {
      icon: CloudOffIcon,
      text: t("status.offline"),
    };
  } else if (readiness.isError) {
    message = {
      icon: ServerCrashIcon,
      text: t("status.unreachable"),
    };
  }

  return (
    <div role="status" aria-live="polite">
      {message && (
        <p className="flex items-center gap-2 border-b border-amber-300 bg-amber-50 px-4 py-2 text-sm text-amber-950 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100">
          <message.icon className="size-4 shrink-0" aria-hidden="true" />
          {message.text}
        </p>
      )}
    </div>
  );
}
