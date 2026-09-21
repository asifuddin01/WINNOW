import { LibraryBigIcon, type LucideIcon } from "lucide-react";

import type { FileRouteTypes } from "@/routeTree.gen";

export interface NavItem {
  to: FileRouteTypes["to"];
  label: string;
  icon: LucideIcon;
  /** Active only on this exact path, not on paths below it. */
  exact?: boolean;
}

/**
 * Instance-level navigation. The project navigation (Overview · Import · Duplicates ·
 * Screen · Full text · Conflicts · Extraction · Risk of bias · Report · Settings, guide
 * 11.2) joins this sidebar when projects exist.
 */
export const workspaceNav: NavItem[] = [
  { to: "/", label: "My reviews", icon: LibraryBigIcon, exact: true },
];
