"""Point-in-time A/H large-cap universe helpers.

The training CSV contract intentionally remains OHLCVA-only.  Membership is
stored in a sidecar and used to decide whether a forecast origin is eligible.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from io import BytesIO
import re
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd


MEMBERSHIP_COLUMNS = (
    "symbol",
    "market",
    "index_name",
    "member_from",
    "member_to",
    "source_url",
)


@dataclass(frozen=True)
class MembershipInterval:
    symbol: str
    market: str
    index_name: str
    member_from: pd.Timestamp
    member_to: pd.Timestamp
    source_url: str = ""


def normalize_symbol(symbol: Any, market: str) -> str:
    """Normalize symbols to the filenames used by this repository."""

    text = str(symbol).strip().upper()
    text = text.removeprefix("SH.").removeprefix("SZ.")
    text = text.removeprefix("SH").removeprefix("SZ")
    text = text.removesuffix(".SH").removesuffix(".SZ").removesuffix(".HK")
    digits = re.sub(r"\D", "", text)
    if not digits:
        raise ValueError(f"invalid {market} symbol: {symbol!r}")
    return digits.zfill(6 if market == "A" else 5)


def snapshots_to_intervals(
    snapshots: Sequence[tuple[Any, Iterable[str], str]],
    *,
    market: str,
    index_name: str,
    end_date: Any,
) -> list[MembershipInterval]:
    """Convert dated complete constituent snapshots into closed intervals."""

    ordered = sorted(
        (
            pd.Timestamp(date).normalize(),
            {normalize_symbol(symbol, market) for symbol in symbols},
            str(source_url),
        )
        for date, symbols, source_url in snapshots
    )
    if not ordered:
        return []

    final_end = pd.Timestamp(end_date).normalize()
    active: dict[str, tuple[pd.Timestamp, str]] = {}
    intervals: list[MembershipInterval] = []
    for date, members, source_url in ordered:
        if date > final_end:
            break
        for symbol in sorted(set(active).difference(members)):
            start, original_source = active.pop(symbol)
            intervals.append(
                MembershipInterval(
                    symbol=symbol,
                    market=market,
                    index_name=index_name,
                    member_from=start,
                    member_to=date - pd.Timedelta(days=1),
                    source_url=original_source,
                )
            )
        for symbol in sorted(members.difference(active)):
            active[symbol] = (date, source_url)

    for symbol, (start, source_url) in sorted(active.items()):
        intervals.append(
            MembershipInterval(
                symbol=symbol,
                market=market,
                index_name=index_name,
                member_from=start,
                member_to=final_end,
                source_url=source_url,
            )
        )
    return sorted(intervals, key=lambda item: (item.market, item.symbol, item.member_from))


def intervals_to_frame(intervals: Iterable[MembershipInterval]) -> pd.DataFrame:
    rows = [
        {
            "symbol": item.symbol,
            "market": item.market,
            "index_name": item.index_name,
            "member_from": item.member_from.date().isoformat(),
            "member_to": item.member_to.date().isoformat(),
            "source_url": item.source_url,
        }
        for item in intervals
    ]
    return pd.DataFrame(rows, columns=MEMBERSHIP_COLUMNS)


def load_membership_intervals(path: str | Any) -> dict[tuple[str, str], list[tuple[pd.Timestamp, pd.Timestamp]]]:
    frame = pd.read_csv(path)
    missing = set(MEMBERSHIP_COLUMNS).difference(frame.columns)
    if missing:
        raise ValueError(f"membership sidecar missing columns: {sorted(missing)}")
    grouped: dict[tuple[str, str], list[tuple[pd.Timestamp, pd.Timestamp]]] = defaultdict(list)
    for row in frame.itertuples(index=False):
        market = str(row.market)
        symbol = normalize_symbol(row.symbol, market)
        grouped[(market, symbol)].append(
            (pd.Timestamp(row.member_from).normalize(), pd.Timestamp(row.member_to).normalize())
        )
    return {
        key: merge_date_intervals(values)
        for key, values in grouped.items()
    }


def merge_date_intervals(
    intervals: Iterable[tuple[pd.Timestamp, pd.Timestamp]],
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    ordered = sorted((pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize()) for start, end in intervals)
    merged: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    for start, end in ordered:
        if end < start:
            raise ValueError(f"membership interval ends before it starts: {start} > {end}")
        if not merged or start > merged[-1][1] + pd.Timedelta(days=1):
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged


def is_member_on(
    intervals: Mapping[tuple[str, str], Sequence[tuple[pd.Timestamp, pd.Timestamp]]],
    *,
    market: str,
    symbol: str,
    date: Any,
) -> bool:
    point = pd.Timestamp(date).normalize()
    key = (market, normalize_symbol(symbol, market))
    return any(start <= point <= end for start, end in intervals.get(key, ()))


def filter_starts_by_membership(
    starts: Iterable[int],
    timestamps: Sequence[Any] | pd.Series,
    *,
    lookback: int,
    market: str,
    symbol: str,
    intervals: Mapping[tuple[str, str], Sequence[tuple[pd.Timestamp, pd.Timestamp]]],
) -> list[int]:
    """Keep windows whose forecast origin is an active index member."""

    ts = pd.to_datetime(pd.Series(timestamps), errors="raise").reset_index(drop=True)
    return [
        int(start)
        for start in starts
        if is_member_on(
            intervals,
            market=market,
            symbol=symbol,
            date=ts.iloc[int(start) + lookback - 1],
        )
    ]


def fetch_hang_seng_snapshots(
    *,
    start_date: str,
    end_date: str,
    session: Any | None = None,
) -> dict[str, list[tuple[pd.Timestamp, set[str], str]]]:
    """Fetch complete HSI/HSCEI/HSTECH snapshots from official review PDFs."""

    import pdfplumber
    import requests

    client = session or requests.Session()
    base = "https://www.hsi.com.hk"
    catalog_url = f"{base}/data/eng/download/press-releases.json"
    catalog = client.get(catalog_url, timeout=30).json()
    records = [item for section in catalog["contentList"] for item in section["resourcesList"]]
    reviews = sorted(
        (item for item in records if "Review Results" in item.get("title", "")),
        key=lambda item: item["lastUpdate"],
    )
    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize()
    names = {1: "HSI", 2: "HSCEI", 3: "HSTECH"}
    snapshots: dict[str, list[tuple[pd.Timestamp, set[str], str]]] = defaultdict(list)

    for record in reviews:
        url = f"{base}{record['url']}"
        response = client.get(url, timeout=60)
        response.raise_for_status()
        with pdfplumber.open(BytesIO(response.content)) as pdf:
            first_text = "\n".join((page.extract_text() or "") for page in pdf.pages[:3])
            effective = _hang_seng_effective_date(first_text)
            if effective < start or effective > end:
                continue
            constituents = _hang_seng_pdf_constituents(pdf.pages)
        for appendix, index_name in names.items():
            members = constituents[appendix]
            if not members:
                raise ValueError(f"{url} did not yield {index_name} constituents")
            snapshots[index_name].append((effective, members, url))
    return dict(snapshots)


def _hang_seng_effective_date(text: str) -> pd.Timestamp:
    patterns = (
        r"take\s*\|?\s*effect on\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})",
        r"Effective\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return pd.Timestamp(match.group(1)).normalize()
    raise ValueError("Hang Seng review PDF does not contain an effective date")


def _hang_seng_pdf_constituents(pages: Sequence[Any]) -> dict[int, set[str]]:
    result: dict[int, set[str]] = {1: set(), 2: set(), 3: set()}
    for page in pages:
        text = page.extract_text() or ""
        appendix_match = re.search(r"Appendix\s+([123])", text[:120])
        if not appendix_match:
            continue
        appendix = int(appendix_match.group(1))
        for table in page.extract_tables():
            if not table or len(table[0]) < 4:
                continue
            header = " ".join(str(value or "") for value in table[0])
            if not header.startswith("Code ") or "FAF" not in header:
                continue
            for row in table[1:]:
                codes = [value.strip() for value in str(row[0] or "").splitlines()]
                after = [value.strip() for value in str(row[-1] or "").splitlines()]
                if len(codes) != len(after):
                    continue
                for code, after_weight in zip(codes, after):
                    if re.fullmatch(r"\d{1,5}", code) and after_weight not in {"", "-"}:
                        result[appendix].add(normalize_symbol(code, "HK"))
    expected = {2: 50, 3: 30}
    for appendix, count in expected.items():
        if len(result[appendix]) != count:
            raise ValueError(
                f"Hang Seng Appendix {appendix} expected {count} constituents, "
                f"found {len(result[appendix])}"
            )
    if not 50 <= len(result[1]) <= 120:
        raise ValueError(f"Hang Seng Appendix 1 has implausible size: {len(result[1])}")
    return result


def fetch_csi300_snapshots(
    *,
    start_date: str,
    end_date: str,
    probe_days: int = 31,
) -> list[tuple[pd.Timestamp, set[str], str]]:
    """Fetch historical CSI300 snapshots and refine every detected change date."""

    import baostock as bs

    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize()
    source = "http://baostock.com/baostock/index.php/沪深300成分股"
    login = bs.login()
    if login.error_code != "0":
        raise RuntimeError(f"BaoStock login failed: {login.error_msg}")
    cache: dict[pd.Timestamp, set[str]] = {}

    def query(date: pd.Timestamp) -> set[str]:
        date = date.normalize()
        if date in cache:
            return cache[date]
        rows: set[str] = set()
        for attempt in range(2):
            result = bs.query_hs300_stocks(date=date.date().isoformat())
            rows.clear()
            while result.error_code == "0" and result.next():
                values = result.get_row_data()
                rows.add(normalize_symbol(values[1], "A"))
            if result.error_code == "0":
                break
            if attempt == 0:
                bs.login()
        if result.error_code != "0":
            raise RuntimeError(f"BaoStock CSI300 query failed on {date.date()}: {result.error_msg}")
        if rows and len(rows) != 300:
            raise ValueError(f"BaoStock CSI300 snapshot on {date.date()} has {len(rows)} members")
        cache[date] = rows
        return rows

    try:
        probes = list(pd.date_range(start, end, freq=f"{probe_days}D"))
        if not probes or probes[-1] != end:
            probes.append(end)
        observed: list[tuple[pd.Timestamp, set[str]]] = []
        for index, date in enumerate(probes, start=1):
            members = query(date)
            if members:
                observed.append((date, members))
            if index % 12 == 0 or index == len(probes):
                print(f"[CSI300 universe] {index}/{len(probes)} probes", flush=True)
        refined: list[tuple[pd.Timestamp, set[str]]] = [observed[0]]
        for date, members in observed[1:]:
            previous_date, previous_members = refined[-1]
            if members == previous_members:
                continue
            low = previous_date + pd.Timedelta(days=1)
            high = date
            while low < high:
                midpoint = low + pd.Timedelta(days=(high - low).days // 2)
                midpoint_members = query(midpoint)
                if midpoint_members and midpoint_members != previous_members:
                    high = midpoint
                else:
                    low = midpoint + pd.Timedelta(days=1)
            first_members = query(low)
            refined.append((low, first_members if first_members else members))
        return [(date, members, source) for date, members in refined]
    finally:
        bs.logout()
