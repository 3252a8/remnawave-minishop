import { expect, test, type Locator, type Page } from "@playwright/test";
import type { Core } from "cytoscape";

const adminUrl = (route: string) =>
  `/demo/runtime/admin/${route}?theme_preview=dark&mock=checkout-addons`;

for (const width of [1440, 768, 390, 320]) {
  for (const theme of ["dark", "light"]) {
    test(`relationship graph supports complete referral and partner navigation at ${width}px ${theme}`, async ({
      page,
    }, testInfo) => {
      const errors: string[] = [];
      let workers = 0;
      let graphRequests = 0;
      page.on("pageerror", (error) => errors.push(error.message));
      page.on("worker", () => workers++);
      page.on("request", (request) => {
        if (new URL(request.url()).pathname.endsWith("/api/admin/users/relationships"))
          graphRequests++;
      });
      await page.setViewportSize({ width, height: width < 600 ? 844 : 900 });
      await page.goto(`/demo/runtime/admin/users/910083?theme_preview=${theme}`);
      await page.locator('[data-admin-action="show-in-relationships-graph"]').click();
      const graph = page.locator("[data-relationships-graph]");
      await expect(graph).toBeVisible();
      await expect(graph.locator(".relationships-stage")).toHaveAttribute("aria-busy", "false");
      await expect(page).toHaveURL(/view=relationships.*focus=910083/);
      await expect(graph.locator('[data-graph-user-id="910083"]')).toBeVisible();
      // A middle generation includes both its inviter and its own invitees.
      await expect(
        graph.locator('.relationships-selection li[data-relationship-kind="referral"]')
      ).toHaveCount(5);
      await graph.locator('input[type="search"]').fill("910001");
      await graph.locator('input[type="search"]').press("Enter");
      await expect(graph.locator('[data-graph-user-id="910001"]')).toHaveClass(/selected/);
      expect(
        await graph
          .locator('.relationships-selection li[data-relationship-kind="referral"]')
          .count()
      ).toBeGreaterThan(0);
      expect(
        await graph.locator('.relationships-selection li[data-relationship-kind="partner"]').count()
      ).toBeGreaterThan(0);
      await expect(graph.locator(".relationships-stage canvas").first()).toBeVisible();
      const backgrounds = await graph
        .locator(
          ".relationships-stage, .relationships-node, .admin-list-toolbar, .relationships-selection, .admin-btn"
        )
        .evaluateAll((elements) =>
          elements.map((element) => getComputedStyle(element).backgroundImage)
        );
      expect(backgrounds.every((background) => background === "none")).toBe(true);
      if (width === 1440 && theme === "dark") {
        await page.setViewportSize({ width: 390, height: 844 });
        await expect
          .poll(() =>
            graph.locator(".relationships-node.selected").evaluate((node) => {
              const bounds = node.getBoundingClientRect(),
                stage = node.closest(".relationships-stage")!.getBoundingClientRect();
              return bounds.left >= stage.left && bounds.right <= stage.right;
            })
          )
          .toBe(true);
        await page.screenshot({
          path: testInfo.outputPath("relationships-resized-mobile.png"),
          fullPage: true,
          animations: "disabled",
        });
        await page.setViewportSize({ width, height: 900 });
      }
      const geometry = await graph.locator(".relationships-canvas").evaluate((element) => {
        const cy = (element as HTMLDivElement & { _cyreg: { cy: Core } })._cyreg.cy;
        return cy.edges().map((edge) => ({
          source: edge.source().id(),
          target: edge.target().id(),
          points: [edge.sourceEndpoint(), ...(edge.segmentPoints() || []), edge.targetEndpoint()],
        }));
      });
      expect(geometry.length).toBeGreaterThan(10);
      const layoutBounds = await graph.locator(".relationships-canvas").evaluate((element) => {
        const cy = (element as HTMLDivElement & { _cyreg: { cy: Core } })._cyreg.cy;
        const bounds = cy.elements().boundingBox();
        const targets = new Set(cy.edges().map((edge) => edge.target().id()));
        return {
          aspectRatio: bounds.w / bounds.h,
          rootRows: new Set(
            cy
              .nodes()
              .filter((node) => !targets.has(node.id()))
              .map((node) => Math.round(node.position("y")))
          ).size,
        };
      });
      // Independent families must occupy several rows, even in the overview.
      // INCLUDE_CHILDREN previously flattened this fixture into a 30k-pixel strip.
      expect(layoutBounds.aspectRatio).toBeLessThan(3);
      expect(layoutBounds.rootRows).toBeGreaterThan(2);
      for (const route of geometry) {
        expect(Math.abs(route.points[0].x - route.points[1].x)).toBeLessThan(0.01);
        expect(Math.abs(route.points.at(-1)!.x - route.points.at(-2)!.x)).toBeLessThan(0.01);
        for (let index = 1; index < route.points.length; index++) {
          const before = route.points[index - 1],
            after = route.points[index];
          expect(Math.abs(before.x - after.x) < 0.01 || Math.abs(before.y - after.y) < 0.01).toBe(
            true
          );
        }
      }
      const uuid = graph.locator(".relationships-node.selected dl > div:first-child dd");
      await expect(uuid).toHaveText(/^ms_[0-9a-f]{32}$/);
      expect(await uuid.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(
        true
      );
      const identityGeometry = await graph
        .locator(".relationships-node.selected")
        .evaluate((node) => {
          const avatar = node.querySelector(".admin-avatar")!.getBoundingClientRect();
          const values = Array.from(node.querySelectorAll("dl dd, .admin-user-cell-name")).map(
            (value) => value.getBoundingClientRect()
          );
          return {
            rightOfAvatar: values.every((value) => value.left >= avatar.right),
            fitsHeight: node.scrollHeight <= node.clientHeight,
            height: node.clientHeight,
          };
        });
      expect(identityGeometry.rightOfAvatar).toBe(true);
      expect(identityGeometry.fitsHeight).toBe(true);
      expect(identityGeometry.height).toBeLessThanOrEqual(112);
      if (width === 1440 && theme === "dark") {
        const focusBefore = new URL(page.url()).searchParams.get("focus");
        await graph.locator(".relationships-node").first().focus();
        await page.keyboard.press("Tab");
        await expect
          .poll(() =>
            graph.evaluate((element) => {
              const active = document.activeElement;
              const stage = element.querySelector(".relationships-stage")!,
                overlay = element.querySelector(".relationships-overlays")!;
              if (!active?.matches(".relationships-node")) return false;
              const bounds = active.getBoundingClientRect(),
                viewport = stage.getBoundingClientRect();
              return (
                stage.scrollLeft === 0 &&
                stage.scrollTop === 0 &&
                overlay.scrollLeft === 0 &&
                overlay.scrollTop === 0 &&
                bounds.left >= viewport.left &&
                bounds.right <= viewport.right &&
                bounds.top >= viewport.top &&
                bounds.bottom <= viewport.bottom
              );
            })
          )
          .toBe(true);
        expect(new URL(page.url()).searchParams.get("focus")).toBe(focusBefore);
        await graph.locator('input[type="search"]').press("Enter");
      }
      // Pointer gestures over the HTML card must still reach the canvas beneath it.
      const card = graph.locator(".relationships-node.selected");
      const layer = graph.locator(".relationships-node-layer");
      await graph.locator(".relationships-stage").scrollIntoViewIfNeeded();
      await card.scrollIntoViewIfNeeded();
      const before = await layer.getAttribute("style");
      const cardStyle = await card.getAttribute("style");
      await card.evaluate((element) => element.setAttribute("data-pan-preserved", "true"));
      const bounds = (await card.boundingBox())!;
      const stageBounds = (await graph.locator(".relationships-stage").boundingBox())!;
      const point = {
        x:
          (Math.max(bounds.x, stageBounds.x, 0) +
            Math.min(bounds.x + bounds.width, stageBounds.x + stageBounds.width, width)) /
          2,
        y:
          (Math.max(bounds.y, stageBounds.y, 0) +
            Math.min(
              bounds.y + bounds.height,
              stageBounds.y + stageBounds.height,
              width < 600 ? 844 : 900
            )) /
          2,
      };
      expect(
        await page.evaluate(
          ({ x, y }) => Boolean(document.elementFromPoint(x, y)?.closest(".relationships-canvas")),
          point
        )
      ).toBe(true);
      // Cytoscape deliberately ignores wheel zoom for 250 ms after an ancestor
      // scroll; wait for its real scroll guard instead of sending into it.
      await expect
        .poll(() =>
          graph.locator(".relationships-canvas").evaluate((element) => {
            const cy = (
              element as HTMLDivElement & {
                _cyreg: { cy: Core & { renderer(): { scrollingPage?: boolean } } };
              }
            )._cyreg.cy;
            return Boolean(cy.renderer().scrollingPage);
          })
        )
        .toBe(false);
      await page.mouse.move(point.x, point.y);
      const panBefore = await graph
        .locator(".relationships-canvas")
        .evaluate((element) =>
          (element as HTMLDivElement & { _cyreg: { cy: Core } })._cyreg.cy.pan()
        );
      await page.mouse.down();
      await page.mouse.move(point.x + 36, point.y + 24, { steps: 8 });
      const panAfter = await graph
        .locator(".relationships-canvas")
        .evaluate((element) =>
          (element as HTMLDivElement & { _cyreg: { cy: Core } })._cyreg.cy.pan()
        );
      expect(panAfter.x - panBefore.x).toBeCloseTo(36 * 1.5, 0);
      expect(panAfter.y - panBefore.y).toBeCloseTo(24 * 1.5, 0);
      await page.mouse.up();
      const readPan = () =>
        graph.locator(".relationships-canvas").evaluate((element) => ({
          ...(element as HTMLDivElement & { _cyreg: { cy: Core } })._cyreg.cy.pan(),
        }));
      await expect.poll(async () => (await readPan()).x).toBeGreaterThan(panAfter.x + 3);
      // A fresh press stops inertia immediately, without waiting for a drag.
      await page.mouse.down();
      const stopped = await readPan();
      await page.waitForTimeout(100);
      expect(await readPan()).toEqual(stopped);
      await page.mouse.up();
      if (width === 1440 && theme === "dark") {
        await page.emulateMedia({ reducedMotion: "reduce" });
        await page.mouse.down();
        await page.mouse.move(point.x + 48, point.y + 32, { steps: 4 });
        await page.mouse.up();
        const reduced = await readPan();
        await page.waitForTimeout(100);
        expect(await readPan()).toEqual(reduced);
        await page.emulateMedia({ reducedMotion: "no-preference" });
        // Holding a gesture still before release must not cause a stale flick.
        await page.mouse.down();
        await page.mouse.move(point.x + 60, point.y + 40, { steps: 4 });
        await page.waitForTimeout(120);
        await page.mouse.up();
        const held = await readPan();
        await page.waitForTimeout(100);
        expect(await readPan()).toEqual(held);
        // A pause before movement must not dilute the velocity of a fresh flick.
        await page.mouse.down();
        await page.waitForTimeout(150);
        await page.mouse.move(point.x + 72, point.y + 48, { steps: 4 });
        const flick = await readPan();
        await page.mouse.up();
        await expect.poll(async () => (await readPan()).x).toBeGreaterThan(flick.x + 3);
        await page.mouse.down();
        await page.mouse.up();
      }
      await expect(layer).not.toHaveAttribute("style", before!);
      await expect(card).toHaveAttribute("style", cardStyle!);
      await expect(card).toHaveAttribute("data-pan-preserved", "true");
      if ((width === 390 || width === 1440) && theme === "dark") {
        const canvas = graph.locator(".relationships-canvas");
        const box = (await canvas.boundingBox())!;
        const touch = { x: box.x + box.width / 2, y: Math.max(70, Math.min(box.y + 120, 760)) };
        const touchInitial = await canvas.evaluate((element) => {
          const cy = (element as HTMLDivElement & { _cyreg: { cy: Core } })._cyreg.cy;
          return { pan: { ...cy.pan() }, zoom: cy.zoom() };
        });
        const session = await page.context().newCDPSession(page);
        try {
          await session.send("Input.dispatchTouchEvent", {
            type: "touchStart",
            touchPoints: [{ ...touch, id: 1 }],
          });
          // Cross the browser/Cytoscape touch threshold before measuring the
          // steady drag: the native initial threshold delta depends on zoom.
          await session.send("Input.dispatchTouchEvent", {
            type: "touchMove",
            touchPoints: [{ x: touch.x + 20, y: touch.y + 10, id: 1 }],
          });
          await expect
            .poll(() =>
              canvas.evaluate(
                (element) =>
                  (element as HTMLDivElement & { _cyreg: { cy: Core } })._cyreg.cy.pan().x
              )
            )
            .not.toBe(touchInitial.pan.x);
          const touchBefore = await canvas.evaluate((element) => {
            const cy = (element as HTMLDivElement & { _cyreg: { cy: Core } })._cyreg.cy;
            return { pan: { ...cy.pan() }, zoom: cy.zoom() };
          });
          for (let step = 1; step <= 8; step++) {
            await session.send("Input.dispatchTouchEvent", {
              type: "touchMove",
              touchPoints: [{ x: touch.x + 20 + step * 5, y: touch.y + 10 + step * 2.5, id: 1 }],
            });
          }
          const touchAfter = await canvas.evaluate((element) => {
            const cy = (element as HTMLDivElement & { _cyreg: { cy: Core } })._cyreg.cy;
            return { pan: { ...cy.pan() }, zoom: cy.zoom() };
          });
          expect(touchAfter.pan.x - touchBefore.pan.x).toBeCloseTo(40 * 1.5, 0);
          expect(touchAfter.pan.y - touchBefore.pan.y).toBeCloseTo(20 * 1.5, 0);
          expect(touchAfter.zoom).toBe(touchBefore.zoom);
          await session.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
          await expect.poll(async () => (await readPan()).x).toBeGreaterThan(touchAfter.pan.x + 2);
          // Two fingers retain native 1:1 translation and the exact pinch ratio.
          const start = [
            { x: touch.x - 110, y: touch.y, id: 1 },
            { x: touch.x + 110, y: touch.y, id: 2 },
          ];
          await session.send("Input.dispatchTouchEvent", {
            type: "touchStart",
            touchPoints: start,
          });
          const pinchBefore = await canvas.evaluate((element) => {
            const cy = (element as HTMLDivElement & { _cyreg: { cy: Core } })._cyreg.cy;
            return { pan: { ...cy.pan() }, zoom: cy.zoom() };
          });
          await session.send("Input.dispatchTouchEvent", {
            type: "touchMove",
            touchPoints: [
              { x: touch.x - 132, y: touch.y, id: 1 },
              { x: touch.x + 132, y: touch.y, id: 2 },
            ],
          });
          await session.send("Input.dispatchTouchEvent", {
            type: "touchMove",
            touchPoints: [
              { x: touch.x - 132 + 10, y: touch.y + 6, id: 1 },
              { x: touch.x + 132 + 10, y: touch.y + 6, id: 2 },
            ],
          });
          await session.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
          const pinched = await canvas.evaluate((element) => {
            const cy = (element as HTMLDivElement & { _cyreg: { cy: Core } })._cyreg.cy;
            return { pan: { ...cy.pan() }, zoom: cy.zoom() };
          });
          expect(pinched.zoom / pinchBefore.zoom).toBeCloseTo(1.2, 2);
          expect(pinched.pan.x).toBeCloseTo(
            1.2 * pinchBefore.pan.x - 0.2 * (touch.x - box.x) + 10,
            0
          );
          expect(pinched.pan.y).toBeCloseTo(
            1.2 * pinchBefore.pan.y - 0.2 * (touch.y - box.y) + 6,
            0
          );
        } finally {
          await session.detach();
        }
        await expect
          .poll(() =>
            card.evaluate((element) => {
              const canvas = element
                .closest(".relationships-stage")!
                .querySelector(".relationships-canvas") as HTMLDivElement & {
                _cyreg: { cy: Core };
              };
              const point = canvas._cyreg.cy
                .getElementById(element.getAttribute("data-graph-user-id")!)
                .renderedPosition();
              const bounds = element.getBoundingClientRect(),
                viewport = canvas.getBoundingClientRect();
              return Math.max(
                Math.abs(bounds.x + bounds.width / 2 - viewport.x - point.x),
                Math.abs(bounds.y + bounds.height / 2 - viewport.y - point.y)
              );
            })
          )
          .toBeLessThan(1);
        await expect(card).toHaveAttribute("data-pan-preserved", "true");
      }
      await expect
        .poll(() =>
          card.evaluate((element) => {
            const canvas = element
              .closest(".relationships-stage")!
              .querySelector(".relationships-canvas") as HTMLDivElement & { _cyreg: { cy: Core } };
            const point = canvas._cyreg.cy
              .getElementById(element.getAttribute("data-graph-user-id")!)
              .renderedPosition();
            const box = element.getBoundingClientRect(),
              stage = canvas.getBoundingClientRect();
            return Math.max(
              Math.abs(box.x + box.width / 2 - stage.x - point.x),
              Math.abs(box.y + box.height / 2 - stage.y - point.y)
            );
          })
        )
        .toBeLessThan(1);
      const beforeWheel = await layer.getAttribute("style");
      const wheelPoint = { x: Math.round(point.x), y: Math.round(point.y) };
      await page.mouse.move(wheelPoint.x, wheelPoint.y);
      const wheelBefore = await graph
        .locator(".relationships-canvas")
        .evaluate((element, pointer) => {
          const cy = (element as HTMLDivElement & { _cyreg: { cy: Core } })._cyreg.cy;
          const box = element.getBoundingClientRect();
          return {
            zoom: cy.zoom(),
            x: (pointer.x - box.x - cy.pan().x) / cy.zoom(),
            y: (pointer.y - box.y - cy.pan().y) / cy.zoom(),
          };
        }, wheelPoint);
      await page.mouse.wheel(0, -160);
      await expect(layer).not.toHaveAttribute("style", beforeWheel!);
      await expect
        .poll(() =>
          graph
            .locator(".relationships-canvas")
            .evaluate((element) =>
              (element as HTMLDivElement & { _cyreg: { cy: Core } })._cyreg.cy.zoom()
            )
        )
        .toBeGreaterThanOrEqual(wheelBefore.zoom * 1.12);
      const wheelAfter = await graph
        .locator(".relationships-canvas")
        .evaluate((element, pointer) => {
          const cy = (element as HTMLDivElement & { _cyreg: { cy: Core } })._cyreg.cy;
          const box = element.getBoundingClientRect();
          return {
            zoom: cy.zoom(),
            x: (pointer.x - box.x - cy.pan().x) / cy.zoom(),
            y: (pointer.y - box.y - cy.pan().y) / cy.zoom(),
          };
        }, wheelPoint);
      expect(wheelAfter.zoom).toBeLessThanOrEqual(wheelBefore.zoom * 1.25 + 0.000001);
      expect(wheelAfter.x).toBeCloseTo(wheelBefore.x, 4);
      expect(wheelAfter.y).toBeCloseTo(wheelBefore.y, 4);
      await page.mouse.wheel(0, 160);
      await expect
        .poll(() =>
          graph
            .locator(".relationships-canvas")
            .evaluate((element) =>
              (element as HTMLDivElement & { _cyreg: { cy: Core } })._cyreg.cy.zoom()
            )
        )
        .toBeCloseTo(wheelBefore.zoom, 4);
      await expect(card).toHaveAttribute("style", cardStyle!);
      await expect(card).toHaveAttribute("data-pan-preserved", "true");
      const focusedCards = await graph.locator(".relationships-node").count();
      await graph.getByRole("button", { name: /Весь граф|Fit graph/, exact: true }).click();
      await expect
        .poll(() => graph.locator(".relationships-node").count())
        .toBeGreaterThan(focusedCards);
      const overviewCards = await graph.locator(".relationships-node").count();
      await page.locator(".admin-main").evaluate((element) => element.scrollTo({ top: 0 }));
      await page.screenshot({
        path: testInfo.outputPath(`relationships-overview-${theme}-${width}.png`),
        fullPage: true,
        animations: "disabled",
      });
      await graph.locator('input[type="search"]').press("Enter");
      await expect
        .poll(() => graph.locator(".relationships-node").count())
        .toBeLessThan(overviewCards);
      await graph
        .locator(".relationships-stage")
        .screenshot({ path: testInfo.outputPath(`relationships-${theme}-${width}.png`) });
      await graph
        .locator(".relationships-selection")
        .screenshot({ path: testInfo.outputPath(`relationships-user-${theme}-${width}.png`) });
      await page.locator(".admin-main").evaluate((element) => element.scrollTo({ top: 0 }));
      await page.screenshot({
        path: testInfo.outputPath(`relationships-screen-${theme}-${width}.png`),
        fullPage: true,
        animations: "disabled",
      });
      if (width < 1000) {
        await graph.locator(".relationships-selection").scrollIntoViewIfNeeded();
        await page.screenshot({
          path: testInfo.outputPath(`relationships-details-screen-${theme}-${width}.png`),
          fullPage: true,
          animations: "disabled",
        });
      }
      await noOverflow(graph);
      await graph.getByRole("button", { name: /Снять выделение|Clear selection/ }).click();
      await expect(graph.locator(".relationships-selection")).toHaveCount(0);
      await expect(page).not.toHaveURL(/focus=/);
      await graph.locator('input[type="search"]').press("Enter");
      const parallel = geometry.find((route, index) =>
        geometry.some(
          (other, otherIndex) =>
            index !== otherIndex && route.source === other.source && route.target === other.target
        )
      );
      if (parallel) {
        await graph.locator(".relationships-canvas").evaluate((element, pair) => {
          const cy = (element as HTMLDivElement & { _cyreg: { cy: Core } })._cyreg.cy;
          cy.fit(cy.getElementById(pair.source).union(cy.getElementById(pair.target)), 32);
        }, parallel);
        await page.locator(".admin-main").evaluate((element) => element.scrollTo({ top: 0 }));
        await page.screenshot({
          path: testInfo.outputPath(`relationships-parallel-${theme}-${width}.png`),
          fullPage: true,
          animations: "disabled",
        });
      }
      // Filters reuse the complete layout and hide users without matching edges.
      const loadedWorkers = workers,
        loadedRequests = graphRequests;
      const initial = await graph.locator(".relationships-canvas").evaluate((element) => {
        const cy = (element as HTMLDivElement & { _cyreg: { cy: Core } })._cyreg.cy;
        const referrals = new Set(
          cy
            .edges('[kind="referral"]')
            .connectedNodes()
            .map((node) => node.id())
        );
        const partners = new Set(
          cy
            .edges('[kind="partner"]')
            .connectedNodes()
            .map((node) => node.id())
        );
        return {
          nodes: cy.nodes().length,
          referrals: referrals.size,
          partners: partners.size,
          referralOnly: [...referrals].find((id) => !partners.has(id))!,
          positions: cy.nodes().map((node) => ({ id: node.id(), ...node.position() })),
        };
      });
      expect(initial.referrals).not.toBe(initial.partners);
      const filter = graph.getByRole("button", { name: /Связи|Connections/, exact: true });
      await filter.click();
      await expect(page.getByRole("listbox")).toBeVisible();
      expect(
        await page
          .getByRole("listbox")
          .evaluate((element) => getComputedStyle(element).backgroundImage)
      ).toBe("none");
      await page.screenshot({
        path: testInfo.outputPath(`relationships-filter-menu-${theme}-${width}.png`),
        fullPage: true,
        animations: "disabled",
      });
      await page.getByRole("option", { name: /Рефералы|Referrals/, exact: true }).click();
      await expect(page).toHaveURL(/graph_kind=referral/);
      await expect
        .poll(() =>
          graph.locator(".relationships-canvas").evaluate((element) => {
            const cy = (element as HTMLDivElement & { _cyreg: { cy: Core } })._cyreg.cy;
            return cy.nodes(":visible").length;
          })
        )
        .toBe(initial.referrals);
      await expect(
        graph.locator('.relationships-selection li[data-relationship-kind="partner"]')
      ).toHaveCount(0);
      await graph.locator('input[type="search"]').fill(initial.referralOnly);
      await graph.locator('input[type="search"]').press("Enter");
      await expect(graph.locator(".relationships-node.selected")).toHaveAttribute(
        "data-graph-user-id",
        initial.referralOnly
      );
      await filter.click();
      await page.getByRole("option", { name: /Партнёры|Partners/, exact: true }).click();
      await expect(page).toHaveURL(/graph_kind=partner/);
      await expect(page).not.toHaveURL(/focus=/);
      await expect(graph.locator(".relationships-selection")).toHaveCount(0);
      await expect(graph.locator(".relationships-list summary")).toContainText("0");
      await expect(graph.getByRole("button", { name: /Найти|Find/, exact: true })).toBeDisabled();
      const filtered = await graph.locator(".relationships-canvas").evaluate((element) => {
        const cy = (element as HTMLDivElement & { _cyreg: { cy: Core } })._cyreg.cy;
        return {
          nodes: cy.nodes(":visible").length,
          kinds: cy.edges(":visible").map((edge) => edge.data("kind")),
          positions: cy.nodes().map((node) => ({ id: node.id(), ...node.position() })),
        };
      });
      expect(filtered.nodes).toBe(initial.partners);
      expect(filtered.kinds.every((kind) => kind === "partner")).toBe(true);
      expect(filtered.positions).toEqual(initial.positions);
      expect(workers).toBe(loadedWorkers);
      expect(graphRequests).toBe(loadedRequests);
      await page.locator(".admin-main").evaluate((element) => element.scrollTo({ top: 0 }));
      await page.screenshot({
        path: testInfo.outputPath(`relationships-partners-${theme}-${width}.png`),
        fullPage: true,
        animations: "disabled",
      });
      await page.reload();
      await expect(filter).toContainText(/Партнёры|Partners/);
      await expect(graph.locator(".relationships-stage")).toHaveAttribute("aria-busy", "false");
      await page.goBack();
      await expect(filter).toContainText(/Рефералы|Referrals/);
      await expect(graph.locator(".relationships-node.selected")).toHaveAttribute(
        "data-graph-user-id",
        initial.referralOnly
      );
      await page.goForward();
      await expect(filter).toContainText(/Партнёры|Partners/);
      await expect(graph.locator(".relationships-selection")).toHaveCount(0);
      await filter.click();
      await page.getByRole("option", { name: /Все|All/, exact: true }).click();
      await expect(page).not.toHaveURL(/graph_kind=/);
      await expect
        .poll(() =>
          graph
            .locator(".relationships-canvas")
            .evaluate(
              (element) =>
                (element as HTMLDivElement & { _cyreg: { cy: Core } })._cyreg.cy.nodes(":visible")
                  .length
            )
        )
        .toBe(initial.nodes);
      await graph.locator('input[type="search"]').fill("910001");
      await graph.locator('input[type="search"]').press("Enter");
      await page.reload();
      await expect(graph.locator(".relationships-node.selected")).toHaveAttribute(
        "data-graph-user-id",
        "910001"
      );
      await graph
        .getByRole("button", { name: /К списку пользователей|Back to users/, exact: true })
        .click();
      await expect(page.locator('[data-admin-action="open-relationships-graph"]')).toBeVisible();
      await expect(page).not.toHaveURL(/graph_kind=/);
      await page.screenshot({
        path: testInfo.outputPath(`users-list-${theme}-${width}.png`),
        fullPage: true,
        animations: "disabled",
      });
      await page.goBack();
      await expect(graph).toBeVisible();
      await page.goto(`/demo/runtime/admin/users?theme_preview=${theme}&view=relationships`);
      await expect(graph.locator(".relationships-stage")).toHaveAttribute("aria-busy", "false");
      await expect(graph.locator(".relationships-node.selected")).toHaveCount(0);
      await page.screenshot({
        path: testInfo.outputPath(`relationships-default-${theme}-${width}.png`),
        fullPage: true,
        animations: "disabled",
      });
      if (width === 320 || width === 1440) {
        await page.goto(
          `/demo/runtime/admin/users?theme_preview=${theme}&view=relationships&focus=910001&relationships_scenario=long-identity`
        );
        await expect(graph.locator(".relationships-selection")).toContainText(
          "alexandra.rozhdestvenskaya+partner.operations@very-long-domain.example.com"
        );
        await noOverflow(graph);
        await page.screenshot({
          path: testInfo.outputPath(`relationships-long-${theme}-${width}.png`),
          fullPage: true,
          animations: "disabled",
        });
        if (width === 320) {
          await graph.locator(".relationships-selection").scrollIntoViewIfNeeded();
          await page.screenshot({
            path: testInfo.outputPath(`relationships-long-details-${theme}-${width}.png`),
            fullPage: true,
            animations: "disabled",
          });
        }
      }
      expect(errors).toEqual([]);
    });
  }
}

test("relationship graph omits isolated users and recovers from worker failures", async ({
  page,
}, testInfo) => {
  await page.goto("/demo/runtime/admin/users/910370?theme_preview=dark");
  await expect(page.locator(".admin-user-detail-page")).toBeVisible();
  await expect(page.locator('[data-admin-action="show-in-relationships-graph"]')).toHaveCount(0);
  await page.goto("/demo/runtime/admin/users?theme_preview=dark&view=relationships&focus=910370");
  const graph = page.locator("[data-relationships-graph]");
  await expect(graph.locator(".relationships-stage")).toHaveAttribute("aria-busy", "false");
  await expect(graph.getByRole("status")).toContainText(/нет связей|no connections/);
  await expect(graph.locator('[data-graph-user-id="910370"]')).toHaveCount(0);
  const workerPattern = "**/subscription_webapp_admin.relationships-layout.*.js";
  await page.route(workerPattern, (route) => route.abort());
  await page.reload();
  await expect(graph.getByRole("alert")).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("relationships-error-screen.png"),
    fullPage: true,
    animations: "disabled",
  });
  await page.unroute(workerPattern);
  await graph.getByRole("button", { name: /Обновить|Refresh/, exact: true }).click();
  await expect(graph.getByRole("alert")).toHaveCount(0);
  await expect(graph.locator(".relationships-stage")).toHaveAttribute("aria-busy", "false");
  await expect(graph.locator(".relationships-node").first()).toBeVisible();
  await page.goto("/demo/runtime/admin/partners/partner/10001?theme_preview=dark");
  await page.locator('[data-admin-action="show-partner-in-relationships-graph"]').click();
  await expect(graph.locator(".relationships-node.selected")).toHaveAttribute(
    "data-graph-user-id",
    "910001"
  );
  await page.goto(
    "/demo/runtime/admin/users?theme_preview=light&view=relationships&relationships_scenario=empty"
  );
  await expect(graph.locator(".admin-empty")).toContainText(/связей пока нет|connections yet/);
  await expect(graph.locator(".relationships-stage")).toBeHidden();
  const filter = graph.getByRole("button", { name: /Связи|Connections/, exact: true });
  await filter.click();
  await page.getByRole("option", { name: /Партнёры|Partners/, exact: true }).click();
  await expect(filter).toBeEnabled();
  await expect(page).toHaveURL(/graph_kind=partner/);
  await filter.click();
  await page.getByRole("option", { name: /Все|All/, exact: true }).click();
  await expect(page).not.toHaveURL(/graph_kind=/);
  await page.screenshot({
    path: testInfo.outputPath("relationships-empty-screen.png"),
    fullPage: true,
    animations: "disabled",
  });
});

