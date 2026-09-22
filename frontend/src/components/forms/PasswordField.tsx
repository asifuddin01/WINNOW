import { EyeIcon, EyeOffIcon } from "lucide-react";
import { useState, type ComponentProps } from "react";

import { TextField } from "@/components/forms/TextField";
import { Button } from "@/components/ui/button";

type PasswordFieldProps = Omit<ComponentProps<typeof TextField>, "type" | "trailing">;

/** A password input with a show/hide toggle instead of a "confirm password" box. */
export function PasswordField(props: PasswordFieldProps) {
  const [visible, setVisible] = useState(false);
  return (
    <TextField
      {...props}
      type={visible ? "text" : "password"}
      spellCheck={false}
      trailing={
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-label={visible ? "Hide password" : "Show password"}
          aria-pressed={visible}
          onClick={() => {
            setVisible((shown) => !shown);
          }}
        >
          {visible ? <EyeOffIcon aria-hidden="true" /> : <EyeIcon aria-hidden="true" />}
        </Button>
      }
    />
  );
}
