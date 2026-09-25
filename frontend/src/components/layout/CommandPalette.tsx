import { queryOptions, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "@tanstack/react-router";
import {
  ArchiveRestoreIcon,
  FileTextIcon,
  FolderOpenIcon,
  ListChecksIcon,
  LogOutIcon,
  MoonIcon,
  PlusIcon,
  SearchIcon,
  SunIcon,
  UploadIcon,
  type LucideIcon,
} from "lucide-react";
import { Dialog } from "radix-ui";
import { useCallback, useDeferredValue, useId, useMemo, useState } from "react";
import { toast } from "sonner";

import { meQuery, signOut } from "@/api/auth";
import { api, errorMessage, unwrap } from "@/api/client";
import { projectQuery, projectsQuery } from "@/api/projects";
import { projectNav, workspaceNav } from "@/components/layout/nav";
import { useTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";

type Group = "Actions" | "Pages" | "Reviews" | "Records";
const GROUPS: Group[] = ["Actions", "Pages", "Reviews", "Records"];

interface Command {
  id: string;
  group: Group;
  label: string;
  hint?: string;
  icon: LucideIcon;
  run: () => unknown;
}

// Sub-pages the sidebar does not list, so the palette can reach every page.
const SUB_PAGES = [
  { to: "/p/$pid/report/stats", label: "Report: Statistics" },
  { to: "/p/$pid/report/methods", label: "Report: Methods text" },
  { to: "/p/$pid/report/exports", label: "Report: Exports" },
  { to: "/p/$pid/report/audit", label: "Report: Audit log", requires: "edit_settings" },
  { to: "/p/$pid/extraction/forms", label: "Extraction: Forms" },
  {
    to: "/p/$pid/extraction/consensus",
    label: "Extraction: Consensus",
    requires: "resolve_conflicts",
  },
  { to: "/p/$pid/settings/criteria", label: "Settings: Criteria" },
  { to: "/p/$pid/settings/team", label: "Settings: Team" },
] as const;

const MIN_SEARCH = 3;

const paletteRecordsQuery = (pid: string, q: string) =>
  queryOptions({
    queryKey: ["projects", pid, "palette", q] as const,
    queryFn: async ({ signal }) =>
      unwrap(
        await api.GET("/api/v1/projects/{pid}/records", {
          signal,
          params: { path: { pid }, query: { q, limit: 8 } },
        }),
      ),
    staleTime: 30_000,
  });

export function CommandPalette({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/20 supports-backdrop-filter:backdrop-blur-xs" />
        <Dialog.Content
          className="fixed top-[12vh] left-1/2 z-50 w-[calc(100%-2rem)] max-w-xl -translate-x-1/2 overflow-hidden rounded-xl border border-border bg-popover text-popover-foreground shadow-lg focus:outline-none"
          aria-describedby={undefined}
        >
          <Dialog.Title className="sr-only">
            Go to a page, a review, a record or an action
          </Dialog.Title>
          {open && (
            <Palette
              close={() => {
                onOpenChange(false);
              }}
            />
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function Palette({ close }: { close: () => void }) {
  const id = useId();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { pid } = useParams({ strict: false });
  const { resolvedTheme, setTheme } = useTheme();
  const { data: project } = useQuery({ ...projectQuery(pid ?? ""), enabled: Boolean(pid) });
  const { data: reviews } = useQuery(projectsQuery);
  const { data: me } = useQuery(meQuery);
  const [text, setText] = useState("");
  const [active, setActive] = useState(0);
  const query = useDeferredValue(text.trim());
  const searching = Boolean(pid) && query.length >= MIN_SEARCH;
  const { data: found, isFetching } = useQuery({
    ...paletteRecordsQuery(pid ?? "", query),
    enabled: searching,
  });

  const go = useCallback(
    (to: string, params?: Record<string, string>, search?: Record<string, string>) => () =>
      void navigate({ to, params, search } as never),
    [navigate],
  );

  const commands = useMemo<Command[]>(() => {
    const allowed = (need?: string) =>
      !need || (project?.permissions.includes(need as never) ?? false);
    const list: Command[] = [];
    if (pid && project) {
      const p = { pid };
      if (allowed("screen")) {
        list.push({
          id: "screen",
          group: "Actions",
          label: "Continue screening",
          icon: ListChecksIcon,
          run: go("/p/$pid/screen/ta", p),
        });
      }
      if (allowed("import")) {
        list.push({
          id: "import",
          group: "Actions",
          label: "Import search results",
          icon: UploadIcon,
          run: go("/p/$pid/import", p),
        });
      }
      list.push({
        id: "export",
        group: "Actions",
        label: "Export records",
        icon: FileTextIcon,
        run: go("/p/$pid/report/exports", p),
      });
      for (const item of projectNav) {
        if (!allowed(item.requires)) continue;
        list.push({
          id: `page:${item.to}`,
          group: "Pages",
          label: item.label,
          hint: project.title,
          icon: item.icon,
          run: go(item.to, p),
        });
      }
      for (const item of SUB_PAGES) {
        if (!allowed("requires" in item ? item.requires : undefined)) continue;
        list.push({
          id: `page:${item.to}`,
          group: "Pages",
          label: item.label,
          hint: project.title,
          icon: FolderOpenIcon,
          run: go(item.to, p),
        });
      }
    }
    list.push(
      { id: "new", group: "Actions", label: "New review", icon: PlusIcon, run: go("/new") },
      {
        id: "restore",
        group: "Actions",
        label: "Restore a backup",
        icon: ArchiveRestoreIcon,
        run: go("/restore"),
      },
      {
        id: "theme",
        group: "Actions",
        label: resolvedTheme === "dark" ? "Switch to the light theme" : "Switch to the dark theme",
        icon: resolvedTheme === "dark" ? SunIcon : MoonIcon,
        run: () => {
          setTheme(resolvedTheme === "dark" ? "light" : "dark");
        },
      },
      {
        id: "signout",
        group: "Actions",
        label: "Sign out",
        icon: LogOutIcon,
        run: async () => {
          try {
            await signOut(queryClient);
            await navigate({ to: "/login", replace: true });
          } catch (error) {
            toast.error(errorMessage(error));
          }
        },
      },
    );
    for (const item of workspaceNav) {
      if (item.adminOnly && !me?.is_instance_admin) continue;
      list.push({
        id: `page:${item.to}`,
        group: "Pages",
        label: item.label,
        icon: item.icon,
        run: go(item.to),
      });
    }
    for (const review of reviews?.items ?? []) {
      if (review.id === pid) continue;
      list.push({
        id: `review:${review.id}`,
        group: "Reviews",
        label: review.title,
        icon: FolderOpenIcon,
        run: go("/p/$pid", { pid: review.id }),
      });
    }
    const words = query.toLowerCase();
    const matching = words
      ? list.filter((command) =>
          `${command.label} ${command.hint ?? ""}`.toLowerCase().includes(words),
        )
      : list;
    if (searching && pid) {
      for (const record of found?.items ?? []) {
        const who = record.authors[0]?.split(",")[0];
        matching.push({
          id: `record:${record.id}`,
          group: "Records",
          label: record.title ?? "Untitled record",
          hint: [who, record.year, record.doi].filter(Boolean).join(" · "),
          icon: FileTextIcon,
          run: go("/p/$pid/records", { pid }, { record: record.id }),
        });
      }
    }
    return GROUPS.flatMap((group) => matching.filter((command) => command.group === group));
  }, [
    pid,
    project,
    reviews,
    me,
    query,
    searching,
    found,
    go,
    resolvedTheme,
    setTheme,
    queryClient,
    navigate,
  ]);

  const current = Math.min(active, Math.max(commands.length - 1, 0));
  const choose = (command: Command | undefined) => {
    if (!command) return;
    close();
    void command.run();
  };

  return (
    <div className="grid">
      <div className="flex items-center gap-2 border-b border-border px-3">
        <SearchIcon className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        <input
          role="combobox"
          aria-expanded="true"
          aria-controls={`${id}-list`}
          aria-activedescendant={commands[current] ? `${id}-${current}` : undefined}
          aria-label="Search pages, reviews, records and actions"
          aria-autocomplete="list"
          placeholder={
            pid
              ? "Type a page, an action, or a record's title or DOI…"
              : "Type a page, a review or an action…"
          }
          value={text}
          onChange={(event) => {
            setText(event.target.value);
            setActive(0);
          }}
          onKeyDown={(event) => {
            const last = commands.length - 1;
            if (event.key === "ArrowDown") setActive(current >= last ? 0 : current + 1);
            else if (event.key === "ArrowUp") setActive(current <= 0 ? last : current - 1);
            else if (event.key === "Home") setActive(0);
            else if (event.key === "End") setActive(last);
            else if (event.key === "Enter") choose(commands[current]);
            else return;
            event.preventDefault();
          }}
          className="h-12 w-full bg-transparent text-base outline-none placeholder:text-muted-foreground"
        />
      </div>
      <div
        id={`${id}-list`}
        role="listbox"
        aria-label="Results"
        className="max-h-[60vh] overflow-y-auto p-1"
      >
        {GROUPS.map((group) => {
          const members = commands
            .map((command, index) => ({ command, index }))
            .filter(({ command }) => command.group === group);
          if (members.length === 0) return null;
          return (
            <div key={group} role="group" aria-labelledby={`${id}-${group}`}>
              <div
                id={`${id}-${group}`}
                role="presentation"
                className="px-2 pt-2 pb-1 text-xs font-medium text-muted-foreground"
              >
                {group}
              </div>
              {members.map(({ command, index }) => {
                const Icon = command.icon;
                return (
                  <div
                    key={command.id}
                    id={`${id}-${index}`}
                    role="option"
                    aria-selected={index === current}
                    onMouseMove={() => {
                      setActive(index);
                    }}
                    tabIndex={-1}
                    onClick={() => {
                      choose(command);
                    }}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") choose(command);
                    }}
                    className={cn(
                      "flex cursor-pointer items-center gap-2 rounded-md px-2 py-2 text-sm",
                      index === current && "bg-muted",
                    )}
                  >
                    <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                    <span className="min-w-0 flex-1 truncate">{command.label}</span>
                    {command.hint && (
                      <span className="max-w-[40%] truncate text-xs text-muted-foreground">
                        {command.hint}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>
      <p role="status" className="border-t border-border px-3 py-2 text-xs text-muted-foreground">
        {commands.length === 0
          ? isFetching
            ? "Searching…"
            : "Nothing matches."
          : searching && isFetching
            ? `${commands.length} results; searching records…`
            : `${commands.length} results. ↑↓ to move, Enter to open, Esc to close.`}
      </p>
    </div>
  );
}