for (const width of [1440, 768, 390]) {
  test(`hosted payment methods stay inside provider cards at ${width}px`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(adminUrl("settings/payments"));
    const cards = page.locator(".admin-settings-subsection");
    for (const [provider, methods] of [
      ["Cryptomus", ["cryptomus_subscription"]],
      ["CisPay", ["cispay_subscription_card", "cispay_subscription_sbp"]],
    ] as const) {
      const card = cards.filter({
        has: page.locator(`[data-settings-anchor="settings-subsection:payments:${provider}"]`),
      });
      await expect(card).toHaveCount(1);
      const trigger = card.locator(".admin-settings-subsection-trigger");
      await expect(trigger).toBeVisible();
      await trigger.screenshot({
        path: testInfo.outputPath(`${provider.toLowerCase()}-${width}.png`),
      });
      if ((await trigger.getAttribute("data-state")) === "closed") await trigger.click();
      for (const method of methods) {
        const group = card.locator(
          `[data-settings-anchor="settings-field-group:payments:${provider}:${method}"]`
        );
        await expect(group).toBeVisible();
        await expect(group.locator(".admin-setting")).toHaveCount(2);
        await noOverflow(group);
        await group.scrollIntoViewIfNeeded();
        await group.screenshot({ path: testInfo.outputPath(`${method}-${width}.png`) });
      }
      await noOverflow(card);
    }
    await expect(
      cards.filter({ hasText: /Cryptomus · автоплатежи|CisPay · (карта|СБП), автоплатежи/ })
    ).toHaveCount(0);
  });
}

