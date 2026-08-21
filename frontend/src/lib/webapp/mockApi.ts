import { buildAdminDemoFixtures } from "./mockApi/adminFixtures";
import { adminFallbackResponse } from "./mockApi/adminFallback";
import { defaultClone, type MockApiContext } from "./mockApi/dataset";
import { demoApiResponse } from "./mockApi/datasetApi";
import { partnerProgramDemoResponse } from "./mockApi/partnerProgramResponse";
import { webappFallbackResponse } from "./mockApi/webappFallback";

export async function mockApi(
  path: string,
  options: RequestInit = {},
  context: MockApiContext = {}
): Promise<unknown> {
  const {
    currentLang = "ru",
    normalizeLangCode = (value: unknown) => String(value || "ru"),
    clone = defaultClone,
  } = context;
  await new Promise((resolve) => window.setTimeout(resolve, 120));
  const cleanPath = String(path || "").split("?")[0];
  const resolvedContext: MockApiContext = { clone, currentLang, normalizeLangCode };
  const demoResponse = demoApiResponse(path, cleanPath, options, resolvedContext);
  if (demoResponse !== undefined) return demoResponse;
  const partnerResponse = partnerProgramDemoResponse(path, cleanPath, options, resolvedContext);
  if (partnerResponse !== undefined) return partnerResponse;
  const fixtures = buildAdminDemoFixtures();
  const adminResponse = adminFallbackResponse(path, cleanPath, options, resolvedContext, fixtures);
  if (adminResponse !== undefined) return adminResponse;
  return webappFallbackResponse(path, cleanPath, options, resolvedContext, fixtures);
}
