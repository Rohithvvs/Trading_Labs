from __future__ import annotations

import requests
from ..config import settings


class MarketInfoService:
    """Best-effort company profile and corporate events lookup.

    If `settings.company_info_api_url` is configured, this service will attempt
    to query it with the provided symbol. Otherwise it returns an empty dict.
    """

    def __init__(self) -> None:
        self.base = getattr(settings, "company_info_api_url", None)
        self._nifty_profile_cache: dict[str, dict] | None = None

    def get_company_profile(self, symbol: str) -> dict:
        normalized_symbol = self._normalize_symbol(symbol)
        profile: dict = {}

        if not self.base:
            profile.update(self._get_nifty_csv_profile(normalized_symbol))
            return profile

        try:
            url = f"{self.base.rstrip('/')}/company/{normalized_symbol}"
            resp = requests.get(url, timeout=6)
            if resp.status_code == 200:
                data = resp.json()
                profile.update(
                    {
                        "company_name": data.get("company_name") or data.get("name") or data.get("short_name") or None,
                        "company_description": data.get("company_description") or data.get("description") or None,
                        "sector": data.get("sector") or data.get("industry_sector") or None,
                        "industry": data.get("industry") or data.get("industry_group") or None,
                        "market_cap": data.get("market_cap") or data.get("marketCapitalization") or None,
                        "corporate_events": data.get("corporate_events") or data.get("events") or None,
                    }
                )
        except Exception:
            pass

        # The bundled NIFTY CSV is a reliable fallback for listed-name and industry.
        csv_profile = self._get_nifty_csv_profile(normalized_symbol)
        return {**csv_profile, **{key: value for key, value in profile.items() if value not in (None, "", {})}}

    def _get_nifty_csv_profile(self, symbol: str) -> dict:
        if self._nifty_profile_cache is None:
            self._nifty_profile_cache = self._load_nifty_profiles()
        return dict(self._nifty_profile_cache.get(symbol, {}))

    def _load_nifty_profiles(self) -> dict[str, dict]:
        profiles: dict[str, dict] = {}
        try:
            csv_path = settings.ROOT_DIR / settings.nifty500_csv_path if hasattr(settings, "ROOT_DIR") else None
        except Exception:
            csv_path = None

        try:
            from ..config.settings import ROOT_DIR

            csv_path = ROOT_DIR / settings.nifty500_csv_path
        except Exception:
            return profiles

        if not csv_path.exists():
            return profiles

        try:
            from .universe_csv import load_unique_nifty500_csv_rows

            for parsed in load_unique_nifty500_csv_rows(csv_path):
                symbol_key = self._normalize_symbol(
                    f"{parsed['symbol']}-{parsed['series']}" if parsed["series"] else parsed["symbol"]
                )
                industry = parsed["industry"] or None
                company_name = parsed["company_name"] or None
                profiles[symbol_key] = {
                    "company_name": company_name,
                    "company_description": company_name,
                    "sector": industry,
                    "industry": industry,
                }
        except Exception:
            return profiles
        return profiles

    def _normalize_symbol(self, symbol: str) -> str:
        normalized = symbol.strip().upper()
        if ":" in normalized:
            _, normalized = normalized.split(":", 1)
        return normalized.replace("-EQ", "")
