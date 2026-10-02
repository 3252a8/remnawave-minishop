import { createHash } from "node:crypto";
import { expect, test, type Page } from "@playwright/test";

const sha256 = (value: Buffer) => createHash("sha256").update(value).digest("hex");
const archiveName = "minishop-from-telegram.zip";
const contents = Buffer.from("PK\u0003\u0004backup-data");

function backupFiles() {
  const parts = [contents.subarray(0, 8), contents.subarray(8)].map((buffer, index) => ({
    name: `${archiveName}.part${String(index + 1).padStart(4, "0")}`,
    mimeType: "application/octet-stream",
    buffer,
  }));
  const manifest = {
    name: `${archiveName}.parts.json`,
    mimeType: "application/json",
    buffer: Buffer.from(
      JSON.stringify({
        format: "remnawave-minishop-backup-parts",
        version: 1,
        archive_name: archiveName,
        size_bytes: contents.length,
        sha256: sha256(contents),
        parts: parts.map(({ name, buffer }) => ({
          name,
          size_bytes: buffer.length,
          sha256: sha256(buffer),
        })),
      })
    ),
  };
  return { manifest, parts };
}

async function installBackupApi(page: Page) {
  await page.addInitScript(() => {
    type Api = (path: string, options?: RequestInit) => Promise<Record<string, unknown>>;
    type Bundle = {
      mount: (target: HTMLElement, props: { api: Api } & Record<string, unknown>) => unknown;
    };
    type Archive = {
      name: string;
      size_bytes: number;
      has_database: boolean;
      has_compose: boolean;
      warnings: string[];
    };
    const uploads: string[][] = [];
    const restores: Record<string, unknown>[] = [];
    Object.assign(window, { backupTest: { uploads, restores } });
    const archives: Archive[] = [];
    let bundle: Bundle | undefined;
    async function hash(file: Blob) {
      return Array.from(
        new Uint8Array(await crypto.subtle.digest("SHA-256", await file.arrayBuffer()))
      )
        .map((byte) => byte.toString(16).padStart(2, "0"))
        .join("");
    }
    Object.defineProperty(window, "SubscriptionWebAppAdmin", {
      configurable: true,
      get: () => bundle,
      set(value: Bundle) {
        const mount = value.mount;
        value.mount = (target, props) =>
          mount(target, {
            ...props,
            api: async (path, options) => {
              if (path === "/admin/backups")
                return { ok: true, backup_dir: "data/backups", archives };
              if (path === "/admin/backups/upload") {
                if (!(options?.body instanceof FormData)) return { ok: false };
                const files = options.body
                  .getAll("file")
                  .filter((file): file is File => file instanceof File);
                uploads.push(files.map((file) => file.name));
                let name = files[0]?.name;
                let size = files[0]?.size;
                if (files.length > 1) {
                  const manifestFile = files.find((file) => file.name.endsWith(".parts.json"));
                  if (!manifestFile) return { ok: false, error: "invalid_backup_parts" };
                  const manifest = JSON.parse(await manifestFile.text()) as {
                    archive_name: string;
                    size_bytes: number;
                    sha256: string;
                    parts: { name: string; size_bytes: number; sha256: string }[];
                  };
                  const ordered: File[] = [];
                  for (const part of manifest.parts) {
                    const file = files.find((file) => file.name === part.name);
                    if (
                      !file ||
                      file.size !== part.size_bytes ||
                      (await hash(file)) !== part.sha256
                    )
                      return { ok: false, error: "invalid_backup_parts" };
                    ordered.push(file);
                  }
                  const assembled = new Blob(ordered);
                  if (
                    files.length !== ordered.length + 1 ||
                    assembled.size !== manifest.size_bytes ||
                    (await hash(assembled)) !== manifest.sha256
                  )
                    return { ok: false, error: "invalid_backup_parts" };
                  name = manifest.archive_name;
                  size = assembled.size;
                }
                if (!name?.endsWith(".zip") || !size) return { ok: false };
                const archive = {
                  name,
                  size_bytes: size,
                  has_database: true,
                  has_compose: true,
                  warnings: [],
                };
                archives.push(archive);
                return { ok: true, archive };
              }
              if (path === "/admin/backups/restore") {
                const request = JSON.parse(String(options?.body)) as Record<string, unknown>;
                restores.push(request);
                return {
                  ok: true,
                  result: { archive_name: request.archive_name, compose_restored: true },
                };
              }
              return props.api(path, options);
            },
          });
        bundle = value;
      },
    });
  });
}

