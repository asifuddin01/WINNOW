import { z } from "zod";

const line = (max: number, message: string) => z.string().trim().min(1, message).max(max);
const optionalText = (max: number) => z.string().trim().max(max).optional();

export const basicsSchema = z.object({
  title: line(300, "Give the review a title."),
  review_type: z.enum(["systematic", "scoping", "rapid", "umbrella", "other"]),
  description: optionalText(5000),
  research_question: optionalText(5000),
  population: optionalText(2000),
  intervention: optionalText(2000),
  comparator: optionalText(2000),
  outcome: optionalText(2000),
});

export const criterionSchema = z.object({
  kind: z.enum(["inclusion", "exclusion"]),
  text: line(1000, "Write the criterion."),
});

export const keywordGroupSchema = z.object({
  name: line(100, "Name the group."),
  kind: z.enum(["include", "exclude", "neutral"]),
  color: z.enum(["gray", "red", "orange", "amber", "green", "teal", "blue", "violet", "pink"]),
});

export const keywordsSchema = z.object({
  terms: line(2000, "Type at least one term."),
  is_regex: z.boolean(),
  whole_word: z.boolean(),
});

export const reasonSchema = z.object({
  label: line(100, "Name the reason."),
  stage: z.enum(["title_abstract", "full_text", "both"]),
});

export const labelSchema = z.object({
  name: line(100, "Name the label."),
  color: z.enum(["gray", "red", "orange", "amber", "green", "teal", "blue", "violet", "pink"]),
});

export const inviteSchema = z.object({
  email: z.email("Enter a valid email address.").max(254),
  role: z.enum(["admin", "reviewer", "viewer"]),
});

export const titleSchema = z.object({ title: line(300, "Give the copy a title.") });

export type BasicsValues = z.infer<typeof basicsSchema>;
export type CriterionValues = z.infer<typeof criterionSchema>;
export type KeywordGroupValues = z.infer<typeof keywordGroupSchema>;
export type KeywordsValues = z.infer<typeof keywordsSchema>;
export type ReasonValues = z.infer<typeof reasonSchema>;
export type LabelValues = z.infer<typeof labelSchema>;
export type InviteValues = z.infer<typeof inviteSchema>;
export type TitleValues = z.infer<typeof titleSchema>;

/** Terms typed as a list: one per line, or separated by commas. */
export function splitTerms(input: string): string[] {
  return [
    ...new Set(
      input
        .split(/[\n,]/)
        .map((term) => term.trim())
        .filter(Boolean),
    ),
  ];
}
