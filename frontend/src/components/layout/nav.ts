import {
  ChartColumnIcon,
  ClipboardListIcon,
  CopyCheckIcon,
  GaugeIcon,
  ListChecksIcon,
  ScaleIcon,
  ServerCogIcon,
  FileTextIcon,
  FileUpIcon,
  LayoutDashboardIcon,
  LibraryBigIcon,
  SettingsIcon,
  ShieldCheckIcon,
  TableIcon,
  type LucideIcon,
} from "lucide-react";

import type { Capability } from "@/api/projects";
import type common from "@/i18n/locales/en/common.json";
import type { FileRouteTypes } from "@/routeTree.gen";

export interface NavItem {
  to: FileRouteTypes["to"];
  /** The label's key in the catalogue (src/i18n); translate with `t(item.labelKey)`. */
  labelKey: `nav.${keyof typeof common.nav}`;
  icon: LucideIcon;
  /** Active only on this exact path, not on paths below it. */
  exact?: boolean;
  /** Shown only to members who may do this. */
  requires?: Capability;
  /** A count beside the label, e.g. the conflicts waiting. */
  badge?: "conflicts";
  /** Only for instance administrators (guide 8.18). */
  adminOnly?: boolean;
}

/** Instance-level navigation, outside any review. */
export const workspaceNav: NavItem[] = [
  { to: "/", labelKey: "nav.myReviews", icon: LibraryBigIcon, exact: true },
  { to: "/account", labelKey: "nav.account", icon: ShieldCheckIcon },
  { to: "/admin", labelKey: "nav.admin", icon: ServerCogIcon, adminOnly: true },
];

/**
 * Inside a review, in workflow order (guide 11.2).
 */
export const projectNav: NavItem[] = [
  { to: "/p/$pid", labelKey: "nav.overview", icon: LayoutDashboardIcon, exact: true },
  { to: "/p/$pid/import", labelKey: "nav.import", icon: FileUpIcon },
  { to: "/p/$pid/duplicates", labelKey: "nav.duplicates", icon: CopyCheckIcon },
  { to: "/p/$pid/screen/ta", labelKey: "nav.screen", icon: ListChecksIcon, requires: "screen" },
  { to: "/p/$pid/screen/ft", labelKey: "nav.fullText", icon: FileTextIcon },
  {
    to: "/p/$pid/conflicts",
    labelKey: "nav.conflicts",
    icon: ScaleIcon,
    requires: "resolve_conflicts",
    badge: "conflicts",
  },
  { to: "/p/$pid/extraction", labelKey: "nav.extraction", icon: ClipboardListIcon },
  { to: "/p/$pid/rob", labelKey: "nav.rob", icon: GaugeIcon },
  { to: "/p/$pid/report", labelKey: "nav.report", icon: ChartColumnIcon },
  { to: "/p/$pid/records", labelKey: "nav.records", icon: TableIcon },
  { to: "/p/$pid/settings", labelKey: "nav.settings", icon: SettingsIcon },
];