async function uploadCount(page: Page) {
  return page.evaluate(
    () => (window as Window & { backupTest: { uploads: string[][] } }).backupTest.uploads.length
  );
}

for (const [device, viewport] of [
  ["desktop", { width: 1440, height: 900 }],
  ["mobile", { width: 390, height: 844 }],
] as const) {
  test(`single ZIP and Telegram parts can be restored through the web UI on ${device}`, async ({
    page,
  }, testInfo) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.setViewportSize(viewport);
    await installBackupApi(page);
    await page.goto("/demo/runtime/admin/backups?theme_preview=dark");
    const input = page.locator(".backups-file-input");
    await expect(input).toHaveAttribute("multiple", "");
    await expect(page.locator(".backups-upload-help")).toContainText(".zip.parts.json");
    await input.setInputFiles({
      name: "single.zip",
      mimeType: "application/zip",
      buffer: contents,
    });
    await expect(page.locator(".backups-selected-name")).toHaveText("single.zip");
    await expect(input).toHaveValue("");

    const { manifest, parts } = backupFiles();
    await input.setInputFiles([parts[1], manifest, parts[0]]);
    await expect(page.locator(".backups-selected-name")).toHaveText(archiveName);
    const uploads = await page.evaluate(
      () => (window as Window & { backupTest: { uploads: string[][] } }).backupTest.uploads
    );
    expect(uploads).toEqual([["single.zip"], [parts[1].name, manifest.name, parts[0].name]]);
    await expect(page.locator(".backups-table")).toContainText(archiveName);

    await page.locator(".backups-check").nth(1).getByRole("checkbox").check();
    await page.locator(".backups-confirmation input").fill(archiveName);
    await page.locator(".backups-restore-body").getByRole("button").last().click();
    await expect
      .poll(() =>
        page.evaluate(
          () =>
            (window as Window & { backupTest: { restores: unknown[] } }).backupTest.restores.length
        )
      )
      .toBe(1);
    expect(
      await page.evaluate(
        () =>
          (window as Window & { backupTest: { restores: Record<string, unknown>[] } }).backupTest
            .restores[0]
      )
    ).toMatchObject({
      archive_name: archiveName,
      restore_compose: true,
      restore_database: false,
      confirmation: archiveName,
    });

    await page.route("**/api/admin/backups/*/download", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/zip",
        headers: { "Content-Disposition": `attachment; filename="${archiveName}"` },
        body: contents,
      })
    );
    const download = page.waitForEvent("download");
    await page
      .locator(".backups-list-toolbar")
      .getByRole("button", { name: "Скачать архив", exact: true })
      .click();
    expect((await download).suggestedFilename()).toBe(archiveName);

    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
      true
    );
    await page.screenshot({
      path: testInfo.outputPath(`backup-parts-${device}.png`),
      fullPage: true,
      animations: "disabled",
    });
    expect(errors).toEqual([]);
  });

  test(`invalid backup sets show errors and allow selecting the same files again on ${device}`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await installBackupApi(page);
    await page.goto("/demo/runtime/admin/backups?theme_preview=dark");
    const input = page.locator(".backups-file-input");
    const { manifest, parts } = backupFiles();
    await input.setInputFiles([manifest, parts[0]]);
    await expect(page.getByText(/Не хватает частей резервной копии/)).toBeVisible();
    expect(await uploadCount(page)).toBe(0);
    await expect(input).toHaveValue("");

    await input.setInputFiles([
      manifest,
      ...parts,
      { name: "other.zip", mimeType: "application/zip", buffer: contents },
    ]);
    await expect(
      page.getByText("Выберите один ZIP либо манифест и все части одной резервной копии.", {
        exact: true,
      })
    ).toBeVisible();
    expect(await uploadCount(page)).toBe(0);

    await input.setInputFiles([{ ...manifest, buffer: Buffer.from("{}") }, ...parts]);
    await expect(page.getByText(/Манифест частей резервной копии повреждён/)).toBeVisible();
    expect(await uploadCount(page)).toBe(0);

    await input.setInputFiles([
      manifest,
      parts[0],
      { ...parts[1], buffer: Buffer.alloc(parts[1].buffer.length) },
    ]);
    await expect.poll(() => uploadCount(page)).toBe(1);
    await expect(page.getByText(/Части резервной копии неполные, повреждены/)).toBeVisible();
    await expect(page.locator(".backups-table")).not.toBeVisible();
    await expect(input).toHaveValue("");

    await input.setInputFiles([manifest, ...parts]);
    await expect(page.locator(".backups-selected-name")).toHaveText(archiveName);
    expect(await uploadCount(page)).toBe(2);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
      true
    );
  });
}
