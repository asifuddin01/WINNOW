import {
  LayoutDashboardIcon,
  LibraryBigIcon,
  SettingsIcon,
  ShieldCheckIcon,
  type LucideIcon,
} from "lucide-react";

import type { FileRouteTypes } from "@/routeTree.gen";

export interface NavItem {
  to: FileRouteTypes["to"];
  label: string;
  icon: LucideIcon;
  /** Active only on this exact path, not on paths below it. */
  exact?: boolean;
}

/** Instance-level navigation, outside any review. */
export const workspaceNav: NavItem[] = [
  { to: "/", label: "My reviews", icon: LibraryBigIcon, exact: true },
  { to: "/account", label: "Account", icon: ShieldCheckIcon },
];

/**
 * Inside a review, in workflow order (guide 11.2). Import, Duplicates, Screen, Full text,
 * Conflicts, Extraction, Risk of bias and Report join this list as their phases land.
 */
export const projectNav: NavItem[] = [
  { to: "/p/$pid", label: "Overview", icon: LayoutDashboardIcon, exact: true },
  { to: "/p/$pid/settings", label: "Settings", icon: SettingsIcon },
];
