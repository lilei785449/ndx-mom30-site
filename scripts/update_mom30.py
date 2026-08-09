from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

import pandas as pd
import requests

VERSION = "NDX-MOM30-v1.0"
TOP_N = 30
MAX_SNAPSHOT_LOOKBACK_DAYS = 14
MAX_PERIOD_LOOKBACK_BUSINESS_DAYS = 90

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
STATE_PATH = DATA_DIR / "ndx_mom30_state.json"
LATEST_PATH = DATA_DIR / "ndx_mom30_latest.json"
HISTORY_PATH = DATA_DIR / "ndx_mom30_history.csv"
TOP30_CSV_PATH = DATA_DIR / "ndx_mom30_top30.csv"
ALL_CSV_PATH = DATA_DIR / "ndx_mom30_all.csv"

NASDAQ_EXPORT = (
    "https://indexes.nasdaqomx.com/Index/ExportWeightings/{index}"
    "?tradeDate={trade_date}T00:00:00.000&timeOfDay=EOD.xlsx"
)


class Mom30Error(RuntimeError):
    pass


def ny_today() -> pd.Timestamp:
    return pd.Timestamp.now(tz=ZoneInfo("America/New_York")).tz_localize(None).normalize()


def _norm(value) -> str:
    if pd.isna(value):
        return ""
    return " ".join(str(value).strip().lower().replace("_", " ").split())


def _is_symbol_header(value) -> bool:
    key = _norm(value)
    return key in {"security symbol", "symbol", "ticker", "ticker symbol"} or "symbol" in key


def _normalize_symbol(value) -> str | None:
    if pd.isna(value):
        return None
    symbol = str(value).strip().upper()
    if not symbol or symbol in {"NAN", "NONE"}:
        return None
    return symbol


def parse_nasdaq_workbook(content: bytes) -> pd.DataFrame:
    try:
        book = pd.ExcelFile(BytesIO(content))
    except Exception as exc:
        raise Mom30Error("无法打开 Nasdaq 权重工作簿") from exc

    diagnostics: list[str] = []
    for sheet in book.sheet_names:
        try:
            preview = pd.read_excel(book, sheet_name=sheet, header=None, nrows=30)
        except Exception as exc:
            diagnostics.append(f"{sheet}: preview {type(exc).__name__}")
            continue

        header_row = None
        for idx, row in preview.iterrows():
            if any(_is_symbol_header(v) for v in row.tolist()):
                header_row = int(idx)
                break

        if header_row is None:
            diagnostics.append(f"{sheet}: no symbol header")
            continue

        raw = pd.read_excel(book, sheet_name=sheet, header=header_row)
        symbol_col = next((c for c in raw.columns if _is_symbol_header(c)), None)
        if symbol_col is not None:
            return raw

    raise Mom30Error("Nasdaq 工作簿没有可识别的股票代码列；" + "; ".join(diagnostics))


def fetch_nasdaq_snapshot(trade_date, index: str = "NDX") -> pd.DataFrame:
    date = pd.Timestamp(trade_date).strftime("%Y-%m-%d")
    url = NASDAQ_EXPORT.format(index=index, trade_date=date)
    response = requests.get(
        url,
        timeout=60,
        headers={"User-Agent": "ndx-mom30-site/1.0 (+GitHub Actions research dashboard)"},
    )
    response.raise_for_status()
    raw = parse_nasdaq_workbook(response.content)
    symbol_col = next((c for c in raw.columns if _is_symbol_header(c)), None)
    if symbol_col is None:
        raise Mom30Error(f"Nasdaq 工作簿缺少股票代码列: {list(raw.columns)}")

    tickers = raw[symbol_col].map(_normalize_symbol).dropna().drop_duplicates().sort_values()
    if len(tickers) < 80 or len(tickers) > 130:
        raise Mom30Error(f"可疑的 Nasdaq {index} 成分数量: {len(tickers)} ({date})")

    return pd.DataFrame(
        {
            "ticker": tickers.to_list(),
            "snapshot_date": date,
            "source": url,
        }
    )


