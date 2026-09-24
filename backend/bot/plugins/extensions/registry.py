"""Process-local, atomic registrations belonging to active plugin identities."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .contracts import ExtensionContributions, ExtensionError

IDENTIFIER = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
PERMISSIONS = frozenset({"rewards.balance", "rewards.days", "rewards.traffic", "rewards.codes"})


def identifier(value: str) -> str:
    if not IDENTIFIER.fullmatch(value):
        raise ExtensionError("invalid_extension_identifier", 400)
    return value


def split_key(value: str) -> tuple[str, str]:
    parts = value.split(":")
    if len(parts) != 2:
        raise ExtensionError("invalid_extension_key", 400)
    return identifier(parts[0]), identifier(parts[1])


@dataclass(frozen=True)
class RegisteredExtension:
    version: str
    contributions: ExtensionContributions


class ExtensionRegistry:
    def __init__(self) -> None:
        self._owners: dict[str, RegisteredExtension] = {}

    def register(self, owner: str, version: str, value: ExtensionContributions) -> None:
        identifier(owner)
        if owner == "core":
            raise ExtensionError("reserved_extension_owner")
        if owner in self._owners:
            raise ExtensionError("duplicate_extension_owner")
        if not value.permissions <= PERMISSIONS:
            raise ExtensionError("unknown_extension_permission")
        for collection in (
            value.guides,
            value.resources,
            value.products,
            value.jobs,
            value.backups,
            value.storage,
        ):
            seen: set[str] = set()
            for item in collection:
                identifier(item.id)
                if item.id in seen:
                    raise ExtensionError("duplicate_extension_identifier")
                seen.add(item.id)
        jobs = {job.id for job in value.jobs}
        for job in value.jobs:
            if not 1 <= job.timeout_seconds <= 3600 or not 1 <= job.max_attempts <= 100:
                raise ExtensionError("invalid_extension_job_limits")
            if job.interval_seconds is not None and job.interval_seconds < 60:
                raise ExtensionError("invalid_extension_job_interval")
        event_keys: set[tuple[str, str]] = set()
        for event in value.events:
            if event.job not in jobs or not event.event or len(event.event) > 128:
                raise ExtensionError("invalid_extension_subscription")
            key = (event.event, event.job)
            if key in event_keys:
                raise ExtensionError("duplicate_extension_subscription")
            event_keys.add(key)
        for product in value.products:
            if not product.terms_versions or any(version < 1 for version in product.terms_versions):
                raise ExtensionError("invalid_extension_terms_versions")
        if any(item.version < 1 for item in value.backups):
            raise ExtensionError("invalid_extension_backup_version")
        self._owners[owner] = RegisteredExtension(str(version), value)
        if self is _registry:
            _configure_payment_events(self)

    def owners(self) -> dict[str, RegisteredExtension]:
        return dict(sorted(self._owners.items()))

    def require(self, owner: str) -> RegisteredExtension:
        try:
            return self._owners[owner]
        except KeyError as exc:
            raise ExtensionError("extension_unavailable", 503) from exc

    def permit(self, owner: str, permission: str) -> None:
        if permission not in self.require(owner).contributions.permissions:
            raise ExtensionError("extension_permission_denied", 403)


_registry = ExtensionRegistry()


def get_registry() -> ExtensionRegistry:
    return _registry


def set_registry(registry: ExtensionRegistry) -> None:
    global _registry
    _registry = registry
    _configure_payment_events(registry)


def _configure_payment_events(registry: ExtensionRegistry) -> None:
    from db.dal.extension_dal import configure_payment_subscribers

    subscribers: list[tuple[str, str, int]] = []
    for owner, entry in registry.owners().items():
        jobs = {job.id: job for job in entry.contributions.jobs}
        subscribers.extend(
            (owner, subscription.job, jobs[subscription.job].max_attempts)
            for subscription in entry.contributions.events
            if subscription.event == "payment.succeeded"
        )
    configure_payment_subscribers(tuple(subscribers))
