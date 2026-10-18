from bot.app.web.partner_schemas import (
    AdminPartnerApplicationDecisionIn,
    AdminPartnerApplicationOut,
    AdminPartnerBalanceAdjustmentIn,
    AdminPartnerBulkReferralImportPreviewOut,
    AdminPartnerBulkReferralImportResultOut,
    AdminPartnerCreateIn,
    AdminPartnerRateIn,
    AdminPartnerReferralImportIn,
    AdminPartnerReferralImportPreviewOut,
    AdminPartnerReferralImportResultOut,
    AdminPartnerRequisitesOut,
    AdminPartnerStatusIn,
    AdminPartnerWithdrawalOut,
    AdminPartnerWithdrawalTransitionIn,
    PartnerProfileOut,
)
from bot.app.web.route_contracts import (
    BOOLEAN_SCHEMA,
    RouteContract,
    ok_envelope_for,
    ok_envelope_with,
)

PARTNER_ADMIN_ROUTE_CONTRACTS: dict[str, RouteContract] = {
    "admin_partner_attention_route": RouteContract(response_schema=ok_envelope_with()),
    "admin_partner_overview_route": RouteContract(response_schema=ok_envelope_with()),
    "admin_partners_list_route": RouteContract(response_schema=ok_envelope_with()),
    "admin_partner_detail_route": RouteContract(
        response_schema=ok_envelope_with({"has_relationships": BOOLEAN_SCHEMA})
    ),
    "admin_partner_create_route": RouteContract(
        request_model=AdminPartnerCreateIn,
        response_schema=ok_envelope_for(PartnerProfileOut, key="partner"),
        models=(AdminPartnerCreateIn, PartnerProfileOut),
    ),
    "admin_partner_referral_import_preview_route": RouteContract(
        response_schema=ok_envelope_for(AdminPartnerReferralImportPreviewOut, key="preview"),
        models=(AdminPartnerReferralImportPreviewOut,),
    ),
    "admin_partner_referral_import_route": RouteContract(
        request_model=AdminPartnerReferralImportIn,
        response_schema=ok_envelope_for(AdminPartnerReferralImportResultOut, key="result"),
        models=(AdminPartnerReferralImportIn, AdminPartnerReferralImportResultOut),
    ),
    "admin_partner_bulk_referral_import_preview_route": RouteContract(
        response_schema=ok_envelope_for(
            AdminPartnerBulkReferralImportPreviewOut,
            key="preview",
        ),
        models=(AdminPartnerBulkReferralImportPreviewOut,),
    ),
    "admin_partner_bulk_referral_import_route": RouteContract(
        request_model=AdminPartnerReferralImportIn,
        response_schema=ok_envelope_for(
            AdminPartnerBulkReferralImportResultOut,
            key="result",
        ),
        models=(AdminPartnerReferralImportIn, AdminPartnerBulkReferralImportResultOut),
    ),
    "admin_partner_rate_route": RouteContract(
        request_model=AdminPartnerRateIn,
        response_schema=ok_envelope_for(PartnerProfileOut, key="partner"),
        models=(AdminPartnerRateIn, PartnerProfileOut),
    ),
    "admin_partner_balance_adjustment_route": RouteContract(
        request_model=AdminPartnerBalanceAdjustmentIn,
        response_schema=ok_envelope_with(),
        models=(AdminPartnerBalanceAdjustmentIn,),
    ),
    "admin_partner_pause_route": RouteContract(
        request_model=AdminPartnerStatusIn,
        response_schema=ok_envelope_for(PartnerProfileOut, key="partner"),
        models=(AdminPartnerStatusIn, PartnerProfileOut),
    ),
    "admin_partner_resume_route": RouteContract(
        request_model=AdminPartnerStatusIn,
        response_schema=ok_envelope_for(PartnerProfileOut, key="partner"),
        models=(AdminPartnerStatusIn, PartnerProfileOut),
    ),
    "admin_partner_close_route": RouteContract(
        request_model=AdminPartnerStatusIn,
        response_schema=ok_envelope_for(PartnerProfileOut, key="partner"),
        models=(AdminPartnerStatusIn, PartnerProfileOut),
    ),
    "admin_partner_link_rotate_route": RouteContract(
        response_schema=ok_envelope_for(PartnerProfileOut, key="partner"),
        models=(PartnerProfileOut,),
    ),
    "admin_partner_applications_route": RouteContract(response_schema=ok_envelope_with()),
    "admin_partner_application_detail_route": RouteContract(
        response_schema=ok_envelope_for(AdminPartnerApplicationOut, key="application"),
        models=(AdminPartnerApplicationOut,),
    ),
    "admin_partner_application_approve_route": RouteContract(
        request_model=AdminPartnerApplicationDecisionIn,
        response_schema=ok_envelope_with(),
        models=(AdminPartnerApplicationDecisionIn,),
    ),
    "admin_partner_application_reject_route": RouteContract(
        request_model=AdminPartnerApplicationDecisionIn,
        response_schema=ok_envelope_for(AdminPartnerApplicationOut, key="application"),
        models=(AdminPartnerApplicationDecisionIn, AdminPartnerApplicationOut),
    ),
    "admin_partner_application_reopen_route": RouteContract(
        response_schema=ok_envelope_for(AdminPartnerApplicationOut, key="application"),
        models=(AdminPartnerApplicationOut,),
    ),
    "admin_partner_withdrawals_route": RouteContract(response_schema=ok_envelope_with()),
    "admin_partner_withdrawal_detail_route": RouteContract(
        response_schema=ok_envelope_for(AdminPartnerWithdrawalOut, key="withdrawal"),
        models=(AdminPartnerWithdrawalOut,),
    ),
    "admin_partner_withdrawal_reveal_route": RouteContract(
        response_schema=ok_envelope_for(AdminPartnerRequisitesOut, key="requisites"),
        models=(AdminPartnerRequisitesOut,),
    ),
    "admin_partner_withdrawal_processing_route": RouteContract(
        request_model=AdminPartnerWithdrawalTransitionIn,
        response_schema=ok_envelope_for(AdminPartnerWithdrawalOut, key="withdrawal"),
        models=(AdminPartnerWithdrawalTransitionIn, AdminPartnerWithdrawalOut),
    ),
    "admin_partner_withdrawal_paid_route": RouteContract(
        request_model=AdminPartnerWithdrawalTransitionIn,
        response_schema=ok_envelope_for(AdminPartnerWithdrawalOut, key="withdrawal"),
        models=(AdminPartnerWithdrawalTransitionIn, AdminPartnerWithdrawalOut),
    ),
    "admin_partner_withdrawal_reject_route": RouteContract(
        request_model=AdminPartnerWithdrawalTransitionIn,
        response_schema=ok_envelope_for(AdminPartnerWithdrawalOut, key="withdrawal"),
        models=(AdminPartnerWithdrawalTransitionIn, AdminPartnerWithdrawalOut),
    ),
    "admin_partner_withdrawal_fail_route": RouteContract(
        request_model=AdminPartnerWithdrawalTransitionIn,
        response_schema=ok_envelope_for(AdminPartnerWithdrawalOut, key="withdrawal"),
        models=(AdminPartnerWithdrawalTransitionIn, AdminPartnerWithdrawalOut),
    ),
}