def latest_official_snapshot(on_or_before: pd.Timestamp) -> tuple[pd.Timestamp, pd.DataFrame]:
    target = pd.Timestamp(on_or_before).tz_localize(None).normalize()
    errors: list[str] = []
    for i in range(MAX_SNAPSHOT_LOOKBACK_DAYS + 1):
        day = target - pd.Timedelta(days=i)
        if day.weekday() >= 5:
            continue
        try:
            snapshot = fetch_nasdaq_snapshot(day)
        except Exception as exc:
            errors.append(f"{day.date()}: {type(exc).__name__}")
            continue
        if snapshot["ticker"].nunique() >= 80:
            return day, snapshot

    raise Mom30Error("无法取得近期官方 NDX 成分快照；" + "; ".join(errors[-6:]))


def ticker_set(snapshot: pd.DataFrame) -> set[str]:
    return set(snapshot["ticker"].astype(str).str.upper().str.strip())


def detect_period_start(latest_date: pd.Timestamp, latest_set: set[str]) -> pd.Timestamp:
    earliest_same = pd.Timestamp(latest_date).normalize()
    cursor = earliest_same - pd.Timedelta(days=1)
    checked_business_days = 0
    errors = 0

    while checked_business_days < MAX_PERIOD_LOOKBACK_BUSINESS_DAYS:
        if cursor.weekday() >= 5:
            cursor -= pd.Timedelta(days=1)
            continue

        try:
            snapshot = fetch_nasdaq_snapshot(cursor)
        except Exception:
            errors += 1
            cursor -= pd.Timedelta(days=1)
            if errors > 20:
                raise Mom30Error("寻找本轮起点时 Nasdaq 快照失败次数过多")
            continue

        checked_business_days += 1
        if ticker_set(snapshot) != latest_set:
            return earliest_same

        earliest_same = cursor
        cursor -= pd.Timedelta(days=1)

    raise Mom30Error(
        f"在 {MAX_PERIOD_LOOKBACK_BUSINESS_DAYS} 个交易日内未找到上一组成分集合"
    )


def yf_symbol(ticker: str) -> str:
    return str(ticker).upper().replace("/", "-").replace(".", "-")


def download_prices(
    tickers: list[str], baseline_date: pd.Timestamp, latest_snapshot_date: pd.Timestamp
) -> tuple[pd.DataFrame, pd.DataFrame]:
    import yfinance as yf

    symbol_map = {ticker: yf_symbol(ticker) for ticker in tickers}
    yahoo_symbols = sorted(set(symbol_map.values()))
    start = (baseline_date - pd.Timedelta(days=5)).strftime("%Y-%m-%d")
    end = (latest_snapshot_date + pd.Timedelta(days=2)).strftime("%Y-%m-%d")

    raw = yf.download(
        yahoo_symbols,
        start=start,
        end=end,
        auto_adjust=True,
        progress=False,
        group_by="column",
        threads=True,
    )
    if raw.empty:
        raise Mom30Error("yfinance 没有返回价格数据")

    if not isinstance(raw.columns, pd.MultiIndex):
        if len(yahoo_symbols) != 1:
            raise Mom30Error("yfinance 返回了异常的列结构")
        open_df = raw[["Open"]].rename(columns={"Open": yahoo_symbols[0]})
        close_df = raw[["Close"]].rename(columns={"Close": yahoo_symbols[0]})
    else:
        if "Open" not in raw.columns.get_level_values(0) or "Close" not in raw.columns.get_level_values(0):
            raise Mom30Error("yfinance 数据缺少 Open/Close")
        open_df = raw["Open"].copy()
        close_df = raw["Close"].copy()
        if isinstance(open_df, pd.Series):
            open_df = open_df.to_frame(name=yahoo_symbols[0])
        if isinstance(close_df, pd.Series):
            close_df = close_df.to_frame(name=yahoo_symbols[0])

    open_df.index = pd.to_datetime(open_df.index, errors="coerce").tz_localize(None)
    close_df.index = pd.to_datetime(close_df.index, errors="coerce").tz_localize(None)
    return open_df, close_df


