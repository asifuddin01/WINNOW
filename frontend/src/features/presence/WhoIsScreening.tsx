import { useQuery } from "@tanstack/react-query";

import { presenceQuery, type PresentMember } from "@/api/presence";
import { initials } from "@/lib/format";

const STAGES: Record<PresentMember["stage"], string> = {
  title_abstract: "titles and abstracts",
  full_text: "full texts",
};

/** "Grace is screening titles and abstracts": who, and which stage; never which record. */
export function WhoIsScreening({ pid }: { pid: string }) {
  const { data: present = [] } = useQuery(presenceQuery(pid));
  if (present.length === 0) return null;
  return (
    <ul
      aria-label="Screening now"
      className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground"
    >
      {present.map((member) => (
        <li key={member.user_id} className="flex items-center gap-1.5">
          <span
            aria-hidden="true"
            className="relative flex size-6 items-center justify-center rounded-full bg-secondary text-[0.65rem] font-semibold text-secondary-foreground"
          >
            {initials(member.name)}
            <span className="absolute -right-0.5 -bottom-0.5 size-2 rounded-full border border-background bg-include" />
          </span>
          <span>
            <span className="font-medium text-foreground">{member.name}</span> is screening{" "}
            {STAGES[member.stage]}
          </span>
        </li>
      ))}
    </ul>
  );
}
