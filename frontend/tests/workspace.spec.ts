import { test, expect } from "@playwright/test";

test("reviewer can navigate all cases and the actual rulebook", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "A little help. A clear answer." }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Scenarios", exact: true }).click();
  await expect(
    page.getByRole("heading", {
      name: "Twelve conversations. Every decision visible.",
    }),
  ).toBeVisible();
  await expect(page.locator("[data-case]")).toHaveCount(12);
  await page.getByRole("button", { name: "Policy", exact: true }).click();
  await expect(
    page.getByText("Paylane rulebook — paylane-v1", { exact: false }),
  ).toBeVisible();
});

test("mobile layout keeps composer and navigation inside viewport", async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/");
  await expect(page.getByRole("textbox", { name: "Message" })).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "../docs/screenshots/mobile.png",
    fullPage: true,
  });
});

test("desktop evidence panel starts without fabricated tool activity", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/");
  await expect(page.getByText("No tools called yet.")).toBeVisible();
  await page.screenshot({
    path: "../docs/screenshots/playground.png",
    fullPage: true,
  });
});

test("network retry keeps request identity and does not duplicate user message", async ({
  page,
}) => {
  const ids: string[] = [];
  let attempts = 0;
  await page.route("**/api/sessions/*/requests/*", (r) =>
    r.fulfill({ status: 404, json: { detail: "request_not_found" } }),
  );
  await page.route("**/api/sessions/*/messages", (r) => {
    ids.push(r.request().postDataJSON().request_id);
    attempts++;
    return attempts === 1
      ? r.abort("failed")
      : r.fulfill({
          json: {
            text: "Identity required.",
            outcome: "verify",
            verified: false,
            events: [],
          },
        });
  });
  await page.goto("/");
  await page.getByLabel("Message", { exact: true }).fill("Hello");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByRole("log")).toContainText("Identity required.");
  expect(ids.length).toBe(2);
  expect(ids[0]).toBe(ids[1]);
  await expect(page.locator(".message.user")).toHaveCount(1);
});

test("verification badge follows the latest result", async ({ page }) => {
  let turns = 0;
  await page.route("**/api/sessions/*/messages", (r) =>
    r.fulfill({
      json: {
        text: ++turns === 1 ? "Confirmed." : "Please verify again.",
        outcome: "verify",
        verified: turns === 1,
        events: [],
      },
    }),
  );
  await page.goto("/");
  await page.getByLabel("Message", { exact: true }).fill("First");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.locator(".chat-heading")).toContainText(
    "Identity verified",
  );
  await page.getByLabel("Message", { exact: true }).fill("Second");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.locator(".chat-heading")).toContainText("Not verified");
});
