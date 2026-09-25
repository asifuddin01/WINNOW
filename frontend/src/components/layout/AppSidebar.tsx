import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";

import { meQuery } from "@/api/auth";

import { projectQuery } from "@/api/projects";
import { progressQuery } from "@/api/screening";
import { BrandMark, Wordmark } from "@/components/layout/Brand";
import { projectNav, workspaceNav, type NavItem } from "@/components/layout/nav";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  useSidebar,
} from "@/components/ui/sidebar";

export function AppSidebar() {
  const { t } = useTranslation();
  const { isMobile, setOpenMobile } = useSidebar();
  // Inside a review, its own pages come first; elsewhere there is no pid to read.
  const { pid } = useParams({ strict: false });
  const { data: me } = useQuery(meQuery);
  // On phones the sidebar is a sheet; close it once a destination is chosen.
  const closeOnMobile = () => {
    if (isMobile) setOpenMobile(false);
  };

  return (
    <Sidebar collapsible="icon" aria-label={t("shell.main")}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" asChild tooltip={t("shell.home")}>
              <Link to="/" onClick={closeOnMobile}>
                <BrandMark />
                <Wordmark />
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        {pid && <ProjectGroup pid={pid} onNavigate={closeOnMobile} />}
        <nav aria-label={t("shell.workspace")}>
          <SidebarGroup>
            <SidebarGroupLabel>{t("shell.workspace")}</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {workspaceNav
                  .filter((item) => !item.adminOnly || me?.is_instance_admin)
                  .map((item) => (
                    <NavLink key={item.to} item={item} onNavigate={closeOnMobile} />
                  ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        </nav>
      </SidebarContent>
      <SidebarRail />
    </Sidebar>
  );
}

function NavLink({
  item,
  params,
  onNavigate,
  count,
}: {
  item: NavItem;
  params?: { pid: string };
  onNavigate: () => void;
  count?: number | null;
}) {
  const { t } = useTranslation();
  return (
    <SidebarMenuItem>
      <SidebarMenuButton asChild tooltip={t(item.labelKey)}>
        <Link
          to={item.to}
          params={params}
          onClick={onNavigate}
          activeOptions={{ exact: item.exact ?? false }}
          activeProps={{ "data-active": true, "aria-current": "page" }}
        >
          <item.icon aria-hidden="true" />
          <span>{t(item.labelKey)}</span>
          {count ? (
            <span className="ml-auto rounded-full bg-conflict px-1.5 text-xs font-semibold text-white tabular-nums dark:text-background">
              {count}
              <span className="sr-only"> waiting</span>
            </span>
          ) : null}
        </Link>
      </SidebarMenuButton>
    </SidebarMenuItem>
  );
}

/** The pages of the review being looked at, titled with its name. */
function ProjectGroup({ pid, onNavigate }: { pid: string; onNavigate: () => void }) {
  const { t } = useTranslation();
  const { data: project } = useQuery(projectQuery(pid));
  const resolver = project?.permissions.includes("resolve_conflicts") ?? false;
  // Only for someone allowed to know: the count alone says reviewers disagreed.
  const { data: progress } = useQuery({
    ...progressQuery(pid, "title_abstract"),
    enabled: resolver && (project?.permissions.includes("screen") ?? false),
  });
  const items = projectNav.filter(
    (item) => !item.requires || (project?.permissions.includes(item.requires) ?? false),
  );
  return (
    <nav aria-label={t("shell.thisReview")}>
      <SidebarGroup>
        <SidebarGroupLabel className="truncate">
          {project?.title ?? t("shell.review")}
        </SidebarGroupLabel>
        <SidebarGroupContent>
          <SidebarMenu>
            {items.map((item) => (
              <NavLink
                key={item.to}
                item={item}
                params={{ pid }}
                onNavigate={onNavigate}
                count={item.badge === "conflicts" ? progress?.conflicts : undefined}
              />
            ))}
          </SidebarMenu>
        </SidebarGroupContent>
      </SidebarGroup>
    </nav>
  );
}
