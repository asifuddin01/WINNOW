import { CircleAlertIcon, CircleCheckIcon } from "lucide-react";
import type { ReactNode } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";

/** A message about the whole form: announced to screen readers, never colour alone. */
export function FormAlert({
  tone = "error",
  children,
}: {
  tone?: "error" | "success";
  children: ReactNode;
}) {
  const Icon = tone === "error" ? CircleAlertIcon : CircleCheckIcon;
  return (
    <Alert
      variant={tone === "error" ? "destructive" : "default"}
      role={tone === "error" ? "alert" : "status"}
      className={tone === "success" ? "border-include/40 text-include" : undefined}
    >
      <Icon aria-hidden="true" />
      <AlertDescription className={tone === "success" ? "text-foreground" : undefined}>
        {children}
      </AlertDescription>
    </Alert>
  );
}
