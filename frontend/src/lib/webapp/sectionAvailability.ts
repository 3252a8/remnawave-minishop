type SectionAvailabilityInput = {
  devicesEnabled?: boolean;
  installGuidesAvailable?: boolean;
  isAdmin?: boolean;
  partnerProgramEnabled?: boolean;
  referralProgramEnabled?: boolean;
  section: string;
  supportEnabled?: boolean;
};

export function resolveAvailableWebappSection({
  devicesEnabled = false,
  installGuidesAvailable = false,
  isAdmin = false,
  partnerProgramEnabled = false,
  referralProgramEnabled = true,
  section,
  supportEnabled = true,
}: SectionAvailabilityInput) {
  if (section === "admin" && !isAdmin) return "settings";
  if (section === "devices" && !devicesEnabled) return "home";
  if (section === "invite" && !referralProgramEnabled) return "home";
  if (section === "partner" && !partnerProgramEnabled) return "home";
  if (section === "support" && !supportEnabled) return "home";
  if (section === "install" && !installGuidesAvailable) return "home";
  return section;
}

export function activeTabForWebappSection(
  section: string,
  { partnerSettingsVisible = false }: { partnerSettingsVisible?: boolean } = {}
) {
  if (section === "admin") return "settings";
  if (section === "security") return "settings";
  if (section === "partner" && partnerSettingsVisible) return "settings";
  if (section === "install" || section === "trial") return "home";
  return section;
}
