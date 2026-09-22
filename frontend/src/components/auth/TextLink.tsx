import { Link, type LinkProps } from "@tanstack/react-router";
import type { ReactNode } from "react";

/** An in-app text link styled for use inside sentences. */
export function TextLink({ children, ...props }: LinkProps & { children: ReactNode }) {
  return (
    <Link
      {...props}
      className="font-medium text-primary underline-offset-4 hover:underline focus-visible:rounded-sm focus-visible:outline-2"
    >
      {children}
    </Link>
  );
}
