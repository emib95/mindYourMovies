from ipaddress import ip_address

import httpx
from starlette.datastructures import Headers

from app.config import Settings
from app.schemas import LocationResponse


COUNTRY_HEADERS = (
    "cf-ipcountry",
    "x-vercel-ip-country",
    "x-country-code",
    "x-appengine-country",
)
IP_HEADERS = (
    "cf-connecting-ip",
    "x-real-ip",
    "x-forwarded-for",
)
UNKNOWN_COUNTRY_CODES = {"", "XX", "ZZ", "T1"}


class LocationResolver:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def resolve(self, headers: Headers, client_host: str | None) -> LocationResponse:
        header_region = self._country_from_headers(headers)
        if header_region:
            return LocationResponse(region=header_region, source="header", detected=True)

        client_ip = self._client_ip(headers, client_host)
        if client_ip:
            ip_region = await self._country_from_ip(client_ip)
            if ip_region:
                return LocationResponse(region=ip_region, source="ip", detected=True)

        return LocationResponse(
            region=self._normalize_country(self.settings.tmdb_region) or "GB",
            source="default",
            detected=False,
        )

    def _country_from_headers(self, headers: Headers) -> str | None:
        for header in COUNTRY_HEADERS:
            country = self._normalize_country(headers.get(header))
            if country:
                return country
        return None

    def _client_ip(self, headers: Headers, client_host: str | None) -> str | None:
        for header in IP_HEADERS:
            value = headers.get(header)
            if not value:
                continue
            for candidate in value.split(","):
                public_ip = self._public_ip(candidate.strip())
                if public_ip:
                    return public_ip

        return self._public_ip(client_host or "")

    async def _country_from_ip(self, client_ip: str) -> str | None:
        url = self.settings.geolocation_api_url.format(ip=client_ip)
        try:
            async with httpx.AsyncClient(timeout=4) as client:
                response = await client.get(url)
                response.raise_for_status()
        except httpx.HTTPError:
            return None

        try:
            payload = response.json()
        except ValueError:
            return None

        if payload.get("success") is False:
            return None

        return self._normalize_country(payload.get("country_code"))

    def _normalize_country(self, value: str | None) -> str | None:
        country = (value or "").strip().upper()
        if country in UNKNOWN_COUNTRY_CODES or len(country) != 2 or not country.isalpha():
            return None
        return country

    def _public_ip(self, value: str) -> str | None:
        candidate = value.strip()
        if not candidate:
            return None

        if candidate.count(":") == 1 and "." in candidate:
            candidate = candidate.rsplit(":", 1)[0]

        try:
            parsed_ip = ip_address(candidate)
        except ValueError:
            return None

        if (
            parsed_ip.is_private
            or parsed_ip.is_loopback
            or parsed_ip.is_link_local
            or parsed_ip.is_multicast
            or parsed_ip.is_reserved
            or parsed_ip.is_unspecified
        ):
            return None

        return str(parsed_ip)
