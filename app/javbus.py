import asyncio
import random
import re
from pathlib import Path
from urllib.parse import unquote, urljoin

import httpx
from bs4 import BeautifulSoup

from .config import JAVBUS_BASE_URL


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,"
        "*/*;q=0.8"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
}


def normalize_code(raw: str) -> str:
    """
    将番号统一为类似 SSIS-001 的格式。

    支持：
    SSIS-001
    ssis001
    SSIS_001
    SSIS 001
    """

    raw = raw.strip().upper()
    raw = raw.replace("_", "-")
    raw = re.sub(r"\s+", "-", raw)

    match = re.fullmatch(
        r"([A-Z]+)-?(\d+)",
        raw
    )

    if not match:
        raise ValueError(
            "番号格式不正确，例如 SSIS-001"
        )

    prefix, number = match.groups()

    return f"{prefix}-{number}"


async def fetch_text(
    client: httpx.AsyncClient,
    url: str,
    **kwargs
) -> str:
    """
    请求网页，失败自动重试三次。
    """

    last_error = None

    for attempt in range(3):
        try:
            response = await client.get(
                url,
                timeout=20,
                follow_redirects=True,
                **kwargs
            )

            response.raise_for_status()

            return response.text

        except Exception as exc:
            last_error = exc

            print(
                f"[请求失败] 第 {attempt + 1}/3 次："
                f"{type(exc).__name__}: {exc}"
            )

            if attempt < 2:
                await asyncio.sleep(
                    1.5 * (attempt + 1)
                )

    raise last_error


def extract_value(text: str, key: str):
    """
    从 JS 或 HTML 中提取变量值。

    支持以下形式：

    var gid = 45622817370;
    var uc = 0;
    var img = '/pics/cover/xxx.jpg';

    var gid = '123';
    gid = "123";
    gid: '123';
    "gid": "123";
    const gid = '123';
    gid: 123;
    """

    escaped_key = re.escape(key)

    patterns = [
        # var gid = 123;
        rf"\b{escaped_key}\s*=\s*([0-9]+)\s*;?",

        # var gid = 'xxx';
        rf"\b{escaped_key}\s*=\s*['\"]([^'\"]+)['\"]",

        # gid: 'xxx'
        rf"\b{escaped_key}\s*:\s*['\"]([^'\"]+)['\"]",

        # "gid": "xxx"
        rf"['\"]{escaped_key}['\"]\s*:\s*['\"]([^'\"]+)['\"]",

        # gid: 123
        rf"\b{escaped_key}\s*:\s*([0-9]+)",

        # "gid": 123
        rf"['\"]{escaped_key}['\"]\s*:\s*([0-9]+)",
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE
        )

        if match:
            return match.group(1).strip()

    return None


def extract_ajax_params(html: str):
    """
    从页面 HTML / JS 中提取 JavBus AJAX 所需参数。
    """

    result = {
        "gid": extract_value(html, "gid"),
        "uc": extract_value(html, "uc"),
        "img": extract_value(html, "img"),
    }

    print(
        "[参数提取结果]",
        result
    )

    # 这里不能使用 all(result.values())
    # 因为 uc=0，字符串 "0" 虽然是真值，但做明确判断更安全
    if (
        result["gid"] is not None
        and result["uc"] is not None
        and result["img"] is not None
    ):
        return result

    return None


