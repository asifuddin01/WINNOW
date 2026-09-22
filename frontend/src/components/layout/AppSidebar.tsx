import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "@tanstack/react-router";

import { projectQuery } from "@/api/projects";
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
  const { isMobile, setOpenMobile } = useSidebar();
  // Inside a review, its own pages come first; elsewhere there is no pid to read.
  const { pid } = useParams({ strict: false });
  // On phones the sidebar is a sheet; close it once a destination is chosen.
  const closeOnMobile = () => {
    if (isMobile) setOpenMobile(false);
  };

  return (
    <Sidebar collapsible="icon" aria-label="Main">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" asChild tooltip="Winnow home">
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
        <nav aria-label="Workspace">
          <SidebarGroup>
            <SidebarGroupLabel>Workspace</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {workspaceNav.map((item) => (
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
}: {
  item: NavItem;
  params?: { pid: string };
  onNavigate: () => void;
}) {
  return (
    <SidebarMenuItem>
      <SidebarMenuButton asChild tooltip={item.label}>
        <Link
          to={item.to}
          params={params}
          onClick={onNavigate}
          activeOptions={{ exact: item.exact ?? false }}
          activeProps={{ "data-active": true, "aria-current": "page" }}
        >
          <item.icon aria-hidden="true" />
          <span>{item.label}</span>
        </Link>
      </SidebarMenuButton>
    </SidebarMenuItem>
  );
}

/** The pages of the review being looked at, titled with its name. */
function ProjectGroup({ pid, onNavigate }: { pid: string; onNavigate: () => void }) {
  const { data: project } = useQuery(projectQuery(pid));
  return (
    <nav aria-label="This review">
      <SidebarGroup>
        <SidebarGroupLabel className="truncate">{project?.title ?? "Review"}</SidebarGroupLabel>
        <SidebarGroupContent>
          <SidebarMenu>
            {projectNav.map((item) => (
              <NavLink key={item.to} item={item} params={{ pid }} onNavigate={onNavigate} />
            ))}
          </SidebarMenu>
        </SidebarGroupContent>
      </SidebarGroup>
    </nav>
  );
}
