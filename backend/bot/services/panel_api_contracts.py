"""Machine-readable Remnawave API integration contract.

This module is the source of truth for every outbound Remnawave request made by
Mini Shop.  Runtime request labels, compatibility documentation, and drift
tests all consume the same operation registry so adding a call without an
explicit support decision fails CI.

The exact versions that Core certifies live in ``remnawave_support.json`` next
to this module.  Operations are grouped by API *generation*, not only SemVer
major: Remnawave has shipped compatibility-relevant changes in minor releases.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any


class PanelApiGeneration(StrEnum):
    RW2_UUID = "rw2-uuid-user-id"
    RW3_NUMERIC = "rw3-numeric-user-id"
    UNKNOWN = "unknown"


class PanelApiCapability(StrEnum):
    NUMERIC_USER_IDS = "numeric-user-ids"
    USER_STREAM = "user-stream"
    USER_STREAM_FILTERS = "user-stream-filters"
    TARGETED_SQUAD_BULK = "targeted-squad-bulk"
    CONNECTIONS_DROP = "connections-drop"
    HWID_USER_ID_SELECTOR = "hwid-user-id-selector"
    EMPTY_SUCCESS_BODY = "empty-success-body"
    MULTI_NODE_USAGE = "multi-node-usage"
    MULTI_NODE_TOP_USERS = "multi-node-top-users"
    BULK_SQUAD_UPDATE = "bulk-squad-update"


GENERATION_CAPABILITIES: dict[PanelApiGeneration, frozenset[PanelApiCapability]] = {
    PanelApiGeneration.RW2_UUID: frozenset(
        {
            PanelApiCapability.MULTI_NODE_TOP_USERS,
            PanelApiCapability.BULK_SQUAD_UPDATE,
        }
    ),
    PanelApiGeneration.RW3_NUMERIC: frozenset(PanelApiCapability),
    PanelApiGeneration.UNKNOWN: frozenset(),
}


class PanelApiOperation(StrEnum):
    SYSTEM_METADATA = "system.metadata"
    USERS_STREAM = "users.stream"
    USERS_LIST = "users.list"
    USER_GET = "users.get"
    USER_LOOKUP_TELEGRAM = "users.lookup.telegram"
    USER_LOOKUP_USERNAME = "users.lookup.username"
    USER_LOOKUP_EMAIL = "users.lookup.email"
    USER_CREATE = "users.create"
    USER_UPDATE = "users.update"
    USERS_BULK_UPDATE_SQUADS = "users.bulk-update-squads"
    USER_STATUS = "users.status"
    USER_CONNECTIONS_DROP_V2 = "users.connections.drop-v2"
    USER_CONNECTIONS_DROP_V3 = "users.connections.drop-v3"
    USER_DELETE = "users.delete"
    USER_REVOKE = "users.revoke"
    USER_RESET_TRAFFIC = "users.reset-traffic"
    SUBSCRIPTION_CONFIG_RESOLVED = "subscription.config.resolved"
    SUBSCRIPTION_PAGE_CONFIG_LIST = "subscription-page-config.list"
    SUBSCRIPTION_PAGE_CONFIG_GET = "subscription-page-config.get"
    EXTERNAL_SQUAD_GET = "external-squads.get"
    HWID_DEVICES_GET = "hwid.devices.get"
    HWID_DEVICE_DELETE = "hwid.devices.delete"
    HWID_STATS = "hwid.devices.stats"
    HWID_TOP_USERS = "hwid.devices.top-users"
    NODE_RESTART = "nodes.restart"
    NODES_RESTART_ALL = "nodes.restart-all"
    NODES_LIST = "nodes.list"
    NODE_STATS = "nodes.stats"
    SYSTEM_STATS = "system.stats"
    SYSTEM_BANDWIDTH_STATS = "system.stats.bandwidth"
    NODE_BANDWIDTH = "bandwidth.nodes"
    USER_BANDWIDTH = "bandwidth.users"
    NODE_USER_BANDWIDTH = "bandwidth.node-users"
    NODES_USER_BANDWIDTH = "bandwidth.nodes-users"
    NODES_USER_USAGE = "bandwidth.nodes-usage"
    INTERNAL_SQUADS_LIST = "internal-squads.list"
    INTERNAL_SQUAD_GET = "internal-squads.get"
    INTERNAL_SQUAD_NODES = "internal-squads.nodes"
    INTERNAL_SQUAD_ADD_USERS = "internal-squads.add-users"
    INTERNAL_SQUAD_REMOVE_USERS = "internal-squads.remove-users"
    HOSTS_LIST = "hosts.list"


class PanelApiCoverage(StrEnum):
    FIXTURE = "fixture"
    UNIT = "unit"
    LIVE_READ = "live-read"
    LIVE_WRITE = "live-write"
    UPGRADE = "upgrade"


@dataclass(frozen=True, slots=True)
class PanelApiOperationContract:
    operation: PanelApiOperation
    method: str
    path: str
    log_label: str
    generations: tuple[PanelApiGeneration, ...]
    success_statuses: tuple[int, ...]
    response_shape: str
    mutation: bool = False
    idempotent: bool = True
    empty_success_body: bool = False
    identity_sensitive: bool = False
    compatibility_note: str = "Stable across the certified API generations."
    coverage: tuple[PanelApiCoverage, ...] = (
        PanelApiCoverage.UNIT,
        PanelApiCoverage.LIVE_READ,
    )


RW2_AND_RW3 = (PanelApiGeneration.RW2_UUID, PanelApiGeneration.RW3_NUMERIC)
RW2_ONLY = (PanelApiGeneration.RW2_UUID,)
RW3_ONLY = (PanelApiGeneration.RW3_NUMERIC,)
READ_COVERAGE = (PanelApiCoverage.UNIT, PanelApiCoverage.LIVE_READ)
WRITE_COVERAGE = (PanelApiCoverage.UNIT, PanelApiCoverage.LIVE_WRITE)
UPGRADE_COVERAGE = (
    PanelApiCoverage.UNIT,
    PanelApiCoverage.LIVE_READ,
    PanelApiCoverage.UPGRADE,
)


def _contract(
    operation: PanelApiOperation,
    method: str,
    path: str,
    log_label: str,
    *,
    generations: tuple[PanelApiGeneration, ...] = RW2_AND_RW3,
    success_statuses: tuple[int, ...] = (200,),
    response_shape: str = "JSON envelope with response",
    mutation: bool = False,
    idempotent: bool = True,
    empty_success_body: bool = False,
    identity_sensitive: bool = False,
    compatibility_note: str = "Stable across the certified API generations.",
    coverage: tuple[PanelApiCoverage, ...] = READ_COVERAGE,
) -> PanelApiOperationContract:
    return PanelApiOperationContract(
        operation=operation,
        method=method,
        path=path,
        log_label=log_label,
        generations=generations,
        success_statuses=success_statuses,
        response_shape=response_shape,
        mutation=mutation,
        idempotent=idempotent,
        empty_success_body=empty_success_body,
        identity_sensitive=identity_sensitive,
        compatibility_note=compatibility_note,
        coverage=coverage,
    )


PANEL_API_OPERATION_CONTRACTS: tuple[PanelApiOperationContract, ...] = (
    _contract(
        PanelApiOperation.SYSTEM_METADATA,
        "GET",
        "/system/metadata",
        "/system/metadata",
        compatibility_note="Stable version probe; failures are not treated as a capability result.",
    ),
    _contract(
        PanelApiOperation.USERS_STREAM,
        "GET",
        "/users/stream",
        "/users/stream",
        compatibility_note=(
            "3.x is the canonical cursor stream and supports lookup filters; a 2.8 stream "
            "may expose UUID users or ignore the new filters, so Core validates results."
        ),
        coverage=UPGRADE_COVERAGE,
    ),
    _contract(
        PanelApiOperation.USERS_LIST,
        "GET",
        "/users",
        "/users",
        generations=RW2_ONLY,
        compatibility_note="Legacy offset pagination used when the stream is absent or UUID-based.",
    ),
    _contract(
        PanelApiOperation.USER_GET,
        "GET",
        "/users/{userRef}",
        "/users",
        identity_sensitive=True,
        compatibility_note="{userRef} is a UUID in 2.8.1 and a numeric id in 3.x.",
        coverage=UPGRADE_COVERAGE,
    ),
    _contract(
        PanelApiOperation.USER_LOOKUP_TELEGRAM,
        "GET",
        "/users/by-telegram-id/{telegramId}",
        "/users/by-telegram-id",
        generations=RW2_ONLY,
        compatibility_note="3.x uses /users/stream?telegramId=... instead.",
    ),
    _contract(
        PanelApiOperation.USER_LOOKUP_USERNAME,
        "GET",
        "/users/by-username/{username}",
        "/users/by-username",
        compatibility_note=(
            "The username lookup route remains stable through 3.2.1; 3.1+ reports an "
            "absent user as 404/A063."
        ),
    ),
    _contract(
        PanelApiOperation.USER_LOOKUP_EMAIL,
        "GET",
        "/users/by-email/{email}",
        "/users/by-email",
        generations=RW2_ONLY,
        compatibility_note="3.x uses /users/stream?email=... instead.",
    ),
    _contract(
        PanelApiOperation.USER_CREATE,
        "POST",
        "/users",
        "/users",
        success_statuses=(200, 201),
        mutation=True,
        idempotent=False,
        identity_sensitive=True,
        compatibility_note="Core never sends a caller-provided user UUID; 3.x returns numeric id.",
        coverage=WRITE_COVERAGE,
    ),
    _contract(
        PanelApiOperation.USER_UPDATE,
        "PATCH",
        "/users",
        "/users",
        success_statuses=(200, 202, 204),
        mutation=True,
        empty_success_body=True,
        identity_sensitive=True,
        compatibility_note="Selector field is uuid in 2.8.1 and integer id in 3.x.",
        coverage=WRITE_COVERAGE,
    ),
    _contract(
        PanelApiOperation.USERS_BULK_UPDATE_SQUADS,
        "POST",
        "/users/bulk/update-squads",
        "/users",
        success_statuses=(200, 202, 204),
        mutation=True,
        empty_success_body=True,
        identity_sensitive=True,
        compatibility_note=(
            "Exact-state squad update, chunked at 500 users. 2.8.1 selects UUIDs with "
            "uuids and returns affectedRows; 3.x selects numeric userIds and returns 204. "
            "An empty target state uses per-user PATCH because 3.0.0 returns A088/500."
        ),
        coverage=WRITE_COVERAGE,
    ),
    _contract(
        PanelApiOperation.USER_STATUS,
        "POST",
        "/users/{userRef}/actions/{enable|disable}",
        "/users",
        success_statuses=(200, 202, 204),
        mutation=True,
        empty_success_body=True,
        identity_sensitive=True,
        compatibility_note="Path identity follows the UUID/numeric-id generation.",
        coverage=WRITE_COVERAGE,
    ),
    _contract(
        PanelApiOperation.USER_CONNECTIONS_DROP_V2,
        "POST",
        "/ip-control/drop-connections",
        "/ip-control",
        generations=RW2_ONLY,
        success_statuses=(200, 202, 204),
        mutation=True,
        empty_success_body=True,
        identity_sensitive=True,
        compatibility_note="2.8 payload selects userUuids.",
        coverage=WRITE_COVERAGE,
    ),
    _contract(
        PanelApiOperation.USER_CONNECTIONS_DROP_V3,
        "POST",
        "/connections/drop",
        "/connections",
        generations=RW3_ONLY,
        success_statuses=(200, 202, 204),
        mutation=True,
        empty_success_body=True,
        identity_sensitive=True,
        compatibility_note="3.x payload selects numeric userIds.",
        coverage=WRITE_COVERAGE,
    ),
    _contract(
        PanelApiOperation.USER_DELETE,
        "DELETE",
        "/users/{userRef}",
        "/users",
        success_statuses=(200, 202, 204),
        mutation=True,
        empty_success_body=True,
        identity_sensitive=True,
        compatibility_note=(
            "404 for a missing entity is idempotent success; route absence is distinct."
        ),
        coverage=WRITE_COVERAGE,
    ),
    _contract(
        PanelApiOperation.USER_REVOKE,
        "POST",
        "/users/{userRef}/actions/revoke",
        "/users",
        success_statuses=(200, 202, 204),
        mutation=True,
        empty_success_body=True,
        identity_sensitive=True,
        compatibility_note="Path identity follows the UUID/numeric-id generation.",
        coverage=WRITE_COVERAGE,
    ),
    _contract(
        PanelApiOperation.USER_RESET_TRAFFIC,
        "POST",
        "/users/{userRef}/actions/reset-traffic",
        "/users",
        success_statuses=(200, 202, 204),
        mutation=True,
        empty_success_body=True,
        identity_sensitive=True,
        compatibility_note="Path identity follows the UUID/numeric-id generation.",
        coverage=WRITE_COVERAGE,
    ),
    _contract(
        PanelApiOperation.SUBSCRIPTION_CONFIG_RESOLVED,
        "GET",
        "/subscriptions/subpage-config/{shortUuid}",
        "/subscriptions/subpage-config",
        compatibility_note=(
            "GET intentionally carries requestHeaders in a JSON body as required upstream."
        ),
    ),
    _contract(
        PanelApiOperation.SUBSCRIPTION_PAGE_CONFIG_LIST,
        "GET",
        "/subscription-page-configs",
        "/subscription-page-configs",
    ),
    _contract(
        PanelApiOperation.SUBSCRIPTION_PAGE_CONFIG_GET,
        "GET",
        "/subscription-page-configs/{uuid}",
        "/subscription-page-configs",
    ),
    _contract(
        PanelApiOperation.EXTERNAL_SQUAD_GET,
        "GET",
        "/external-squads/{uuid}",
        "/external-squads",
    ),
    _contract(
        PanelApiOperation.HWID_DEVICES_GET,
        "GET",
        "/hwid/devices/{userRef}",
        "/hwid/devices",
        identity_sensitive=True,
        compatibility_note="Path userRef is UUID in 2.8.1 and numeric id in 3.x.",
    ),
    _contract(
        PanelApiOperation.HWID_DEVICE_DELETE,
        "POST",
        "/hwid/devices/delete",
        "/hwid/devices/delete",
        success_statuses=(200, 202, 204),
        mutation=True,
        empty_success_body=True,
        identity_sensitive=True,
        compatibility_note="Payload selector is userUuid in 2.8.1 and userId in 3.x.",
        coverage=WRITE_COVERAGE,
    ),
    _contract(
        PanelApiOperation.HWID_STATS,
        "GET",
        "/hwid/devices/stats",
        "/hwid/devices/stats",
    ),
    _contract(
        PanelApiOperation.HWID_TOP_USERS,
        "GET",
        "/hwid/devices/top-users",
        "/hwid/devices/top-users",
    ),
    _contract(
        PanelApiOperation.NODE_RESTART,
        "POST",
        "/nodes/{uuid}/actions/restart",
        "/nodes",
        success_statuses=(200, 202, 204),
        mutation=True,
        empty_success_body=True,
        compatibility_note="Node identifiers remain UUIDs in 3.x.",
        coverage=(PanelApiCoverage.UNIT,),
    ),
    _contract(
        PanelApiOperation.NODES_RESTART_ALL,
        "POST",
        "/nodes/actions/restart-all",
        "/nodes",
        success_statuses=(200, 202, 204),
        mutation=True,
        empty_success_body=True,
        compatibility_note="Not run in live CI because it disrupts every registered node.",
        coverage=(PanelApiCoverage.UNIT,),
    ),
    _contract(PanelApiOperation.NODES_LIST, "GET", "/nodes", "/nodes"),
    _contract(
        PanelApiOperation.NODE_STATS,
        "GET",
        "/system/stats/nodes",
        "/system/stats/nodes",
    ),
    _contract(PanelApiOperation.SYSTEM_STATS, "GET", "/system/stats", "/system/stats"),
    _contract(
        PanelApiOperation.SYSTEM_BANDWIDTH_STATS,
        "GET",
        "/system/stats/bandwidth",
        "/system/stats/bandwidth",
    ),
    _contract(
        PanelApiOperation.NODE_BANDWIDTH,
        "GET",
        "/bandwidth-stats/nodes",
        "/bandwidth-stats/nodes",
    ),
    _contract(
        PanelApiOperation.USER_BANDWIDTH,
        "GET",
        "/bandwidth-stats/users/{userRef}",
        "/bandwidth-stats/users",
        identity_sensitive=True,
        compatibility_note="Path userRef is UUID in 2.8.1 and numeric id in 3.x.",
    ),
    _contract(
        PanelApiOperation.NODE_USER_BANDWIDTH,
        "GET",
        "/bandwidth-stats/nodes/{nodeUuid}/users",
        "/bandwidth-stats/nodes",
    ),
    _contract(
        PanelApiOperation.NODES_USER_BANDWIDTH,
        "POST",
        "/bandwidth-stats/nodes/users",
        "/bandwidth-stats/nodes",
        compatibility_note=(
            "2.8.1-compatible aggregate top-users request for a set of nodes; "
            "Core detects topUsersLimit saturation before treating missing users as zero."
        ),
    ),
    _contract(
        PanelApiOperation.NODES_USER_USAGE,
        "POST",
        "/bandwidth-stats/nodes/usage",
        "/bandwidth-stats/nodes",
        generations=RW3_ONLY,
        compatibility_note=(
            "3.x returns numeric user ids and per-node totals for all requested nodes. "
            "Usage snapshots are refreshed no faster than the upstream aggregation cadence."
        ),
    ),
    _contract(
        PanelApiOperation.INTERNAL_SQUADS_LIST,
        "GET",
        "/internal-squads",
        "/internal-squads",
    ),
    _contract(
        PanelApiOperation.INTERNAL_SQUAD_GET,
        "GET",
        "/internal-squads/{uuid}",
        "/internal-squads",
    ),
    _contract(
        PanelApiOperation.INTERNAL_SQUAD_NODES,
        "GET",
        "/internal-squads/{uuid}/{accessible-nodes|nodes}",
        "/internal-squads",
        compatibility_note="Core tries both upstream route spellings and validates response shape.",
    ),
    _contract(
        PanelApiOperation.INTERNAL_SQUAD_ADD_USERS,
        "POST",
        "/internal-squads/{uuid}/bulk-actions/add-many-users",
        "/internal-squads",
        generations=RW3_ONLY,
        success_statuses=(200, 202, 204),
        mutation=True,
        empty_success_body=True,
        identity_sensitive=True,
        compatibility_note=(
            "3.x targeted numeric-id bulk, chunked at 1000. In 2.8.1 the superficially "
            "similar add-users route targets every user, so Core PATCHes requested users."
        ),
        coverage=WRITE_COVERAGE,
    ),
    _contract(
        PanelApiOperation.INTERNAL_SQUAD_REMOVE_USERS,
        "DELETE",
        "/internal-squads/{uuid}/bulk-actions/remove-many-users",
        "/internal-squads",
        generations=RW3_ONLY,
        success_statuses=(200, 202, 204),
        mutation=True,
        empty_success_body=True,
        identity_sensitive=True,
        compatibility_note=(
            "3.x targeted numeric-id bulk, chunked at 1000; 2.8.1 uses per-user PATCH."
        ),
        coverage=WRITE_COVERAGE,
    ),
    _contract(PanelApiOperation.HOSTS_LIST, "GET", "/hosts", "/hosts"),
)


PANEL_API_CONTRACT_BY_OPERATION = {
    contract.operation: contract for contract in PANEL_API_OPERATION_CONTRACTS
}

if len(PANEL_API_CONTRACT_BY_OPERATION) != len(PanelApiOperation):
    raise RuntimeError("Every PanelApiOperation must have exactly one contract entry.")


@dataclass(frozen=True, slots=True)
class PanelWebhookContract:
    event: str
    generations: tuple[PanelApiGeneration, ...]
    identity: str
    behavior: str
    coverage: tuple[PanelApiCoverage, ...] = (PanelApiCoverage.UNIT,)


PANEL_WEBHOOK_CONTRACTS: tuple[PanelWebhookContract, ...] = (
    PanelWebhookContract(
        event="user.expires_in_72_hours / 48_hours / 24_hours",
        generations=RW2_AND_RW3,
        identity="user.uuid in 2.8.1; user.id normalized to the internal uuid alias in 3.x",
        behavior="Subscription expiry notification and optional auto-renew processing.",
    ),
    PanelWebhookContract(
        event="user.expiration",
        generations=RW2_AND_RW3,
        identity="user object plus meta.expirationHours",
        behavior="Compatibility event mapped to before/after-expiration notification stages.",
    ),
    PanelWebhookContract(
        event="user.expired / user.expired_24_hours_ago",
        generations=RW2_AND_RW3,
        identity="normalized user identity",
        behavior="Expired subscription notification with stale-subscription suppression.",
    ),
    PanelWebhookContract(
        event="torrent_blocker.report",
        generations=RW2_AND_RW3,
        identity="typed torrent-blocker payload; user identity is resolved independently",
        behavior="Typed security notification; invalid or oversized payloads are rejected.",
    ),
    PanelWebhookContract(
        event="other events (for example user.modified)",
        generations=RW2_AND_RW3,
        identity="normalized user identity when a user object is present",
        behavior="Emitted to the Core/plugin event bus but ignored for lifecycle notifications.",
    ),
)


def operation_contract(operation: PanelApiOperation) -> PanelApiOperationContract:
    return PANEL_API_CONTRACT_BY_OPERATION[operation]


def endpoint_log_labels() -> tuple[str, ...]:
    """Return privacy-safe endpoint families, longest prefix first."""
    return tuple(
        sorted(
            {contract.log_label for contract in PANEL_API_OPERATION_CONTRACTS},
            key=lambda value: (-len(value), value),
        )
    )


SUPPORT_MANIFEST_PATH = Path(__file__).with_name("remnawave_support.json")


@lru_cache(maxsize=1)
def load_support_manifest() -> dict[str, Any]:
    payload = json.loads(SUPPORT_MANIFEST_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("Remnawave support manifest must contain a JSON object.")
    return payload


def panel_version_support_status(
    version: str | None,
    generation: PanelApiGeneration,
) -> str:
    """Classify an exact panel version without claiming untested compatibility."""
    if not version:
        return "unknown"
    normalized = version.strip().lower().removeprefix("v")
    manifest = load_support_manifest()
    generations = manifest.get("generations")
    if isinstance(generations, list):
        for item in generations:
            if not isinstance(item, dict):
                continue
            certified = item.get("certified_versions")
            if isinstance(certified, list) and normalized in {
                str(value).strip().lower().removeprefix("v") for value in certified
            }:
                return str(item.get("status") or "unknown")
    historical = manifest.get("historical_versions")
    if isinstance(historical, list):
        for item in historical:
            if isinstance(item, dict) and normalized == str(item.get("version") or ""):
                return "historical"
    blocked = manifest.get("blocked_versions")
    if isinstance(blocked, list) and normalized in {
        str(value).strip().lower().removeprefix("v") for value in blocked
    }:
        return "unsupported"
    if generation is PanelApiGeneration.UNKNOWN:
        return "unverified"
    return "unverified"


def certified_panel_versions(generation: PanelApiGeneration) -> tuple[str, ...]:
    """Return exact Core-certified releases for one detected API generation."""
    generations = load_support_manifest().get("generations")
    if not isinstance(generations, list):
        return ()
    for item in generations:
        if not isinstance(item, dict) or item.get("id") != generation.value:
            continue
        certified = item.get("certified_versions")
        if not isinstance(certified, list):
            return ()
        return tuple(str(value).strip() for value in certified if str(value).strip())
    return ()