async def query_javbus(raw_code: str) -> dict:
    """
    查询 JavBus 页面并获取 Magnet 信息。
    """

    code = normalize_code(raw_code)

    page_url = f"{JAVBUS_BASE_URL}/{code}"

    print(
        f"[开始请求] {page_url}"
    )

    async with httpx.AsyncClient(
        headers=HEADERS,
        follow_redirects=True
    ) as client:

        html = await fetch_text(
            client,
            page_url
        )

        # 保存网页源码，方便调试
        debug_path = Path(
            "debug_page.html"
        )

        debug_path.write_text(
            html,
            encoding="utf-8"
        )

        print(
            f"[网页已保存] {debug_path.absolute()}"
        )

        print(
            f"[网页长度] {len(html)} 字符"
        )

        soup = BeautifulSoup(
            html,
            "html.parser"
        )

        # 检查是否是 Cloudflare / 验证页面
        lower_html = html.lower()

        blocked_keywords = [
            "just a moment",
            "checking your browser",
            "cf-chl",
            "cloudflare",
            "access denied",
            "captcha",
            "verify you are human",
        ]

        found_block_keyword = [
            keyword
            for keyword in blocked_keywords
            if keyword in lower_html
        ]

        if found_block_keyword:
            print(
                "[警告] 页面可能是验证页，命中关键词：",
                found_block_keyword
            )

        # 提取封面
        image = soup.select_one(
            "a.bigImage img"
        )

        if not image:
            # 尝试其他常见图片选择器
            image = soup.select_one(
                "img"
            )

        if not image:
            raise RuntimeError(
                "页面中没有找到封面，"
                "可能是访问被拦截、页面结构变化或番号不存在。"
                "网页已保存为 debug_page.html"
            )

        title = (
            image.get("title")
            or image.get("alt")
            or code
        )

        cover = image.get(
            "src",
            ""
        ).strip()

        if cover:
            cover = urljoin(
                JAVBUS_BASE_URL + "/",
                cover
            )

        print(
            f"[标题] {title}"
        )

        print(
            f"[封面] {cover}"
        )

        # 提取所有 script
        scripts = soup.find_all(
            "script"
        )

        ajax_params = None

        print(
            f"[Script 数量] {len(scripts)}"
        )

        for index, script in enumerate(
            scripts,
            start=1
        ):
            script_text = script.get_text(
                "",
                strip=False
            )

            lower_script = script_text.lower()

            # 只检查可能相关的脚本
            if (
                "gid" not in lower_script
                and "uc" not in lower_script
                and "img" not in lower_script
            ):
                continue

            print(
                f"[发现疑似参数脚本] 第 {index} 个 script，"
                f"长度：{len(script_text)}"
            )

            params = extract_ajax_params(
                script_text
            )

            if params:
                ajax_params = params

                print(
                    "[成功提取 AJAX 参数]",
                    ajax_params
                )

                break

        # 如果逐个 script 没找到，再从整个 HTML 搜索一次
        if not ajax_params:
            print(
                "[提示] 单独扫描 script 没找到，"
                "尝试扫描整个 HTML"
            )

            ajax_params = extract_ajax_params(
                html
            )

        if not ajax_params:
            raise RuntimeError(
                "没有找到 gid / uc / img，"
                "可能是 JavBus 页面结构已改变，"
                "或者当前返回的是验证页面。"
                "网页已保存为 debug_page.html"
            )

        floor = random.randint(
            1,
            1000
        )

        ajax_url = (
            f"{JAVBUS_BASE_URL}/ajax/"
            f"uncledatoolsbyajax.php"
            f"?gid={ajax_params['gid']}"
            f"&uc={ajax_params['uc']}"
            f"&img={ajax_params['img']}"
            f"&lang=zh"
            f"&floor={floor}"
        )

        print(
            f"[请求 AJAX] {ajax_url}"
        )

        ajax_html = await fetch_text(
            client,
            ajax_url,
            headers={
                "Referer": page_url,
                "X-Requested-With": "XMLHttpRequest",
            }
        )

        # 保存 AJAX 返回内容
        Path(
            "debug_ajax.html"
        ).write_text(
            ajax_html,
            encoding="utf-8"
        )

        print(
            f"[AJAX 返回长度] {len(ajax_html)} 字符"
        )

        ajax_soup = BeautifulSoup(
            ajax_html,
            "html.parser"
        )

        magnets = []

        for row in ajax_soup.select(
            "tr"
        ):
            link = row.select_one(
                "td:nth-child(2) a"
            )

            if not link:
                continue

            href = link.get(
                "href",
                ""
            ).strip()

            if not href:
                continue

            magnets.append({
                "link": unquote(href),
                "size": link.get_text(
                    " ",
                    strip=True
                ),
            })

        print(
            f"[Magnet 数量] {len(magnets)}"
        )

        return {
            "code": code,
            "title": title,
            "cover": cover,
            "magnets": magnets,
        }