"""Drive the site's real form, then extract all displayed result pages."""

from dataclasses import dataclass
import csv
import json
from pathlib import Path
import re
import time
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.sync_api import Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from .config import PERIOD_LABELS, SearchConfig, Settings
from .ocr import read_four_digits


ENTRY_URL = "https://www.gov.il/he/service/real_estate_information"
PUBLISHED_SYSTEM_URL = (
    "https://nadlan.taxes.gov.il/svinfonadlan2010/"
    "startpageNadlanNewDesign.aspx?ProcessKey=cb2fc2f5-08db-4099-9d1e-8eb9f6bcda42"
)
CAPTCHA_IMAGE = "#ContentUsersPage_RadCaptcha1_CaptchaImageUP"


@dataclass(frozen=True)
class BrowserResult:
    columns: list[str]
    rows: list[list[str]]
    reported_count: int
    page_count: int
    url: str
    csv_path: Path


def _open_form(context, page: Page) -> Page:
    response = page.goto(ENTRY_URL, wait_until="domcontentloaded", timeout=45000)
    if (response and response.status == 403) or "cloudflare" in page.title().lower():
        page.goto(PUBLISHED_SYSTEM_URL, wait_until="domcontentloaded", timeout=45000)
        return page
    link = page.get_by_role("link", name=re.compile("כניסה למערכת"))
    if link.count() < 1:
        raise RuntimeError("Government page has no 'כניסה למערכת' link")
    preferred = next(
        (item for item in link.all() if "taxes.gov.il" in (item.get_attribute("href") or "")),
        link.first,
    )
    href = preferred.get_attribute("href")
    before = set(context.pages)
    preferred.click()
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        new_pages = [item for item in context.pages if item not in before]
        if new_pages:
            page = new_pages[-1]
            page.wait_for_load_state("domcontentloaded", timeout=45000)
            break
        if "nadlan.taxes.gov.il" in page.url:
            break
        page.wait_for_timeout(250)
    if "nadlan.taxes.gov.il" not in page.url and href:
        page.goto(urljoin(ENTRY_URL, href), wait_until="domcontentloaded", timeout=45000)
    if "nadlan.taxes.gov.il" not in page.url:
        raise RuntimeError("The government entry did not open the tax search form")
    return page


def _select(page: Page, suffix: str, label: str) -> None:
    control = page.locator(f'select[name$="{suffix}"]')
    if control.count() != 1:
        raise RuntimeError(f"Missing dropdown {suffix}")
    option = control.locator("option").filter(has_text=re.compile(r"^\s*" + re.escape(label) + r"\s*$"))
    if option.count() != 1:
        available = control.locator("option").all_inner_texts()
        raise RuntimeError(f"Option {label!r} missing from {suffix}; choices: {available}")
    control.select_option(label=option.inner_text())


def _fill_filters(page: Page, search: SearchConfig) -> None:
    radio = page.locator('input[name$="rbYeshuvOrGush"][value="rbMegush"]')
    if radio.count() != 1:
        raise RuntimeError("Gush search mode is unavailable")
    radio.check()
    for suffix, value in (("txtmegusha", search.gush_from), ("txtadGush", search.gush_to)):
        field = page.locator(f'input[name$="{suffix}"]')
        if field.count() != 1:
            raise RuntimeError(f"Missing input {suffix}")
        field.fill(str(value))
    _select(page, "DDLTypeNehes", search.property_type)
    page.locator('select[name$="DDLMahutIska"] option').filter(
        has_text=re.compile(r"^\s*" + re.escape(search.transaction_type) + r"\s*$")
    ).wait_for(state="attached", timeout=15000)
    _select(page, "DDLMahutIska", search.transaction_type)
    _select(page, "DDLDateType", PERIOD_LABELS[search.period])


def _download_captcha(page: Page, old_src: str | None, directory: Path) -> Path:
    image = page.locator(CAPTCHA_IMAGE)
    image.wait_for(state="visible", timeout=15000)
    try:
        page.wait_for_function(
            """old => {
              const img = document.querySelector('#ContentUsersPage_RadCaptcha1_CaptchaImageUP');
              return img && img.getAttribute('src') !== old && img.complete && img.naturalWidth > 0;
            }""",
            arg=old_src,
            timeout=15000,
        )
    except PlaywrightTimeoutError:
        if old_src is not None:
            raise RuntimeError("The CAPTCHA did not refresh")
    for _ in range(3):
        src = image.get_attribute("src")
        if not src:
            continue
        response = page.request.get(urljoin(page.url, src), headers={"Referer": page.url}, timeout=15000)
        if not response.ok:
            raise RuntimeError(f"CAPTCHA download returned HTTP {response.status}")
        content_type = response.headers.get("content-type", "").split(";")[0].lower()
        suffix = {"image/jpeg": ".jpg", "image/png": ".png"}.get(content_type)
        if not suffix:
            raise RuntimeError(f"OCR cannot read CAPTCHA format {content_type!r}")
        if image.get_attribute("src") == src:
            path = directory / f"captcha{suffix}"
            path.write_bytes(response.body())
            return path
    raise RuntimeError("CAPTCHA changed during download")


def _result_page(context) -> Page | None:
    for page in reversed(context.pages):
        if page.is_closed():
            continue
        if "infonadlanperut" in page.url.lower():
            return page
        try:
            if page.locator('[id*="GridMulti"]').count():
                return page
        except Exception:
            pass
    return None


