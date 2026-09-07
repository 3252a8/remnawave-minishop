import { ESLint } from "eslint";
import { describe, expect, it } from "vitest";

const eslint = new ESLint();
async function violations(source: string, filePath = "src/admin/sections/UiReuseFixture.svelte") {
  const [result] = await eslint.lintText(source, { filePath });
  expect(result.fatalErrorCount).toBe(0);
  return result.messages.filter((message) =>
    [
      "ui-reuse/native-controls",
      "svelte/no-restricted-html-elements",
      "no-restricted-imports",
    ].includes(message.ruleId || "")
  );
}

describe("UI reuse rules", () => {
  it("rejects legacy list toolbars but keeps field labels and specialized chart controls", async () => {
    expect(
      await violations(
        '<div class="admin-toolbar-card"></div><div class="partners-filters"></div><div class="support-admin-toolbar"></div>'
      )
    ).toHaveLength(3);
    expect(
      await violations(
        '<div class="admin-toolbar-field"></div><div class="admin-revenue-chart-toolbar"></div>'
      )
    ).toEqual([]);
  });
  it("rejects a native menu even in a new screen", async () => {
    expect(await violations("<select><option>Active</option></select>")).toHaveLength(1);
  });
  it("rejects native form fields and manually styled standard buttons", async () => {
    expect(
      await violations(
        '<input type="email" /><textarea></textarea><button class="admin-btn admin-btn-primary">Save</button>'
      )
    ).toHaveLength(3);
  });
  it("keeps semantic HTML and shared components available", async () => {
    expect(
      await violations(
        '<script lang="ts">import { AdminButton, AdminSelect } from "$components/patterns/admin/index.js"; import Input from "$components/ui/input.svelte";</script><article><Input /><AdminSelect /><AdminButton>Save</AdminButton><button aria-label="Expand">+</button></article>'
      )
    ).toEqual([]);
  });
  it("also rejects shared button classes inside expressions and class directives", async () => {
    expect(
      await violations(
        '<button class={true ? "btn-primary" : "btn"}>Save</button><button class:admin-btn={true}>Save</button>'
      )
    ).toHaveLength(2);
  });
  it("rejects direct primitive and icon imports in features", async () => {
    expect(
      await violations(
        '<script lang="ts">import { Select } from "bits-ui"; import { Copy } from "@lucide/svelte";</script>'
      )
    ).toHaveLength(2);
  });
  it("allows native implementation within the UI layer", async () => {
    expect(
      await violations(
        '<input /><button class="btn">Save</button>',
        "src/lib/components/ui/UiReuseFixture.svelte"
      )
    ).toEqual([]);
  });
  it("does not let existing field exceptions grow or silently remain after migration", async () => {
    const file = "src/webapp/checkout/CheckoutEntryScreen.svelte";
    expect(await violations('<input type="email" />', file)).toEqual([]);
    expect(await violations('<input type="email" /><input type="email" />', file)).toHaveLength(1);
    expect(await violations("<p>Migrated</p>", file)).toHaveLength(1);
    expect(await violations('<input type="email" /><input type="password" />', file)).toHaveLength(
      1
    );
  });
});
