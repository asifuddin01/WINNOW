import {
  CopyCheckIcon,
  ListChecksIcon,
  ScaleIcon,
  FileUpIcon,
  LayoutDashboardIcon,
  LibraryBigIcon,
  SettingsIcon,
  ShieldCheckIcon,
  TableIcon,
  type LucideIcon,
} from "lucide-react";

import type { Capability } from "@/api/projects";
import type { FileRouteTypes } from "@/routeTree.gen";

export interface NavItem {
  to: FileRouteTypes["to"];
  label: string;
  icon: LucideIcon;
  /** Active only on this exact path, not on paths below it. */
  exact?: boolean;
  /** Shown only to members who may do this. */
  requires?: Capability;
  /** A count beside the label, e.g. the conflicts waiting. */
  badge?: "conflicts";
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
  { to: "/p/$pid/import", label: "Import", icon: FileUpIcon },
  { to: "/p/$pid/duplicates", label: "Duplicates", icon: CopyCheckIcon },
  { to: "/p/$pid/screen/ta", label: "Screen", icon: ListChecksIcon, requires: "screen" },
  {
    to: "/p/$pid/conflicts",
    label: "Conflicts",
    icon: ScaleIcon,
    requires: "resolve_conflicts",
    badge: "conflicts",
  },
  { to: "/p/$pid/records", label: "Records", icon: TableIcon },
  { to: "/p/$pid/settings", label: "Settings", icon: SettingsIcon },
];