def compute_ranking(
    tickers: list[str],
    baseline_date: pd.Timestamp,
    latest_snapshot_date: pd.Timestamp,
) -> pd.DataFrame:
    open_df, close_df = download_prices(tickers, baseline_date, latest_snapshot_date)
    symbol_map = {ticker: yf_symbol(ticker) for ticker in tickers}

    rows: list[dict] = []
    errors: list[str] = []

    for ticker in sorted(tickers):
        symbol = symbol_map[ticker]
        if symbol not in open_df.columns or symbol not in close_df.columns:
            errors.append(f"{ticker}: missing column")
            continue

        opens = pd.to_numeric(open_df[symbol], errors="coerce").dropna()
        closes = pd.to_numeric(close_df[symbol], errors="coerce").dropna()
        opens = opens[opens.index >= baseline_date]
        closes = closes[closes.index <= latest_snapshot_date]

        if opens.empty or closes.empty:
            errors.append(f"{ticker}: missing comparable price")
            continue

        baseline_observed = pd.Timestamp(opens.index[0]).normalize()
        if baseline_observed != baseline_date:
            errors.append(
                f"{ticker}: baseline mismatch wanted {baseline_date.date()} got {baseline_observed.date()}"
            )
            continue

        baseline_open = float(opens.iloc[0])
        last_close = float(closes.iloc[-1])
        last_date = pd.Timestamp(closes.index[-1]).normalize()

        if baseline_open <= 0 or last_close <= 0:
            errors.append(f"{ticker}: nonpositive price")
            continue

        ret = last_close / baseline_open - 1.0
        tv_symbol = f"NASDAQ:{ticker}"
        tv_url = f"https://www.tradingview.com/chart/?symbol={quote(tv_symbol, safe='')}&interval=240"

        rows.append(
            {
                "ticker": ticker,
                "baseline_date": baseline_date.strftime("%Y-%m-%d"),
                "baseline_open": round(baseline_open, 6),
                "last_date": last_date.strftime("%Y-%m-%d"),
                "last_close": round(last_close, 6),
                "return": ret,
                "return_pct": ret * 100.0,
                "tradingview_symbol": tv_symbol,
                "tradingview_4h_url": tv_url,
            }
        )

    ranking = pd.DataFrame(rows)
    if ranking.empty:
        raise Mom30Error("没有股票获得有效的可比价格")

    ranking = ranking.sort_values(["return", "ticker"], ascending=[False, True]).reset_index(drop=True)
    ranking.insert(0, "rank", range(1, len(ranking) + 1))

    if len(ranking) < TOP_N:
        raise Mom30Error(
            f"只有 {len(ranking)} 只股票具有有效可比价格，少于 Top{TOP_N}；"
            f"示例错误: {errors[:8]}"
        )

    return ranking


def load_state() -> dict | None:
    if not STATE_PATH.exists():
        return None
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_history(summary: dict) -> None:
    columns = [
        "as_of",
        "snapshot_date",
        "baseline_date",
        "leader",
        "leader_return_pct",
        "valid_count",
        "constituent_count",
    ]
    row = pd.DataFrame([{key: summary[key] for key in columns}])

    if HISTORY_PATH.exists() and HISTORY_PATH.stat().st_size > 0:
        history = pd.read_csv(HISTORY_PATH)
        history = history[history["as_of"].astype(str) != str(summary["as_of"])]
        history = pd.concat([history, row], ignore_index=True)
    else:
        history = row

    history = history.sort_values("as_of").reset_index(drop=True)
    history.to_csv(HISTORY_PATH, index=False)


