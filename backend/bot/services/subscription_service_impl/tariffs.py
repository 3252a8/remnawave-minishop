from ._runtime import (
    Any,
    AsyncSession,
    Dict,
    List,
    Optional,
    Subscription,
    SubscriptionServiceMixinContract,
    Tariff,
    TariffsConfig,
    Tuple,
    datetime,
    default_currency_key_for_settings,
    logging,
    math,
    tariff_dal,
    timezone,
)


class TariffMixin(SubscriptionServiceMixinContract):
    @staticmethod
    def gb_to_bytes(gb: float) -> int:
        return int(float(gb) * (1024**3))

    @staticmethod
    def _far_future() -> datetime:
        return datetime(2099, 1, 1, tzinfo=timezone.utc)

    def _parse_sale_mode_context(
        self,
        sale_mode: str,
        explicit_tariff_key: Optional[str] = None,
    ) -> Tuple[str, Optional[str]]:
        mode = (sale_mode or "subscription").strip()
        tariff_key = explicit_tariff_key
        for separator in ("@", "|"):
            if separator in mode:
                base, suffix = mode.split(separator, 1)
                mode = base or mode
                suffix_key = suffix.split("|", 1)[0]
                if separator == "|" and suffix_key in {"bot"}:
                    suffix_key = ""
                tariff_key = tariff_key or suffix_key or None
                break
        return mode, tariff_key

    def _tariffs_config(self) -> Optional[TariffsConfig]:
        config = getattr(self.settings, "tariffs_config", None)
        return config if isinstance(config, TariffsConfig) else None

    def _default_tariff(self) -> Optional[Tariff]:
        config = self._tariffs_config()
        return config.default if config else None

    def _resolve_tariff(
        self, tariff_key: Optional[str], billing_model: Optional[str] = None
    ) -> Optional[Tariff]:
        config = self._tariffs_config()
        if not config:
            return None
        tariff = config.require(tariff_key or config.default_tariff)
        if billing_model and tariff.billing_model != billing_model:
            raise ValueError(
                f"Tariff {tariff.key} is {tariff.billing_model}, expected {billing_model}"
            )
        return tariff

    def _panel_squads_for_tariff(
        self,
        tariff: Optional[Tariff],
        *,
        include_premium: bool = True,
    ) -> Optional[List[str]]:
        if tariff:
            squads = list(tariff.squad_uuids or [])
            if include_premium:
                squads.extend(tariff.premium_squad_uuids or [])
            return list(dict.fromkeys(squads))
        return list(self.settings.parsed_user_squad_uuids or [])

    def _catalog_premium_squad_uuid_set(self) -> set[str]:
        config = self._tariffs_config()
        if not config:
            return set()
        premium_squads: set[str] = set()
        for tariff in getattr(config, "tariffs", []) or []:
            premium_squads.update(str(uuid) for uuid in (tariff.premium_squad_uuids or []))
        return premium_squads

    def _trial_panel_squad_uuids(self) -> List[str]:
        squads = self.settings.parsed_trial_squad_uuids
        if not squads:
            squads = self.settings.parsed_user_squad_uuids or []
        premium_squads = set(self._trial_premium_squad_uuids())
        premium_squads.update(self._catalog_premium_squad_uuid_set())
        return list(
            dict.fromkeys(
                str(uuid)
                for uuid in squads
                if str(uuid or "").strip() and str(uuid) not in premium_squads
            )
        )

    def _trial_all_panel_squad_uuids(self) -> List[str]:
        squads = [*self._trial_panel_squad_uuids(), *self._trial_premium_squad_uuids()]
        return list(dict.fromkeys(str(uuid) for uuid in squads if str(uuid or "").strip()))

    def _trial_premium_squad_uuids(self) -> List[str]:
        squads = self.settings.parsed_trial_premium_squad_uuids or []
        return list(dict.fromkeys(str(uuid) for uuid in squads if str(uuid or "").strip()))

    def _trial_premium_baseline_bytes(self) -> int:
        if not self._trial_premium_squad_uuids():
            return 0
        return int(self.settings.trial_premium_traffic_limit_bytes or 0)

    def _traffic_limit_for_period_tariff(
        self,
        tariff: Optional[Tariff],
        topup_balance_bytes: int = 0,
        regular_bonus_bytes: int = 0,
        regular_unlimited_override: bool = False,
        traffic_used_bytes: int = 0,
    ) -> int:
        if tariff:
            baseline = int(tariff.monthly_bytes or 0)
        else:
            baseline = int(self.settings.user_traffic_limit_bytes)
        return self._compute_main_traffic_limit_bytes(
            tier_baseline_bytes=baseline,
            topup_balance_bytes=topup_balance_bytes,
            regular_bonus_bytes=regular_bonus_bytes,
            regular_unlimited_override=regular_unlimited_override,
            traffic_used_bytes=traffic_used_bytes,
        )

    def _premium_limit_for_tariff(
        self, tariff: Optional[Tariff], topup_balance_bytes: int = 0
    ) -> int:
        if not tariff:
            return 0
        return int(tariff.premium_monthly_bytes + max(0, topup_balance_bytes))

    @staticmethod
    def _premium_effective_limit_bytes(
        premium_baseline_bytes: int,
        premium_topup_balance_bytes: int = 0,
        premium_topup_used_bytes: int = 0,
        premium_bonus_bytes: int = 0,
    ) -> int:
        return (
            int(premium_baseline_bytes or 0)
            + max(0, int(premium_topup_balance_bytes or 0))
            + max(0, int(premium_topup_used_bytes or 0))
            + max(0, int(premium_bonus_bytes or 0))
        )

    def _compute_main_traffic_limit_bytes(
        self,
        *,
        tier_baseline_bytes: int,
        topup_balance_bytes: int,
        regular_bonus_bytes: int,
        regular_unlimited_override: bool,
        traffic_used_bytes: int,
    ) -> int:
        """Numeric cap sent to the panel; Remnawave treats ``0`` as unlimited."""
        floor = (
            int(tier_baseline_bytes or 0)
            + max(0, int(topup_balance_bytes or 0))
            + max(0, int(regular_bonus_bytes or 0))
        )
        if regular_unlimited_override:
            return 0
        return floor

    async def premium_access_for_tariff(self, tariff: Optional[Tariff]) -> Dict[str, Any]:
        if not tariff or not tariff.premium_squad_uuids:
            return {"squad_uuids": [], "squad_labels": [], "node_labels": []}

        cache_key = tuple(sorted(str(uuid) for uuid in tariff.premium_squad_uuids))
        now_ts = datetime.now(timezone.utc).timestamp()
        cached = self._premium_access_cache.get(cache_key)
        if cached and now_ts - float(cached.get("ts", 0)) < 600:
            return {
                "squad_uuids": list(cached.get("squad_uuids") or []),
                "squad_labels": list(cached.get("squad_labels") or []),
                "node_labels": list(cached.get("node_labels") or []),
            }

        def _extract_inbound_uuids(squad_obj: Dict[str, Any]) -> List[str]:
            collected: List[str] = []
            for field in ("inbounds", "internalInbounds", "configProfileInbounds"):
                value = squad_obj.get(field)
                if not isinstance(value, list):
                    continue
                for inbound in value:
                    if isinstance(inbound, dict):
                        ib_uuid = str(
                            inbound.get("uuid")
                            or inbound.get("inboundUuid")
                            or inbound.get("id")
                            or ""
                        )
                    else:
                        ib_uuid = str(inbound or "")
                    if ib_uuid:
                        collected.append(ib_uuid)
            return collected

        squad_name_map: Dict[str, str] = {}
        squad_inbound_map: Dict[str, List[str]] = {}
        try:
            squads = await self.panel_service.get_internal_squads() or []
            for squad in squads:
                if not isinstance(squad, dict):
                    continue
                squad_uuid = str(squad.get("uuid") or squad.get("id") or "")
                if not squad_uuid:
                    continue
                squad_name_map[squad_uuid] = str(
                    squad.get("name") or squad.get("title") or squad_uuid
                )
                squad_inbound_map[squad_uuid] = _extract_inbound_uuids(squad)
        except Exception:
            logging.debug("Failed to load internal squad names for premium display", exc_info=True)

        for squad_uuid in tariff.premium_squad_uuids:
            squad_uuid_str = str(squad_uuid)
            if squad_inbound_map.get(squad_uuid_str):
                continue
            try:
                detail = await self.panel_service.get_internal_squad(squad_uuid_str)
            except Exception:
                logging.debug(
                    "Failed to load internal squad detail for %s", squad_uuid_str, exc_info=True
                )
                detail = None
            if isinstance(detail, dict):
                squad_inbound_map[squad_uuid_str] = _extract_inbound_uuids(detail)
                if squad_uuid_str not in squad_name_map:
                    squad_name_map[squad_uuid_str] = str(
                        detail.get("name") or detail.get("title") or squad_uuid_str
                    )

        hosts_by_inbound: Dict[str, List[Dict[str, Any]]] = {}
        try:
            hosts = await self.panel_service.get_hosts() or []
            for host in hosts:
                if not isinstance(host, dict):
                    continue
                inbound_raw = host.get("inbound")
                inbound_field: Dict[str, Any] = inbound_raw if isinstance(inbound_raw, dict) else {}
                inbound_uuid = (
                    host.get("inboundUuid")
                    or host.get("inbound_uuid")
                    or host.get("configProfileInboundUuid")
                    or inbound_field.get("configProfileInboundUuid")
                    or inbound_field.get("inboundUuid")
                    or inbound_field.get("uuid")
                    or ""
                )
                inbound_uuid = str(inbound_uuid)
                if not inbound_uuid:
                    continue
                hosts_by_inbound.setdefault(inbound_uuid, []).append(host)
            logging.debug(
                "Premium label resolution: %d hosts grouped across %d inbounds; squad inbound map: %s",  # noqa: E501
                len(hosts),
                len(hosts_by_inbound),
                {k: len(v) for k, v in squad_inbound_map.items()},
            )
        except Exception:
            logging.debug("Failed to load hosts for premium display", exc_info=True)

        def _host_remark(host: Dict[str, Any]) -> str:
            for key in ("remark", "name", "label", "title"):
                value = host.get(key)
                if value is None:
                    continue
                candidate = str(value).strip()
                if candidate:
                    return candidate
            return ""

        node_labels: List[str] = []
        for squad_uuid in tariff.premium_squad_uuids:
            squad_uuid_str = str(squad_uuid)
            inbound_uuids = squad_inbound_map.get(squad_uuid_str) or []
            host_labels_for_squad: List[str] = []
            for inbound_uuid in inbound_uuids:
                for host in hosts_by_inbound.get(inbound_uuid, []):
                    remark = _host_remark(host)
                    if remark:
                        host_labels_for_squad.append(remark)

            if host_labels_for_squad:
                node_labels.extend(host_labels_for_squad)
                continue

            try:
                nodes = (
                    await self.panel_service.get_internal_squad_accessible_nodes(squad_uuid) or []
                )
            except Exception:
                logging.debug(
                    "Failed to load accessible nodes for premium squad %s",
                    squad_uuid,
                    exc_info=True,
                )
                nodes = []
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                node_uuid = str(
                    node.get("uuid") or node.get("nodeUuid") or node.get("node_uuid") or ""
                )
                node_name = ""
                for key in (
                    "nodeName",
                    "name",
                    "nodeRemark",
                    "remark",
                    "label",
                    "title",
                    "address",
                    "host",
                ):
                    value = node.get(key)
                    if value is None:
                        continue
                    candidate = str(value).strip()
                    if candidate:
                        node_name = candidate
                        break
                if node_name:
                    label = node_name
                elif node_uuid:
                    label = f"{node_uuid[:8]}..."
                else:
                    continue
                node_labels.append(label)

        squad_labels = [
            squad_name_map.get(str(uuid), f"{str(uuid)[:8]}...")
            for uuid in tariff.premium_squad_uuids
        ]
        payload: Dict[str, Any] = {
            "ts": now_ts,
            "squad_uuids": list(tariff.premium_squad_uuids),
            "squad_labels": list(dict.fromkeys(squad_labels)),
            "node_labels": list(dict.fromkeys(node_labels)),
        }
        self._premium_access_cache[cache_key] = payload
        return {
            "squad_uuids": list(payload["squad_uuids"]),
            "squad_labels": list(payload["squad_labels"]),
            "node_labels": list(payload["node_labels"]),
        }

    def _base_hwid_limit_for_tariff(self, tariff: Optional[Tariff]) -> Optional[int]:
        if tariff and tariff.hwid_device_limit is not None:
            return int(tariff.hwid_device_limit)
        value = self.settings.USER_HWID_DEVICE_LIMIT
        return int(value) if value is not None else None

    @staticmethod
    def _effective_hwid_limit(base_limit: Optional[int], extra_devices: int = 0) -> Optional[int]:
        if base_limit is None:
            return 0
        base_int = max(0, int(base_limit))
        if base_int == 0:
            return 0
        return base_int + max(0, int(extra_devices or 0))

    def calculate_tariff_switch_options(
        self, sub: Subscription, target_tariff: Tariff
    ) -> Dict[str, Any]:
        current_tariff = (
            self._resolve_tariff(sub.tariff_key) if sub.tariff_key else self._default_tariff()
        )
        now = datetime.now(timezone.utc)
        remaining_days = max(0, (sub.end_date - now).days) if sub.end_date else 0
        effective = float(sub.effective_monthly_price_rub or 0)
        current_model = current_tariff.billing_model if current_tariff else "period"
        default_currency = default_currency_key_for_settings(self.settings)

        if current_model == "period" and target_tariff.billing_model == "period":
            target_monthly = (
                target_tariff.period_price(1, default_currency)
                or target_tariff.min_period_price(default_currency)
                or effective
                or 1
            )
            remaining_value = remaining_days * (effective / 30) if effective else 0
            days_after = (
                math.floor((remaining_value / float(target_monthly)) * 30)
                if target_monthly
                else remaining_days
            )
            paid_diff = (
                max(0, math.ceil((float(target_monthly) - effective) * remaining_days / 30))
                if effective
                else 0
            )
            return {
                "mode": "period_to_period",
                "remaining_days": remaining_days,
                "recalc_days": max(0, days_after),
                "paid_diff_rub": paid_diff,
                "paid_diff": paid_diff,
                "target_monthly_rub": float(target_monthly),
                "target_monthly_price": float(target_monthly),
                "currency": default_currency,
            }

        if current_model == "period" and target_tariff.billing_model == "traffic":
            rub_per_gb = target_tariff.currency_per_gb_for_conversion(default_currency)
            remaining_value = remaining_days * (effective / 30) if effective else 0
            converted_gb = math.floor(remaining_value / rub_per_gb) if rub_per_gb else 0
            return {
                "mode": "period_to_traffic",
                "remaining_days": remaining_days,
                "converted_gb": max(0, converted_gb),
                "rub_per_gb": rub_per_gb,
                "currency_per_gb": rub_per_gb,
                "currency": default_currency,
            }

        return {
            "mode": "traffic_to_period",
            "remaining_days": remaining_days,
            "currency": default_currency,
        }

    @staticmethod
    def _aware_utc(value: Optional[datetime]) -> Optional[datetime]:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    async def _hwid_conversion_credit(
        self,
        session: AsyncSession,
        sub: Subscription,
        *,
        at: datetime,
    ) -> Dict[str, Any]:
        entries = await tariff_dal.get_hwid_device_value_entries(
            session,
            subscription_id=sub.subscription_id,
            at=at,
        )
        value_rub = 0.0
        purchase_ids: List[int] = []
        skipped_devices = 0
        for entry in entries:
            currency = str(entry.get("currency") or "").upper()
            if currency in {"XTR", "STARS", "STAR"}:
                skipped_devices += int(entry.get("purchased_devices") or 0)
                continue
            amount = float(entry.get("amount") or 0)
            if amount <= 0:
                continue
            valid_from = (
                self._aware_utc(entry.get("valid_from"))
                or self._aware_utc(entry.get("created_at"))
                or at
            )
            valid_until = self._aware_utc(entry.get("valid_until"))
            if not valid_until or valid_until <= at or valid_from >= valid_until:
                continue
            total_seconds = max(1.0, (valid_until - valid_from).total_seconds())
            remaining_start = max(at, valid_from)
            remaining_seconds = max(0.0, (valid_until - remaining_start).total_seconds())
            if remaining_seconds <= 0:
                continue
            value_rub += amount * (remaining_seconds / total_seconds)
            purchase_ids.append(int(entry["purchase_id"]))
        return {
            "value_rub": value_rub,
            "purchase_ids": purchase_ids,
            "skipped_devices": skipped_devices,
        }

    async def calculate_tariff_switch_options_with_hwid(
        self,
        session: AsyncSession,
        sub: Subscription,
        target_tariff: Tariff,
    ) -> Dict[str, Any]:
        options = dict(self.calculate_tariff_switch_options(sub, target_tariff))
        now = datetime.now(timezone.utc)
        credit = await self._hwid_conversion_credit(session, sub, at=now)
        value_rub = float(credit.get("value_rub") or 0)
        options["converted_hwid_value_rub"] = round(value_rub, 2)
        options["converted_hwid_value"] = round(value_rub, 2)
        options["convertible_hwid_purchase_ids"] = list(credit.get("purchase_ids") or [])
        options["nonconverted_hwid_devices"] = int(credit.get("skipped_devices") or 0)
        if value_rub <= 0:
            return options

        if options.get("mode") == "period_to_period":
            target_monthly = float(options.get("target_monthly_rub") or 0)
            hwid_days = math.floor((value_rub / target_monthly) * 30) if target_monthly > 0 else 0
            options["converted_hwid_days"] = max(0, hwid_days)
            options["recalc_days"] = int(options.get("recalc_days") or 0) + max(0, hwid_days)
            options["paid_diff_rub"] = max(
                0,
                math.ceil(float(options.get("paid_diff_rub") or 0) - value_rub),
            )
            return options

        if options.get("mode") == "period_to_traffic":
            rub_per_gb = float(options.get("rub_per_gb") or 0)
            hwid_gb = math.floor(value_rub / rub_per_gb) if rub_per_gb > 0 else 0
            options["converted_hwid_gb"] = max(0, hwid_gb)
            options["converted_gb"] = int(options.get("converted_gb") or 0) + max(0, hwid_gb)
        return options
