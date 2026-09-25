import { judgementStyle } from "@/features/rob/wording";

/** A judgement as the plots draw it: a coloured disc with a symbol, and its words. */
export function JudgementMark({ judgement, label }: { judgement: string; label: string }) {
  const style = judgementStyle(judgement);
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        aria-hidden="true"
        className="inline-grid size-5 shrink-0 place-items-center rounded-full text-[0.7rem] leading-none font-bold"
        style={{ backgroundColor: style.fill, color: style.ink }}
      >
        {style.symbol}
      </span>
      <span>{label}</span>
    </span>
  );
}