def _submit_captcha(context, page: Page, captcha: Path, settings: Settings, directory: Path) -> Page:
    image = page.locator(CAPTCHA_IMAGE)
    input_box = page.locator("#ContentUsersPage_RadCaptcha1_CaptchaTextBox")
    confirm = page.locator("#ContentUsersPage_btnIshur")
    if input_box.count() != 1 or confirm.count() != 1:
        raise RuntimeError("CAPTCHA input or confirmation button is missing")
    for attempt in range(settings.max_captcha_attempts):
        try:
            digits = read_four_digits(captcha)
        except ValueError:
            if attempt + 1 == settings.max_captcha_attempts:
                break
            old = image.get_attribute("src")
            page.locator("#ContentUsersPage_RadCaptcha1_CaptchaLinkButton").click()
            captcha = _download_captcha(page, old, directory)
            continue
        old = image.get_attribute("src")
        input_box.fill(digits)
        confirm.click()
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            result = _result_page(context)
            if result:
                result.wait_for_load_state("domcontentloaded")
                return result
            if page.is_closed():
                break
            if image.is_visible():
                new = image.get_attribute("src")
                if new and new != old:
                    captcha = _download_captcha(page, old, directory)
                    break
            page.wait_for_timeout(500)
        else:
            raise RuntimeError("No result or refreshed CAPTCHA appeared within 45 seconds")
    raise RuntimeError(f"No CAPTCHA accepted after {settings.max_captcha_attempts} attempts")


def _parse_results(html: str) -> tuple[list[str], list[list[str]], int, int, int]:
    soup = BeautifulSoup(html, "html.parser")
    count_text = soup.select_one("#lblresh")
    page_text = soup.select_one("#lblPage")
    count_match = re.search(r"\d+", count_text.get_text(" ", strip=True)) if count_text else None
    page_match = re.search(r"(\d+)\s+מתוך\s+(\d+)", page_text.get_text(" ", strip=True)) if page_text else None
    if not count_match or not page_match:
        raise RuntimeError("Results count or pagination label is missing")
    current, total = map(int, page_match.groups())
    table = soup.select_one('table[id*="GridMulti"]')
    if table is None and int(count_match.group()) > 0:
        raise RuntimeError("Transaction table is missing")
    if table is None:
        return [], [], int(count_match.group()), current, total
    headers = [cell.get_text(" ", strip=True) for cell in table.select("tr:first-child > th")]
    rows = []
    for tr in table.find_all("tr"):
        if tr.find_parent("table") is not table:
            continue
        cells = tr.find_all("td", recursive=False)
        if cells:
            if len(cells) == 1 and cells[0].has_attr("colspan") and cells[0].select('a[href*="Page$"]'):
                continue  # ASP.NET puts pagination links in a table row.
            rows.append([cell.get_text(" ", strip=True) for cell in cells])
    if rows and (not headers or any(len(row) != len(headers) for row in rows)):
        raise RuntimeError("Results table columns did not match its header")
    return headers, rows, int(count_match.group()), current, total


def _collect_results(page: Page, directory: Path, settings: Settings) -> BrowserResult:
    all_rows: list[list[str]] = []
    columns: list[str] = []
    expected_count = None
    total_pages = None
    result_url = page.url
    for expected_page in range(1, settings.max_pages + 1):
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(750)
        html = page.content()
        (directory / f"page_{expected_page:03}.html").write_text(html, encoding="utf-8")
        current_columns, rows, count, current, total = _parse_results(html)
        if current != expected_page:
            raise RuntimeError(f"Expected result page {expected_page}, got {current}")
        if expected_count is None:
            expected_count, total_pages, columns = count, total, current_columns
            if total > settings.max_pages:
                raise RuntimeError(f"Result has {total} pages; max_pages is {settings.max_pages}")
        elif count != expected_count or current_columns != columns or total != total_pages:
            raise RuntimeError("Results changed while paging")
        (directory / f"page_{current:03}.txt").write_text(page.locator("body").inner_text(), encoding="utf-8")
        if current == 1:
            page.screenshot(path=str(directory / "results.png"), full_page=True)
        all_rows.extend(rows)
        if current == total_pages:
            break
        next_page = current + 1
        link = page.locator(f'a[href*="Page${next_page}"]')
        if link.count() != 1:
            raise RuntimeError(f"Cannot find pagination link to page {next_page}; no partial result saved")
        link.click()
        page.wait_for_function(
            """expected => {
              const label = document.querySelector('#lblPage');
              return label && label.textContent.trim().startsWith('דף ' + expected + ' ');
            }""",
            arg=next_page,
            timeout=30000,
        )
    if expected_count is None or len(all_rows) != expected_count:
        raise RuntimeError(f"Collected {len(all_rows)} rows; site reported {expected_count}")
    csv_path = directory / "transactions.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        if columns:
            writer.writerow(columns)
        writer.writerows(all_rows)
    (directory / "results.json").write_text(
        json.dumps({"columns": columns, "rows": all_rows, "count": expected_count, "pages": total_pages, "url": result_url}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return BrowserResult(columns, all_rows, expected_count, total_pages, result_url, csv_path)


def run_search(search: SearchConfig, settings: Settings, directory: Path) -> BrowserResult:
    directory.mkdir(parents=True, exist_ok=False)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=settings.headless)
        try:
            context = browser.new_context()
            page = _open_form(context, context.new_page())
            try:
                _fill_filters(page, search)
                image = page.locator(CAPTCHA_IMAGE)
                old = image.get_attribute("src") if image.count() else None
                page.locator("#ContentUsersPage_btnHipus").click()
                captcha = _download_captcha(page, old, directory)
                result_page = _submit_captcha(context, page, captcha, settings, directory)
                return _collect_results(result_page, directory, settings)
            except Exception:
                if not page.is_closed():
                    try:
                        page.screenshot(path=str(directory / "error.png"), full_page=True)
                    except Exception:
                        pass
                raise
            finally:
                context.close()
        finally:
            browser.close()
