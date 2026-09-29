import asyncio
import ipaddress
import logging
import random
import re
import socket
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from .config import (
    JAVBUS_BASE_URL,
    MAX_CONCURRENT_FETCHES,
    UPSTREAM_ALLOWED_HOSTS,
)
from .database import get_cache, set_cache


logger = logging.getLogger(__name__)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


class JavBusError(Exception):
    """Base error for lookup failures that can be shown safely to users."""


class InvalidCodeError(JavBusError):
    pass


class NotFoundError(JavBusError):
    pass


class BlockedError(JavBusError):
    pass


class ParseError(JavBusError):
    pass


class FetchError(JavBusError):
    pass


_client: httpx.AsyncClient | None = None
_fetch_semaphore = asyncio.Semaphore(MAX_CONCURRENT_FETCHES)
_inflight: dict[str, asyncio.Task] = {}
_inflight_guard = asyncio.Lock()


async def start_http_client() -> None:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            headers=HEADERS,
            timeout=httpx.Timeout(20),
            follow_redirects=False,
            limits=httpx.Limits(max_connections=MAX_CONCURRENT_FETCHES * 2),
        )


async def close_http_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def download_cover(url: str, referer: str) -> bytes:
    await start_http_client()
    assert _client is not None
    async with _fetch_semaphore:
        response = await _request(
            _client, url, headers={"Referer": referer, "Accept": "image/*"}
        )
        response.raise_for_status()
        if len(response.content) > 10 * 1024 * 1024:
            raise FetchError("Cover image exceeds 10 MB.")
        return response.content


def normalize_code(raw: str) -> str:
    normalized = re.sub(r"\s+", "-", raw.strip().upper().replace("_", "-"))
    match = re.fullmatch(r"([A-Z]+)-?(\d+)", normalized)
    if not match:
        raise InvalidCodeError("番号格式不正确，请使用类似 SSIS-001 的格式。")
    prefix, number = match.groups()
    return f"{prefix}-{number}"


