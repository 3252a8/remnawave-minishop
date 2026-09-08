import { describe, it, expect } from "vitest";
import { zipSync, strToU8 } from "fflate";
import { readDemoZip } from "./themePackages";

describe("documentation theme ZIP import", () => {
  it("reads the uploaded collection instead of substituting a fixed theme", () => {
    const data = zipSync({
      "themes/one/theme.json": strToU8('{"key":"one"}'),
      "themes/two/theme.json": strToU8('{"key":"two"}'),
      "themes/minishop-themes.json": strToU8('{"schema_version":1,"themes":[{"path":"two"}]}'),
    });
    expect(readDemoZip(data).map((item) => item.theme.key)).toEqual(["two"]);
  });
  it("rejects traversal and executable files", () => {
    expect(() => readDemoZip(zipSync({ "../escape/theme.json": strToU8("{}") }))).toThrow();
    expect(() =>
      readDemoZip(
        zipSync({
          "one/theme.json": strToU8('{"key":"one"}'),
          "one/run.js": strToU8("alert(1)"),
        })
      )
    ).toThrow();
  });
  it("rejects broken archives and duplicate case-insensitive paths", () => {
    expect(() => readDemoZip(strToU8("not a zip"))).toThrow();
    expect(() =>
      readDemoZip(
        zipSync({
          "one/theme.json": strToU8('{"key":"one"}'),
          "one/THEME.JSON": strToU8("{}"),
        })
      )
    ).toThrow();
  });
});

describe("documentation package lifecycle", () => {
  it("retains a previous package for rollback after update", async () => {
    const { themePackageResponse } = await import("./themePackages");
    const { DEV_MOCK } = await import("../previewMock");
    DEV_MOCK.config.themesCatalog = { default_theme: "dark", themes: [] };
    const catalog = (await themePackageResponse("/admin/themes/library", {})) as {
      generation: number;
    };
    async function upload(version: string) {
      const form = new FormData();
      form.append(
        "file",
        new File(
          [
            zipSync({
              "ocean/theme.json": strToU8('{"key":"ocean","tokens":{"bg":"#123456"}}'),
              "ocean/theme-package.json": strToU8(
                JSON.stringify({ schema_version: 1, version, compatibility: { theme_api: 1 } })
              ),
            }),
          ],
          "sample.zip"
        )
      );
      const response = (await themePackageResponse("/admin/themes/imports", {
        method: "POST",
        body: form,
      })) as { operation: { id: string } };
      return response.operation.id;
    }
    const first = await upload("1.0.0");
    expect(
      await themePackageResponse("/admin/themes/imports/" + first + "/install", {
        method: "POST",
        body: JSON.stringify({
          choices: [{ key: "ocean", action: "install" }],
          expected_generation: catalog.generation,
          idempotency_key: "first",
        }),
      })
    ).toMatchObject({ ok: true });
    const second = await upload("2.0.0");
    expect(
      await themePackageResponse("/admin/themes/imports/" + second + "/install", {
        method: "POST",
        body: JSON.stringify({
          choices: [{ key: "ocean", action: "update" }],
          expected_generation: catalog.generation + 1,
          idempotency_key: "second",
        }),
      })
    ).toMatchObject({ ok: true });
    expect(await themePackageResponse("/admin/themes/library", {})).toMatchObject({
      installations: [{ key: "ocean", version: "2.0.0", can_rollback: true }],
    });
  });
});
