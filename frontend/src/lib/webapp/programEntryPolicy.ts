export type ProgramEntryPlacement = {
  bonusesNavigationVisible: boolean;
  partnerNavigationVisible: boolean;
  partnerSettingsVisible: boolean;
  promoSettingsVisible: boolean;
};

export function resolveProgramEntryPlacement({
  partnerProgramEnabled,
  referralProgramEnabled,
  giftsAvailable = false,
}: {
  partnerProgramEnabled: boolean;
  referralProgramEnabled: boolean;
  giftsAvailable?: boolean;
}): ProgramEntryPlacement {
  return {
    bonusesNavigationVisible: referralProgramEnabled || giftsAvailable,
    partnerNavigationVisible: partnerProgramEnabled && !referralProgramEnabled,
    partnerSettingsVisible: partnerProgramEnabled && referralProgramEnabled,
    promoSettingsVisible: !referralProgramEnabled,
  };
}