async def fetch_text(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> str:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = await _request(client, url, params=params, headers=headers)
            if response.status_code in {429, 500, 502, 503, 504}:
                response.raise_for_status()
            response.raise_for_status()
            return response.text
        except httpx.HTTPStatusError as exc:
            last_error = exc
            if exc.response.status_code < 500 and exc.response.status_code != 429:
                raise FetchError(
                    f"目标站返回 HTTP {exc.response.status_code}"
                ) from exc
        except httpx.RequestError as exc:
            last_error = exc
        if attempt < 2:
            await asyncio.sleep(1.5 * (attempt + 1))
    raise FetchError("请求目标站失败，请稍后重试。") from last_error


async def _validate_target(url: str) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if (
        parsed.scheme not in {"http", "https"}
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in {None, 80, 443}
        or host not in UPSTREAM_ALLOWED_HOSTS
    ):
        raise FetchError("Upstream URL is not permitted by the host allowlist.")
    try:
        addresses = await asyncio.get_running_loop().getaddrinfo(
            host,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise FetchError("Could not resolve the upstream host.") from exc
    if not addresses or any(
        not ipaddress.ip_address(item[4][0].split("%")[0]).is_global
        for item in addresses
    ):
        raise FetchError("Upstream host resolves to a non-public IP address.")


async def _request(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    current_url = url
    current_params = params
    current_headers = headers
    for redirect_count in range(6):
        await _validate_target(current_url)
        response = await client.get(
            current_url,
            params=current_params,
            headers=current_headers,
        )
        if response.status_code not in {301, 302, 303, 307, 308}:
            return response
        location = response.headers.get("Location")
        if not location or redirect_count == 5:
            raise FetchError("Too many or malformed upstream redirects.")
        next_url = urljoin(str(response.url), location)
        if urlparse(next_url).hostname != urlparse(current_url).hostname:
            current_headers = {
                key: value for key, value in (current_headers or {}).items()
                if key.lower() not in {"authorization", "cookie", "referer"}
            }
        current_url = next_url
        current_params = None
    raise FetchError("Too many upstream redirects.")


def extract_value(text: str, key: str) -> str | None:
    escaped_key = re.escape(key)
    patterns = (
        rf"\b{escaped_key}\s*=\s*([0-9]+)\s*;?",
        rf"\b{escaped_key}\s*=\s*['\"]([^'\"]+)['\"]",
        rf"\b{escaped_key}\s*:\s*['\"]([^'\"]+)['\"]",
        rf"['\"]{escaped_key}['\"]\s*:\s*['\"]([^'\"]+)['\"]",
        rf"\b{escaped_key}\s*:\s*([0-9]+)",
        rf"['\"]{escaped_key}['\"]\s*:\s*([0-9]+)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def extract_ajax_params(page_html: str) -> dict[str, str] | None:
    values = {key: extract_value(page_html, key) for key in ("gid", "uc", "img")}
    if all(value is not None for value in values.values()):
        return values  # type: ignore[return-value]
    return None


def _check_blocked(page_html: str) -> None:
    lowered = page_html.lower()
    blocked_markers = (
        "just a moment", "checking your browser", "cf-chl",
        "access denied", "captcha", "verify you are human",
    )
    if any(marker in lowered for marker in blocked_markers):
        raise BlockedError("目标站要求验证或暂时拒绝访问。")


async def _scrape(code: str, client: httpx.AsyncClient) -> dict:
    page_url = f"{JAVBUS_BASE_URL}/{code}"
    async with _fetch_semaphore:
        page_html = await fetch_text(client, page_url)
        _check_blocked(page_html)

        soup = BeautifulSoup(page_html, "html.parser")
        image_link = soup.select_one("a.bigImage")
        image = soup.select_one("a.bigImage img")
        if not image_link and not image:
            image = soup.select_one("img")
        if not image_link and not image:
            if re.search(r"404|not found|不存在", soup.get_text(" ", strip=True), re.I):
                raise NotFoundError("没有找到这个番号。")
            raise ParseError("页面中没有找到封面，目标站页面可能已变化。")

        title = (image.get("title") or image.get("alt") or code) if image else code
        cover = (image_link.get("href", "") if image_link else image.get("src", "")).strip()
        cover = urljoin(f"{JAVBUS_BASE_URL}/", cover) if cover else ""
        ajax_params = None
        for script in soup.find_all("script"):
            script_text = script.get_text("", strip=False)
            if any(key in script_text.lower() for key in ("gid", "uc", "img")):
                ajax_params = extract_ajax_params(script_text)
                if ajax_params:
                    break
        if not ajax_params:
            ajax_params = extract_ajax_params(page_html)
        if not ajax_params:
            raise ParseError("页面缺少磁力列表所需参数，目标站页面可能已变化。")

        ajax_url = f"{JAVBUS_BASE_URL}/ajax/uncledatoolsbyajax.php"
        ajax_html = await fetch_text(
            client,
            ajax_url,
            params={**ajax_params, "lang": "zh", "floor": str(random.randint(1, 1000))},
            headers={"Referer": page_url, "X-Requested-With": "XMLHttpRequest"},
        )
        ajax_soup = BeautifulSoup(ajax_html, "html.parser")
        magnets = []
        for row in ajax_soup.select("tr"):
            link = row.select_one("td:nth-child(2) a")
            href = link.get("href", "").strip() if link else ""
            if href:
                magnets.append({"link": href, "size": link.get_text(" ", strip=True)})
        return {"code": code, "title": title[:500], "cover": cover, "magnets": magnets}


async def query_javbus(raw_code: str) -> dict:
    code = normalize_code(raw_code)
    cached = await get_cache(code)
    if cached is not None:
        return cached

    async with _inflight_guard:
        task = _inflight.get(code)
        if task is None:
            task = asyncio.create_task(_lookup_and_cache(code))
            _inflight[code] = task
            task.add_done_callback(
                lambda finished, lookup_code=code: _lookup_finished(
                    lookup_code, finished
                )
            )
    try:
        return await asyncio.shield(task)
    finally:
        if task.done():
            async with _inflight_guard:
                if _inflight.get(code) is task:
                    _inflight.pop(code, None)


def _lookup_finished(code: str, task: asyncio.Task) -> None:
    if not task.cancelled():
        task.exception()  # Retrieve the exception if every waiting caller was cancelled.
    asyncio.create_task(_remove_finished_lookup(code, task))


async def _remove_finished_lookup(code: str, task: asyncio.Task) -> None:
    async with _inflight_guard:
        if _inflight.get(code) is task:
            _inflight.pop(code, None)


async def _lookup_and_cache(code: str) -> dict:
    cached = await get_cache(code)
    if cached is not None:
        return cached
    await start_http_client()
    assert _client is not None
    try:
        result = await _scrape(code, _client)
    except JavBusError:
        raise
    except Exception as exc:
        logger.exception("Unexpected lookup error for %s", code)
        raise FetchError("查询过程中发生内部错误，请稍后重试。") from exc
    await set_cache(code, result)
    return result
