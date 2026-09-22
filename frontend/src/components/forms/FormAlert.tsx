import { CircleAlertIcon, CircleCheckIcon, TriangleAlertIcon } from "lucide-react";
import type { ReactNode } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";

/** A message about the whole form: announced to screen readers, never colour alone. */
export function FormAlert({
  tone = "error",
  children,
}: {
  tone?: "error" | "success" | "warning";
  children: ReactNode;
}) {
  const Icon =
    tone === "error" ? CircleAlertIcon : tone === "warning" ? TriangleAlertIcon : CircleCheckIcon;
  return (
    <Alert
      variant={tone === "error" ? "destructive" : "default"}
      role={tone === "error" ? "alert" : "status"}
      className={
        tone === "success"
          ? "border-include/40 text-include"
          : tone === "warning"
            ? "border-maybe/40 text-maybe"
            : undefined
      }
    >
      <Icon aria-hidden="true" />
      <AlertDescription className={tone === "error" ? undefined : "text-foreground"}>
        {children}
      </AlertDescription>
    </Alert>
  );
}
