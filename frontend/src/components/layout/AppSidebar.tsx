import { Link } from "@tanstack/react-router";

import { BrandMark, Wordmark } from "@/components/layout/Brand";
import { workspaceNav } from "@/components/layout/nav";
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
        <nav aria-label="Workspace">
          <SidebarGroup>
            <SidebarGroupLabel>Workspace</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {workspaceNav.map((item) => (
                  <SidebarMenuItem key={item.to}>
                    <SidebarMenuButton asChild tooltip={item.label}>
                      <Link
                        to={item.to}
                        onClick={closeOnMobile}
                        activeOptions={{ exact: item.exact ?? false }}
                        activeProps={{ "data-active": true, "aria-current": "page" }}
                      >
                        <item.icon aria-hidden="true" />
                        <span>{item.label}</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
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
