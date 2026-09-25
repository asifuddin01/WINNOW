import { useQuery } from "@tanstack/react-query";
import { Outlet, createFileRoute } from "@tanstack/react-router";

import { meQuery } from "@/api/auth";
import { SectionTabs, type SectionTab } from "@/components/layout/SectionTabs";

export const Route = createFileRoute("/_app/admin")({
  component: AdminLayout,
  staticData: { title: "Instance admin" },
});

const TABS: SectionTab[] = [
  { to: "/admin", label: "People", exact: true },
  { to: "/admin/settings", label: "Settings" },
  { to: "/admin/health", label: "Health" },
];

/** Guide 8.18: the instance administrator's panel. */
function AdminLayout() {
  const { data: me } = useQuery(meQuery);
  if (!me) return null;
  if (!me.is_instance_admin) {
    return (
      <div className="mx-auto w-full max-w-3xl px-4 py-8 md:px-8">
        <h1 className="text-2xl font-semibold tracking-tight">Page not found</h1>
        <p className="mt-1 text-muted-foreground">There is nothing here.</p>
      </div>
    );
  }
  return (
    <div className="mx-auto grid w-full max-w-5xl gap-6 px-4 py-8 md:px-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Instance admin</h1>
        <p className="mt-1 max-w-2xl text-muted-foreground">
          Everyone with an account on this Winnow, the settings that can change while it runs, and
          how it is doing.
        </p>
      </div>
      <SectionTabs label="Admin sections" tabs={TABS} />
      <Outlet />
    </div>
  );
}
