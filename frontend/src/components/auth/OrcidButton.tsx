import { Button } from "@/components/ui/button";

/** ORCID's iD icon, unaltered, as its brand guidelines ask for sign-in buttons. */
export function OrcidMark() {
  return (
    <svg viewBox="0 0 256 256" className="size-[18px]" aria-hidden="true">
      <path
        fill="#A6CE39"
        d="M256 128c0 70.7-57.3 128-128 128S0 198.7 0 128 57.3 0 128 0s128 57.3 128 128z"
      />
      <path fill="#FFF" d="M86.3 186.2H70.9V79.1h15.4v107.1z" />
      <path
        fill="#FFF"
        d="M108.9 79.1h41.6c39.6 0 57 28.3 57 53.6 0 27.5-21.5 53.6-56.8 53.6h-41.8V79.1zm15.4 93.3h24.5c34.9 0 42.9-26.5 42.9-39.7 0-21.5-13.7-39.7-43.7-39.7h-23.7v79.4z"
      />
      <path
        fill="#FFF"
        d="M88.7 56.8c0 5.5-4.5 10.1-10.1 10.1s-10.1-4.6-10.1-10.1c0-5.6 4.5-10.1 10.1-10.1s10.1 4.6 10.1 10.1z"
      />
    </svg>
  );
}

/** A plain link, like GoogleButton: our API sends the browser to ORCID and back. */
export function OrcidButton({ href }: { href: string }) {
  return (
    <Button asChild variant="outline" size="lg" className="h-10 w-full gap-2.5">
      <a href={href}>
        <OrcidMark />
        Continue with ORCID
      </a>
    </Button>
  );
}
