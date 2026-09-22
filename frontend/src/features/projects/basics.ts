import type { Project, ProjectCreate } from "@/api/projects";
import type { BasicsValues } from "@/features/projects/schemas";

/** An empty text field means "no value", not an empty string. */
function orNull(value: string | undefined): string | null {
  return value?.trim() ? value : null;
}

export function valuesFor(project: Project | undefined): BasicsValues {
  return {
    title: project?.title ?? "",
    review_type: project?.review_type ?? "systematic",
    description: project?.description ?? "",
    research_question: project?.research_question ?? "",
    population: project?.pico?.population ?? "",
    intervention: project?.pico?.intervention ?? "",
    comparator: project?.pico?.comparator ?? "",
    outcome: project?.pico?.outcome ?? "",
  };
}

/** The form's values as the API wants them: PICO is one object, blanks are cleared. */
export function toProject(values: BasicsValues): ProjectCreate {
  return {
    title: values.title,
    review_type: values.review_type,
    description: orNull(values.description),
    research_question: orNull(values.research_question),
    pico: {
      population: orNull(values.population),
      intervention: orNull(values.intervention),
      comparator: orNull(values.comparator),
      outcome: orNull(values.outcome),
    },
  };
}
