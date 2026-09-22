import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { LogOutIcon, UserRoundCogIcon } from "lucide-react";
import { toast } from "sonner";

import { meQuery, signOut } from "@/api/auth";
import { errorMessage } from "@/api/client";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { initials } from "@/lib/format";

export function UserMenu() {
  const { data: me } = useQuery(meQuery);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  if (!me) return null;

  const onSignOut = async () => {
    try {
      await signOut(queryClient);
      await navigate({ to: "/login", replace: true });
    } catch (error) {
      toast.error(errorMessage(error));
    }
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={`Account menu for ${me.name}`}>
          <span className="flex size-7 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
            {initials(me.name)}
          </span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-56">
        <DropdownMenuLabel className="grid gap-0.5">
          <span className="truncate text-sm font-medium text-foreground">{me.name}</span>
          <span className="truncate text-xs font-normal text-muted-foreground">{me.email}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link to="/account">
            <UserRoundCogIcon aria-hidden="true" />
            Account and security
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => void onSignOut()}>
          <LogOutIcon aria-hidden="true" />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
