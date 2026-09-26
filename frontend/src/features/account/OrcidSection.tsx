import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ORCID_LINK_RESULTS, authOptionsQuery, linkOrcid, meQuery, unlinkOrcid } from "@/api/auth";
import { errorMessage } from "@/api/client";
import { OrcidMark } from "@/components/auth/OrcidButton";
import { FormAlert } from "@/components/forms/FormAlert";
import { Button } from "@/components/ui/button";
import { Section } from "@/features/account/Section";

/**
 * Link an ORCID iD to sign in with it. ORCID shares no email address, so an iD signs in
 * only to the account that linked it (docs/decisions.md). `result` is how a link came
 * back from ORCID.
 */
export function OrcidSection({ result }: { result?: string }) {
  const queryClient = useQueryClient();
  const { data: me } = useQuery(meQuery);
  const { data: options } = useQuery(authOptionsQuery);
  const link = useMutation({ mutationFn: linkOrcid });
  const unlink = useMutation({ mutationFn: () => unlinkOrcid(queryClient) });
  // Shown while the instance offers ORCID, and afterwards to anyone with an iD to unlink.
  if (!me || (!options?.orcid_enabled && !me.orcid)) return null;
  const outcome = result ? ORCID_LINK_RESULTS[result] : undefined;
  const problem = link.error ?? unlink.error;

  return (
    <Section title="ORCID" description="Sign in with your ORCID iD instead of a password.">
      <div className="grid gap-3">
        {outcome && (
          <FormAlert tone={result === "linked" ? "success" : "error"}>{outcome}</FormAlert>
        )}
        {problem && <FormAlert>{errorMessage(problem)}</FormAlert>}
        {me.orcid ? (
          <div className="flex flex-wrap items-center gap-3">
            <a
              href={`https://orcid.org/${me.orcid}`}
              className="inline-flex items-center gap-2 font-mono text-sm underline underline-offset-4"
            >
              <OrcidMark />
              https://orcid.org/{me.orcid}
            </a>
            <Button
              variant="outline"
              size="sm"
              disabled={unlink.isPending}
              onClick={() => {
                unlink.mutate();
              }}
            >
              {unlink.isPending ? "Unlinking…" : "Unlink"}
            </Button>
          </div>
        ) : (
          <Button
            variant="outline"
            className="justify-self-start gap-2.5"
            disabled={link.isPending}
            onClick={() => {
              link.mutate();
            }}
          >
            <OrcidMark />
            {link.isPending ? "Opening ORCID…" : "Link your ORCID iD"}
          </Button>
        )}
      </div>
    </Section>
  );
}
