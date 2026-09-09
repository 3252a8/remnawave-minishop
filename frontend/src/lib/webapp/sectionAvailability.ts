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
  section,
  supportEnabled = true,
}: SectionAvailabilityInput) {
  if (section === "admin" && !isAdmin) return "settings";
  if (section === "devices" && !devicesEnabled) return "home";
  // Bonuses also hosts gifts and promo activation independently of referrals.
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
  if (section === "notifications") return "settings";
  if (section === "security") return "settings";
  if (section === "partner" && partnerSettingsVisible) return "settings";
  if (section === "install" || section === "trial") return "home";
  return section;
}