def write_outputs(
    ranking: pd.DataFrame,
    snapshot: pd.DataFrame,
    baseline_date: pd.Timestamp,
    snapshot_date: pd.Timestamp,
) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    top30 = ranking.head(TOP_N).copy()
    top30.to_csv(TOP30_CSV_PATH, index=False)
    ranking.to_csv(ALL_CSV_PATH, index=False)

    latest_price_date = str(ranking["last_date"].max())
    leader = top30.iloc[0]

    payload = {
        "status": "ready",
        "as_of": latest_price_date,
        "research_version": VERSION,
        "ndx": {
            "display_value": f"{len(snapshot)}只",
            "note": f"Nasdaq 官方 NDX 成分快照：{snapshot_date.strftime('%Y-%m-%d')}",
            "constituent_count": int(len(snapshot)),
            "snapshot_date": snapshot_date.strftime("%Y-%m-%d"),
            "baseline_date": baseline_date.strftime("%Y-%m-%d"),
        },
        "mom30": {
            "display_value": f"Top {TOP_N}",
            "note": f"本轮统一从 {baseline_date.strftime('%Y-%m-%d')} 开盘归零",
            "top_n": TOP_N,
            "leader": str(leader["ticker"]),
            "leader_return_pct": round(float(leader["return_pct"]), 4),
            "latest_price_date": latest_price_date,
        },
        "top30": [
            {
                "rank": int(row["rank"]),
                "ticker": str(row["ticker"]),
                "return_pct": round(float(row["return_pct"]), 4),
                "last_close": round(float(row["last_close"]), 4),
                "last_date": str(row["last_date"]),
                "tradingview_4h_url": str(row["tradingview_4h_url"]),
            }
            for _, row in top30.iterrows()
        ],
        "method": {
            "universe": "Nasdaq-100 official constituent snapshot",
            "reset_rule": "official constituent-set change",
            "baseline": "first trading day of current constituent set, open price",
            "ranking": "latest close / common baseline open - 1",
            "selection": "descending return, top 30",
            "price_source": "yfinance auto_adjust=True",
        },
    }
    LATEST_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    state = {
        "version": VERSION,
        "baseline_date": baseline_date.strftime("%Y-%m-%d"),
        "latest_snapshot_date": snapshot_date.strftime("%Y-%m-%d"),
        "constituents": sorted(ticker_set(snapshot)),
        "top_n": TOP_N,
    }
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    save_history(
        {
            "as_of": latest_price_date,
            "snapshot_date": snapshot_date.strftime("%Y-%m-%d"),
            "baseline_date": baseline_date.strftime("%Y-%m-%d"),
            "leader": str(leader["ticker"]),
            "leader_return_pct": round(float(leader["return_pct"]), 4),
            "valid_count": int(len(ranking)),
            "constituent_count": int(len(snapshot)),
        }
    )


def main() -> int:
    requested = ny_today()
    snapshot_date, snapshot = latest_official_snapshot(requested)
    current_set = ticker_set(snapshot)

    state = load_state()
    prior_set = set(state.get("constituents", [])) if state else set()

    if state and prior_set == current_set and state.get("baseline_date"):
        baseline_date = pd.Timestamp(state["baseline_date"]).normalize()
        reason = "成分集合未变化，沿用本轮统一起点"
    else:
        baseline_date = detect_period_start(snapshot_date, current_set)
        reason = "首次初始化" if not state else "官方成分集合变化，重新归零"

    ranking = compute_ranking(sorted(current_set), baseline_date, snapshot_date)
    write_outputs(ranking, snapshot, baseline_date, snapshot_date)

    print(
        f"{VERSION}: snapshot={snapshot_date.date()} baseline={baseline_date.date()} "
        f"reason={reason} valid={len(ranking)}/{len(current_set)}"
    )
    print(ranking.head(TOP_N)[["rank", "ticker", "return_pct", "last_date"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
