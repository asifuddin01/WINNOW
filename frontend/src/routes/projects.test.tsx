import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { PROJECT, USER, mockApi, projectRoutes, summaryOf } from "@/test/api";
import { renderApp, sectionFor } from "@/test/render-app";

const signedIn = { "GET /api/v1/auth/me": USER };

describe("my reviews", () => {
  test("lists the reviews I am on and opens one", async () => {
    const server = mockApi({
      ...signedIn,
      ...projectRoutes(),
      "GET /api/v1/projects": {
        items: [summaryOf(PROJECT), { ...summaryOf(PROJECT), id: "other", title: "Older review" }],
        next_cursor: null,
      },
    });
    const user = userEvent.setup();
    renderApp("/");

    const card = await screen.findByRole("link", { name: /Shift work and sleep quality/ });
    expect(within(card).getByText("Owner")).toBeVisible();
    expect(within(card).getByText(/1 member/)).toBeVisible();
    expect(screen.getByRole("link", { name: /Older review/ })).toBeVisible();

    await user.click(card);
    expect(await screen.findByRole("heading", { level: 1, name: PROJECT.title })).toBeVisible();
    expect(server.calls(`GET /api/v1/projects/${PROJECT.id}`).length).toBeGreaterThan(0);
  });

  test("an empty dashboard invites you to start one", async () => {
    mockApi(signedIn);
    renderApp("/");
    expect(await screen.findByText("No reviews yet")).toBeVisible();
    expect(screen.getAllByRole("link", { name: "New review" }).length).toBeGreaterThan(0);
  });
});

describe("the create-review wizard", () => {
  test("step one creates the review, step two edits its setup", async () => {
    const server = mockApi({
      ...signedIn,
      ...projectRoutes(),
      "POST /api/v1/projects": PROJECT,
      "POST /api/v1/projects/0192f0c1-0000-7000-8000-00000000aaa1/criteria": {
        id: "c1",
        kind: "inclusion",
        text: "Adults over 18",
        position: 0,
      },
    });
    const user = userEvent.setup();
    renderApp("/new");

    await user.type(await screen.findByLabelText("Title"), "Shift work and sleep quality");
    await user.type(
      screen.getByLabelText("Research question"),
      "Do night shifts affect sleep quality in nurses?",
    );
    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(await server.calls("POST /api/v1/projects")[0]?.json()).toMatchObject({
      title: "Shift work and sleep quality",
      review_type: "systematic",
      research_question: "Do night shifts affect sleep quality in nurses?",
    });

    // Step two: the same editors the settings pages use.
    expect(await screen.findByRole("heading", { name: "What counts as relevant?" })).toBeVisible();
    await user.type(screen.getByLabelText("New inclusion criterion"), "Adults over 18");
    await user.click(screen.getByRole("button", { name: "Add inclusion criterion" }));
    expect(await server.calls(`POST /api/v1/projects/${PROJECT.id}/criteria`)[0]?.json()).toEqual({
      kind: "inclusion",
      text: "Adults over 18",
    });

    await user.click(screen.getByRole("button", { name: "Continue to the team" }));
    expect(
      await screen.findByRole("heading", { name: `Who is working on ${PROJECT.title}?` }),
    ).toBeVisible();
  });
});

describe("the review overview", () => {
  test("shows what is still to set up", async () => {
    mockApi({ ...signedIn, ...projectRoutes() });
    renderApp(`/p/${PROJECT.id}`);

    expect(await screen.findByRole("heading", { level: 1, name: PROJECT.title })).toBeVisible();
    expect(screen.getByText("Systematic review")).toBeVisible();
    const checklist = sectionFor(screen.getByRole("heading", { name: "Getting ready" }));
    expect(within(checklist).getAllByText("still to do")).toHaveLength(4);
    expect(within(checklist).getByText("Records imported")).toBeVisible();
    const main = within(screen.getByRole("main"));
    expect(main.getByRole("link", { name: "Settings" })).toHaveAttribute(
      "href",
      `/p/${PROJECT.id}/settings`,
    );
  });

  test("a review you cannot see is not found", async () => {
    mockApi(signedIn);
    renderApp("/p/0192f0c1-0000-7000-8000-00000000bbb2");
    expect(await screen.findByRole("heading", { name: "Review not found" })).toBeVisible();
  });
});
