import { createContext, useContext } from "react";

/** True inside AppShell, which already renders the footer. */
export const ShellContext = createContext(false);

export function useInShell(): boolean {
  return useContext(ShellContext);
}
