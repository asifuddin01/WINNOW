import { useState, type ReactNode } from "react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface ConfirmDialogProps {
  /** What opens it; leave it out and pass `open` to open it from elsewhere (a menu). */
  trigger?: ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  title: string;
  description: ReactNode;
  confirmLabel: string;
  /** When set, the person must type this exactly before the action is enabled. */
  confirmPhrase?: string;
  destructive?: boolean;
  onConfirm: () => void;
}

/** Guide 2.3: anything destructive is confirmed, and the important ones are typed out. */
export function ConfirmDialog({
  trigger,
  open: controlled,
  onOpenChange,
  title,
  description,
  confirmLabel,
  confirmPhrase,
  destructive = false,
  onConfirm,
}: ConfirmDialogProps) {
  const [own, setOwn] = useState(false);
  const open = controlled ?? own;
  const setOpen = (next: boolean) => {
    setOwn(next);
    onOpenChange?.(next);
  };
  const [typed, setTyped] = useState("");
  const ready = !confirmPhrase || typed.trim() === confirmPhrase;

  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) setTyped("");
      }}
    >
      {trigger && <AlertDialogTrigger asChild>{trigger}</AlertDialogTrigger>}
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        {confirmPhrase && (
          <div className="grid gap-1.5">
            <Label htmlFor="confirm-phrase">
              Type <span className="font-medium text-foreground">{confirmPhrase}</span> to confirm
            </Label>
            <Input
              id="confirm-phrase"
              value={typed}
              autoComplete="off"
              onChange={(event) => {
                setTyped(event.target.value);
              }}
            />
          </div>
        )}
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            disabled={!ready}
            className={destructive ? "bg-destructive text-white hover:bg-destructive/90" : ""}
            onClick={(event) => {
              if (!ready) {
                event.preventDefault();
                return;
              }
              onConfirm();
            }}
          >
            {confirmLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