async function noOverflow(element: Locator, vertical = false) {
  const bounds = await element.evaluate((node) => ({
    x: node.scrollWidth - node.clientWidth,
    y: node.scrollHeight - node.clientHeight,
  }));
  expect(bounds.x).toBeLessThanOrEqual(2);
  if (vertical) expect(bounds.y).toBeLessThanOrEqual(2);
}

async function alignedSearch(page: Page) {
  const controls = page.locator(
    ".admin-list-toolbar-search .input, .admin-list-toolbar-search .admin-btn"
  );
  await expect(controls.first()).toBeVisible();
  const heights = await controls.evaluateAll((nodes) =>
    nodes
      .filter((node) => node.getClientRects().length)
      .map((node) => node.getBoundingClientRect().height)
  );
  expect(heights.length).toBeGreaterThanOrEqual(2);
  expect(Math.max(...heights) - Math.min(...heights)).toBeLessThanOrEqual(1);
}

async function copyFullLink(page: Page, field: Locator) {
  const input = field.locator("input");
  const value = await input.inputValue();
  expect(value).toMatch(/^https:\/\//);
  await input.click();
  expect(
    await input.evaluate((node: HTMLInputElement) => node.selectionEnd! - node.selectionStart!)
  ).toBe(value.length);
  await field.locator("button").first().click();
  await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toBe(value);
  await noOverflow(field);
  const heights = await field
    .locator("input, button")
    .evaluateAll((nodes) => nodes.map((node) => node.getBoundingClientRect().height));
  expect(Math.max(...heights) - Math.min(...heights)).toBeLessThanOrEqual(1);
}

for (const [device, viewport] of [
  ["desktop", { width: 1440, height: 900 }],
  ["mobile", { width: 390, height: 844 }],
] as const) {
  test(`promo expiry uses the shared calendar and preserves time on ${device}`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await page.goto(adminUrl("promos"));
    await page.getByRole("button", { name: "Редактировать", exact: true }).first().click();
    const dialog = page.locator(".admin-promo-edit-dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.locator('input[type="datetime-local"]')).toHaveCount(0);
    const trigger = dialog.getByRole("button", { name: "Действует до", exact: true });
    const unlimited = dialog.getByRole("checkbox", { name: "Без ограничения", exact: true });
    await trigger.click();
    const calendar = page.locator(".date-input-popover");
    await expect(calendar).toBeVisible();
    const bounds = await calendar.boundingBox();
    expect(bounds!.x).toBeGreaterThanOrEqual(0);
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(viewport.width);
    await noOverflow(calendar);
    await calendar.locator(".date-input-day:not([data-outside-month])").nth(15).click();
    await expect(calendar).toBeHidden();
    await trigger.click();
    await expect(calendar).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(calendar).toBeHidden();
    await expect(dialog).toBeVisible();
    await expect(trigger).toBeFocused();
    await dialog.getByRole("button", { name: "Очистить дату: Действует до", exact: true }).click();
    await expect(unlimited).toBeChecked();
    await expect(trigger).toBeDisabled();
    await unlimited.uncheck();
    await expect(trigger).toBeEnabled();
    const field = dialog.locator(".date-input-shell");
    await noOverflow(field.locator(".date-input"));
    for (const [part, value] of Object.entries({
      year: "2031",
      month: "05",
      day: "20",
      hour: "14",
      minute: "30",
    })) {
      await field.locator(`[data-segment="${part}"]`).pressSequentially(value);
    }
    await expect(field.locator('[data-segment="year"]')).toHaveAttribute("aria-valuenow", "2031");
    await expect(field.locator('[data-segment="hour"]')).toHaveAttribute("aria-valuenow", "14");
    await expect(field.locator('[data-segment="minute"]')).toHaveAttribute("aria-valuenow", "30");
    await expect(unlimited).not.toBeChecked();
    await expect(dialog.getByRole("button", { name: "Сохранить", exact: true })).toBeEnabled();
    await noOverflow(dialog);
  });

  test(`guest checkout uses shared email validation on ${device}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto("/demo/runtime/login?mock=auth&plan=standard&theme_preview=dark");
    await expect(page.getByRole("heading", { name: "Укажите email", exact: true })).toBeVisible();
    const email = page.locator('.checkout-card input[type="email"]');
    await expect(email).toHaveClass(/input/);
    await expect(email).toHaveAttribute("autocomplete", "email");
    await email.fill("invalid");
    await email.press("Enter");
    await expect(email).toHaveAttribute("aria-invalid", "true");
    await email.fill("ui-regression@example.test");
    await expect(email).not.toHaveAttribute("aria-invalid", "true");
    await expect(email).toHaveValue("ui-regression@example.test");
    await noOverflow(page.locator(".checkout-card"));
  });

  test(`subscription extension uses the shared calendar on ${device}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto(
      "/demo/runtime/admin/users/ms_100000000000400080000000000de418?theme_preview=dark"
    );
    const action = page.locator(".admin-user-action-sheet--extend");
    await action.getByRole("button", { name: "Указать дату", exact: true }).click();
    await expect(action.locator('input[type="date"]')).toHaveCount(0);
    const trigger = action.getByRole("button", { name: "Новая дата окончания", exact: true });
    const submit = action.getByRole("button", { name: "Изменить срок", exact: true });
    await expect(submit).toBeDisabled();
    await trigger.press("Enter");
    const calendar = page.locator(".date-input-popover");
    await expect(calendar).toBeVisible();
    await expect(calendar.locator(".date-input-day[data-disabled]").first()).toBeVisible();
    const bounds = await calendar.boundingBox();
    expect(bounds!.x).toBeGreaterThanOrEqual(0);
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(viewport.width);
    await noOverflow(calendar);
    const availableDay = calendar.locator(".date-input-day:not([data-disabled])").first();
    const selectedDate = await availableDay.getAttribute("data-value");
    const tomorrow = new Date();
    tomorrow.setUTCDate(tomorrow.getUTCDate() + 1);
    expect(selectedDate! >= tomorrow.toISOString().slice(0, 10)).toBe(true);
    await availableDay.click();
    await page.keyboard.press("Escape");
    await expect(calendar).toBeHidden();
    await expect(trigger).toBeFocused();
    await expect(submit).toBeEnabled();
    await trigger.click();
    await expect(calendar.locator(".date-input-day[data-selected]")).toHaveAttribute(
      "data-value",
      selectedDate!
    );
    await page.keyboard.press("Escape");
    await expect(trigger).toBeFocused();
    await action
      .getByRole("button", { name: "Очистить дату: Новая дата окончания", exact: true })
      .click();
    await expect(submit).toBeDisabled();
    await expect(trigger).toBeFocused();
    await noOverflow(action);
    expect(errors).toEqual([]);
  });

  test(`account merge with email confirmation fits on ${device}`, async ({ page }, testInfo) => {
    await page.setViewportSize(viewport);
    await page.goto(
      "/demo/runtime/app/?mock=checkout-addons&theme_preview=dark&telegram_auth=account_merge_required"
    );
    const dialog = page.locator(".account-merge-dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("heading", { name: "Объединение аккаунтов" })).toBeVisible();
    await expect(dialog.locator(".account-merge-form input")).toHaveValue("123456");
    await expect(
      dialog.getByRole("button", { name: "Подтвердить через Google", exact: true })
    ).toBeVisible();
    await expect(
      dialog.getByRole("button", { name: "Подтвердить через Discord", exact: true })
    ).toBeVisible();
    await expect(
      dialog.getByRole("button", { name: "Подтвердить через Yandex", exact: true })
    ).toBeVisible();
    await noOverflow(dialog);
    const bounds = await dialog.boundingBox();
    expect(bounds).not.toBeNull();
    expect(bounds!.x).toBeGreaterThanOrEqual(0);
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(viewport.width);
    await dialog.screenshot({ path: testInfo.outputPath(`account-merge-email-${device}.png`) });
    await dialog.locator(".account-merge-form input").fill("000000");
    await dialog.getByRole("button", { name: "Объединить аккаунты", exact: true }).click();
    await expect(dialog).toContainText("Неверный код");
    await dialog.locator(".account-merge-form input").fill("123456");
    await dialog.getByRole("button", { name: "Объединить аккаунты", exact: true }).click();
    await expect(dialog).toContainText("Аккаунты объединены");
  });

  test(`provider merge works with email disabled on ${device}`, async ({ page }, testInfo) => {
    await page.setViewportSize(viewport);
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto(
      "/demo/runtime/app/?mock=checkout-addons&theme_preview=dark&merge_demo=provider-only&external_auth=yandex:account_merge_required"
    );
    const dialog = page.locator(".account-merge-dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText("Подтверждённый профиль Yandex");
    await expect(dialog.locator(".account-merge-form")).toHaveCount(0);
    await expect(
      dialog.getByRole("button", { name: "Подтвердить через Discord", exact: true })
    ).toBeVisible();
    await noOverflow(dialog);
    await dialog.screenshot({ path: testInfo.outputPath(`account-merge-providers-${device}.png`) });
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    expect(errors).toEqual([]);

    await page.goto(
      "/demo/runtime/app/?mock=checkout-addons&theme_preview=dark&merge_demo=provider-only&external_auth=google:account_merge_ready"
    );
    await expect(dialog).toContainText("Вход в текущий аккаунт подтверждён");
    await expect(dialog.locator("input")).toHaveCount(0);
    await dialog.getByRole("button", { name: "Объединить аккаунты", exact: true }).click();
    await expect(dialog).toContainText("Аккаунты объединены");
    expect(errors).toEqual([]);
  });

  test(`future provider can reconfirm account ownership on ${device}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto(
      "/demo/runtime/app/?mock=checkout-addons&theme_preview=dark&merge_demo=future&external_auth=discord:account_merge_required"
    );
    const dialog = page.locator(".account-merge-dialog");
    const button = dialog.getByRole("button", {
      name: "Подтвердить через future-provider",
      exact: true,
    });
    await expect(button).toBeVisible();
    await noOverflow(dialog);
    await page.route("**/auth/future-provider/start?*", (route) => route.fulfill({ body: "" }));
    const request = page.waitForRequest("**/auth/future-provider/start?*");
    await button.click();
    const url = new URL((await request).url());
    expect(url.searchParams.get("purpose")).toBe("merge");
    expect(url.searchParams.get("return_to")).toBe("/settings/security");
  });

  test(`registered future providers can create and link accounts on ${device}`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize(viewport);
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto("/demo/runtime/login?mock=auth&provider_demo=future&theme_preview=dark");
    const login = page.getByRole("button", { name: "Войти через future-provider", exact: true });
    await expect(login).toBeVisible();
    await expect(login.locator('[data-provider-logo="future-provider"]')).toBeVisible();
    await expect(page.locator('[data-provider-logo="google"]')).toBeVisible();
    await expect(page.locator('[data-provider-logo="yandex"]')).toBeVisible();
    await expect(page.locator('[data-provider-logo="discord"]')).toBeVisible();
    await noOverflow(page.locator(".auth-provider-stack"));
    await page
      .locator(".auth-provider-stack")
      .screenshot({ path: testInfo.outputPath(`future-provider-login-${device}.png`) });
    await page.route("**/auth/future-provider/start?*", (route) => route.fulfill({ body: "" }));
    const loginRequest = page.waitForRequest("**/auth/future-provider/start?*");
    await login.click();
    expect(new URL((await loginRequest).url()).searchParams.get("purpose")).toBe("login");

    await page.goto(
      "/demo/runtime/settings/security?mock=future-providers&provider_demo=future&theme_preview=dark"
    );
    const methods = page.locator(".security-methods");
    const row = methods
      .locator(".settings-row")
      .filter({ has: page.locator('[data-provider-logo="future-provider"]') });
    await expect(row).toContainText("future-provider");
    await expect(row).toContainText("Привязать аккаунт");
    await expect(methods).toContainText("Discord user");
    await noOverflow(methods);
    await methods.screenshot({
      path: testInfo.outputPath(`future-provider-security-${device}.png`),
    });
    const linkRequest = page.waitForRequest("**/auth/future-provider/start?*");
    await row.click();
    expect(new URL((await linkRequest).url()).searchParams.get("purpose")).toBe("link");

    await page.goto(
      "/demo/runtime/settings/security?mock=future-providers&provider_demo=future&future_linked=1&theme_preview=dark"
    );
    await expect(methods).toContainText("Future user");
    await expect(
      methods.getByRole("button", { name: "Отвязать future-provider", exact: true })
    ).toBeVisible();
    expect(errors).toEqual([]);
  });

  test(`gift navigation initializes from the profile on ${device}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    const url = (scenario: string) =>
      `/demo/runtime/app/?mock=partner-referral-disabled&theme_preview=dark&gift_demo=${scenario}`;
    const navigation = page.locator(".bottom-nav");
    const bonuses = navigation.getByRole("button", { name: "Бонусы", exact: true });

    // The demo /me response deliberately exposes id, never the admin-only user_id.
    await page.goto(url("empty"));
    await expect(bonuses).toBeVisible();
    await bonuses.click();
    await expect(page.locator(".gift-list")).toContainText("Здесь появятся");
    await expect(
      page.locator(".gift-entry").getByRole("button", { name: "Подарить" })
    ).toBeVisible();

    for (const scenario of ["loading", "error"]) {
      await page.goto(url(scenario));
      await expect(bonuses).toBeVisible();
      await bonuses.click();
      const entry = page.locator(".gift-entry");
      await expect(entry).toBeVisible();
      await expect(entry.getByRole("button", { name: "Подарить" })).toBeVisible();
      if (scenario === "loading")
        await expect(entry.locator(".gift-list")).toContainText("Загрузка");
      else await expect(entry.getByRole("alert")).toBeVisible();
    }

    await page.goto(url("disabled"));
    await expect(bonuses).toBeVisible();
    await bonuses.click();
    await expect(page.locator(".gift-entry .copy-link-field").first()).toBeVisible();
    await expect(page.locator(".gift-entry").getByRole("button", { name: "Подарить" })).toHaveCount(
      0
    );
    await page.goto(url("disabled-empty"));
    await expect(navigation).toBeVisible();
    await expect(navigation.getByRole("button", { name: "Партнёрка", exact: true })).toBeVisible();
    await expect(bonuses).toHaveCount(0);

    await page.goto(`${url("received")}&gift=${"R".repeat(43)}`);
    await expect(page.locator(".gift-dialog")).toBeVisible();
    await expect(
      page.locator(".gift-dialog").getByRole("button", { name: "Активировать подарок" })
    ).toBeVisible();
    expect(errors).toEqual([]);
  });

  test(`bonus cards share corners and spacing on ${device}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto(
      "/demo/runtime/app/?mock=checkout-addons&path=/invite&gift_demo=empty&theme_preview=dark"
    );
    await expect(page.locator(".gift-entry")).toBeVisible();
    await expect(page.locator(".gift-entry")).toHaveCSS("background-image", "none");
    const layout = await page.locator("main.content").evaluate((node) => {
      const gift = node.querySelector<HTMLElement>(".gift-entry")!;
      const promo = node
        .querySelector<HTMLElement>(".promo-heading")!
        .closest<HTMLElement>(".card")!;
      const referral = node.querySelector<HTMLElement>(".bonus-card")!;
      return {
        radii: [gift, promo, referral].map((card) => getComputedStyle(card).borderRadius),
        gaps: [
          promo.getBoundingClientRect().top - gift.getBoundingClientRect().bottom,
          referral.getBoundingClientRect().top - promo.getBoundingClientRect().bottom,
        ],
      };
    });
    expect(new Set(layout.radii).size).toBe(1);
    expect(Math.abs(layout.gaps[0] - layout.gaps[1])).toBeLessThanOrEqual(1);
    await noOverflow(page.locator(".gift-entry"));
  });

  test(`remaining admin lists reuse toolbar controls on ${device}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto(adminUrl("partners"));
    for (const tab of [1, 2, 3]) {
      await page.locator('.partners-toolbar [role="tab"]').nth(tab).click();
      const toolbar = page.locator(".partner-list-toolbar");
      await expect(toolbar).toBeVisible();
      await alignedSearch(page);
      await expect(toolbar.locator(".admin-field-label > span")).toHaveCSS("font-size", "11px");
      await expect(toolbar.locator(".admin-field-label > span")).toHaveCSS(
        "text-transform",
        "uppercase"
      );
      await noOverflow(toolbar);
      const input = toolbar.locator('input[type="search"]');
      await input.fill("missing-user-example");
      await input.press("Enter");
      await expect(toolbar.locator(".admin-list-toolbar-summary strong")).toHaveText("0");
      await input.fill("");
      await input.press("Enter");
      await expect(toolbar.locator(".admin-list-toolbar-summary strong")).not.toHaveText("0");
      await toolbar.locator(".admin-select-trigger").click();
      await expect(page.getByRole("option").first()).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(toolbar).toBeVisible();
    }
    for (const route of ["logs", "support", "backups"]) {
      await page.goto(adminUrl(route));
      const toolbar = page.locator(".admin-list-toolbar");
      await expect(toolbar).toBeVisible();
      await noOverflow(toolbar);
      if (route === "backups") {
        await toolbar.getByRole("button", { name: "Обновить", exact: true }).click();
        await expect(page.locator(".backups-restore-card")).toBeVisible();
        const radios = page.getByRole("radio");
        const choices = page.locator(".backups-archive-choice");
        await expect(radios).toHaveCount(2);
        await expect(page.getByRole("checkbox", { name: "БД" })).toBeDisabled();
        await choices.nth(1).locator("span").last().click();
        await expect(radios.nth(1)).toBeChecked();
        await expect(page.getByRole("checkbox", { name: "БД" })).toBeEnabled();
        await expect(page.locator(".backups-selected-name")).toHaveText(
          await choices.nth(1).innerText()
        );
        const confirmation = page.locator(".backups-confirmation input");
        await confirmation.fill(await choices.nth(1).innerText());
        await radios.nth(1).press("ArrowUp");
        await expect(radios.first()).toBeChecked();
        await expect(confirmation).toHaveValue("");
        await noOverflow(page.locator(".backups-table"));
        if (device === "mobile") {
          await expect(page.locator(".backups-table thead th")).toHaveCount(3);
          const target = await choices.first().boundingBox();
          expect(target?.height).toBeGreaterThanOrEqual(44);
        }
      } else {
        await alignedSearch(page);
        await toolbar.getByRole("button", { name: "Применить", exact: true }).click();
        if (route === "support") {
          await expect(toolbar.locator(".admin-list-toolbar-summary")).toHaveCount(0);
          if (device === "mobile") {
            await expect(toolbar.locator(".admin-list-toolbar-filters")).toBeHidden();
            await toolbar.getByRole("button", { name: "Фильтры" }).click();
          }
          const filters = page.locator(
            device === "mobile"
              ? ".support-filter-dialog .admin-select-trigger"
              : ".support-list-toolbar .admin-select-trigger"
          );
          await expect(filters).toHaveCount(3);
          for (let index = 0; index < 3; index++) {
            await filters.nth(index).click();
            await expect(page.getByRole("option").first()).toBeVisible();
            await page.keyboard.press("Escape");
          }
          if (device === "mobile") {
            await page.locator(".support-filter-dialog .dialog-close-button").click();
            await page.setViewportSize({ width: 390, height: 460 });
            const content = page.locator(".admin-content");
            const heading = page.locator(".admin-header");
            await expect
              .poll(() =>
                content.evaluate((element) => element.scrollHeight - element.clientHeight)
              )
              .toBeGreaterThan(120);
            const headingTop = await heading.evaluate(
              (element) => element.getBoundingClientRect().top
            );
            await content.evaluate((element) => (element.scrollTop = 120));
            await expect
              .poll(() => heading.evaluate((element) => element.getBoundingClientRect().top))
              .toBeLessThan(headingTop - 60);
            await page.setViewportSize(viewport);
          }
        }
      }
    }
    expect(errors).toEqual([]);
  });

  test(`shared list controls and gift creation remain consistent on ${device}`, async ({
    page,
    context,
  }) => {
    await page.setViewportSize(viewport);
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto(adminUrl("users"));
    await expect(page.locator(".admin-users-search-button")).toBeVisible();
    await alignedSearch(page);
    if (device === "mobile") {
      await expect(page.locator(".admin-list-toolbar-filters")).toBeHidden();
      await page.evaluate(() => {
        document.documentElement.style.setProperty("--telegram-fullscreen-fallback-top", "96px");
      });
      await page.locator(".admin-users-filter-toggle").click();
      const dialog = page.locator(".admin-users-filter-dialog");
      await expect(dialog).toBeVisible();
      await dialog.locator('.admin-select-trigger[aria-label="Фильтр"]').click();
      const menu = page.locator(".admin-select-content[data-state='open']");
      const menuViewport = menu.locator(".admin-select-viewport");
      await expect(page.getByRole("option").first()).toBeVisible();
      const menuBounds = await menu.boundingBox();
      expect(menuBounds).not.toBeNull();
      expect(menuBounds!.y).toBeGreaterThanOrEqual(96);
      expect(menuBounds!.y + menuBounds!.height).toBeLessThanOrEqual(viewport.height - 12);
      const overflow = await menuViewport.evaluate((node) => node.scrollHeight - node.clientHeight);
      expect(overflow).toBeGreaterThan(0);
      await menuViewport.evaluate((node) => {
        node.scrollTop = node.scrollHeight;
      });
      await expect(menu.getByRole("option").last()).toBeInViewport();
      await page.keyboard.press("Escape");
      await expect(dialog).toBeVisible();
      await dialog.locator(".dialog-head button").click();
    }

    await page.goto(adminUrl("gifts"));
    await expect(page.locator(".admin-pagination-jump-input")).toBeVisible();
    const currentPage = page.locator(".admin-pagination-page[aria-current='page']");
    await expect(currentPage).toHaveCount(1);
    const selectedColor = await currentPage.evaluate(
      (button) => getComputedStyle(button).backgroundColor
    );
    for (const button of await page
      .locator(".admin-pagination-page:not([aria-current='page'])")
      .all()) {
      expect(await button.evaluate((node) => getComputedStyle(node).backgroundColor)).not.toBe(
        selectedColor
      );
    }
    const paginationHeights = await page
      .locator(".admin-pagination input, .admin-pagination button")
      .evaluateAll((nodes) =>
        nodes
          .filter((node) => node.getClientRects().length)
          .map((node) => node.getBoundingClientRect().height)
      );
    expect(paginationHeights.length).toBeGreaterThan(2);
    expect(Math.max(...paginationHeights) - Math.min(...paginationHeights)).toBeLessThanOrEqual(1);
    const rows = page.locator(
      device === "desktop" ? ".gift-desktop tbody tr" : ".gift-mobile-card"
    );
    await expect(rows.first()).toBeVisible();
    await alignedSearch(page);
    await expect(page.locator(".admin-list-toolbar-filters")).toBeVisible();
    await page.locator('.gifts-toolbar .admin-select-trigger[aria-label="Источник"]').click();
    await page.getByRole("option", { name: "От администратора", exact: true }).click();
    await expect(rows).toHaveCount(1);
    const provider = rows.first().locator(".admin-payment-provider");
    await expect(provider).toContainText("От администратора");
    await expect(provider.locator(".admin-payment-provider-logo")).toHaveText("🎁");
    await rows.first().locator(".details-toggle").click();
    const details = page.locator(".admin-gift-dialog");
    await expect(details.locator(".admin-payment-provider-logo")).toHaveText("🎁");
    await copyFullLink(page, details.locator(".copy-link-field"));
    await noOverflow(details.locator(".dialog-body-scroll > .scroll-area__viewport"), true);
    await details.locator(".dialog-head button").click();

    await page.getByRole("button", { name: "Создать подарок", exact: true }).click();
    const creation = page.locator(".admin-gift-create-dialog");
    const tariff = creation.locator(".gift-create-plan .admin-select-trigger").first();
    await expect(tariff).toBeVisible();
    const initial = await tariff.innerText();
    await tariff.click();
    await expect(page.getByRole("option").first()).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(creation).toBeVisible();
    await expect(tariff).toHaveText(initial);
    await expect(creation.locator("select")).toHaveCount(0);
    const limits = creation.locator(".gift-create-limits .admin-select-trigger");
    await expect(limits).toHaveCount(3);
    await limits.first().click();
    await page.keyboard.press("End");
    await page.keyboard.press("Enter");
    await creation.locator('input[type="email"]').fill("friend@example.com");
    await noOverflow(creation.locator(".dialog-body-scroll > .scroll-area__viewport"), true);
    await creation.locator('button[type="submit"]').click();
    await expect(details.locator(".copy-link-field")).toBeVisible();
    await expect(details).toContainText("0.00");
    await expect(details).toContainText("friend@example.com");
    await noOverflow(details.locator(".dialog-body-scroll > .scroll-area__viewport"), true);
    await details.locator(".dialog-head button").click();
    await expect(rows).toHaveCount(25);
    const firstRow = await rows.first().innerText();
    await page.getByRole("button", { name: "Далее", exact: true }).click();
    await expect.poll(() => rows.first().innerText()).not.toBe(firstRow);
    await page.locator('.gifts-toolbar input[type="search"]').fill("missing-gift-ui-regression");
    await page.getByRole("button", { name: "Найти", exact: true }).click();
    await expect(page.getByText("Подарки не найдены", { exact: true })).toBeVisible();
    expect(errors).toEqual([]);
  });

  test(`shared copy field, payment provider and manual controls render on ${device}`, async ({
    page,
    context,
  }, testInfo) => {
    await page.setViewportSize(viewport);
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    // Keep the actual UI; seed the operation and both confirmation variants.
    await page.addInitScript(() => {
      type Props = {
        api: (path: string, options?: RequestInit) => Promise<Record<string, unknown>>;
      };
      type Bundle = { mount: (target: HTMLElement, props: Props) => unknown };
      let bundle: Bundle | undefined;
      Object.defineProperty(window, "SubscriptionWebAppAdmin", {
        configurable: true,
        get: () => bundle,
        set(value: Bundle) {
          const mount = value.mount;
          value.mount = (target, props) =>
            mount(target, {
              ...props,
              api: async (path, options) => {
                const result = await props.api(path, options);
                if (path.split("?")[0] === "/admin/payments" && Array.isArray(result.payments)) {
                  return {
                    ...result,
                    payments: result.payments.map((payment, index) =>
                      index ? payment : { ...payment, provider: "admin_gift", amount: 0 }
                    ),
                  };
                }
                if (/^\/admin\/payments\/\d+$/.test(path) && result.payment) {
                  return {
                    ...result,
                    payment: {
                      ...result.payment,
                      can_manual_finalize: true,
                      can_reverse: true,
                      manual_finalize_requires_promo_confirmation: true,
                      manual_finalize_requires_context_confirmation: true,
                      manual_finalize_warnings: ["active_subscription_end_changed"],
                      promo_code_id: 14,
                    },
                  };
                }
                return result;
              },
            });
          bundle = value;
        },
      });
    });
    await page.goto(adminUrl("payments"));
    await expect(page.locator(".admin-list-toolbar")).toBeVisible();
    const rows = page.locator(
      device === "desktop" ? ".admin-payments-table tbody tr" : ".admin-payment-mobile-card"
    );
    await expect(rows.first().locator(".admin-payment-provider-name")).toHaveText(
      "От администратора"
    );
    await expect(rows.first().locator(".admin-payment-provider-logo")).toHaveText("🎁");
    await alignedSearch(page);
    const summary = page.locator(".admin-list-toolbar-summary");
    const gap = await summary.evaluate((node) => {
      const label = node.querySelector("span")!.getBoundingClientRect();
      const count = node.querySelector("strong")!.getBoundingClientRect();
      return count.left - label.right;
    });
    expect(gap).toBeLessThanOrEqual(8);
    const search = page.locator('.admin-list-toolbar input[type="search"]');
    await search.fill("not-a-real-user@example.invalid");
    await search.press("Enter");
    await expect(summary.locator("strong")).toHaveText("0");
    await expect(rows).toHaveCount(0);
    await search.fill("");
    await search.press("Enter");
    await expect(rows.first()).toBeVisible();
    await noOverflow(page.locator(".admin-list-toolbar"));
    await rows
      .first()
      .getByRole("button", { name: /Открыть.*плат/ })
      .click();
    const paymentDialog = page.locator(".admin-payment-dialog");
    await paymentDialog.getByRole("button", { name: "Провести платёж", exact: true }).click();
    const reason = paymentDialog.getByRole("textbox", { name: "Причина", exact: true });
    await expect(reason).toHaveClass(/textarea/);
    await expect(reason).toHaveAttribute("maxlength", "500");
    const confirm = paymentDialog.getByRole("button", { name: "Подтвердить", exact: true });
    const conflict = paymentDialog.getByRole("checkbox", { name: /Применить сохранённые условия/ });
    await expect(conflict).toHaveClass(/ui-checkbox/);
    await expect(confirm).toBeDisabled();
    await reason.fill("UI regression reason");
    await expect(confirm).toBeDisabled();
    await conflict.press("Space");
    await expect(conflict).toBeChecked();
    await expect(confirm).toBeDisabled();
    const contextConfirmation = paymentDialog.getByRole("checkbox", {
      name: /История проверена: эта покупка ещё не начислена/,
    });
    await expect(contextConfirmation).toHaveClass(/ui-checkbox/);
    await contextConfirmation.press("Space");
    await expect(contextConfirmation).toBeChecked();
    await expect(confirm).toBeEnabled();
    await noOverflow(paymentDialog);
    await paymentDialog.screenshot({
      path: testInfo.outputPath(`payment-confirmation-${device}.png`),
    });
    await paymentDialog.getByRole("button", { name: "Отмена", exact: true }).click();
    await paymentDialog.getByRole("button", { name: "Отменить платёж", exact: true }).click();
    const restore = paymentDialog.getByRole("checkbox", {
      name: "Вернуть это использование промокоду",
      exact: true,
    });
    await expect(restore).toHaveClass(/ui-checkbox/);
    await expect(restore).toBeChecked();
    await restore.press("Space");
    await expect(restore).not.toBeChecked();
    await reason.fill("UI regression reason");
    await expect(confirm).toBeEnabled();
    await noOverflow(paymentDialog);
    await paymentDialog.getByRole("button", { name: "Закрыть", exact: true }).last().click();
    await page.goto("/demo/runtime/app/?mock=checkout-addons&path=/invite&theme_preview=dark");
    await expect(page.locator(".gift-entry .copy-link-field").first()).toBeVisible();
    await copyFullLink(page, page.locator(".gift-entry .copy-link-field").first());
    const referralField = page.locator(".bonus-card .copy-link-field").first();
    await copyFullLink(page, referralField);
    await referralField.getByRole("button", { name: /QR/ }).click();
    await expect(page.locator(".link-qr-tile img")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.locator(".link-qr-tile")).toHaveCount(0);
  });
}
