from __future__ import annotations

from bot.app.web.route_contracts import RouteContract, ok_envelope_for

from .documents import PublicDocumentContentOut, PublicDocumentOut, PublicDocumentsOut

DOCUMENTS_ROUTE_CONTRACTS: dict[str, RouteContract] = {
    "documents_list_route": RouteContract(
        response_schema=ok_envelope_for(PublicDocumentsOut),
        models=(PublicDocumentOut, PublicDocumentsOut),
    ),
    "document_content_route": RouteContract(
        response_schema=ok_envelope_for(PublicDocumentContentOut),
        models=(PublicDocumentContentOut,),
    ),
}
