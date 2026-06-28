"""
Stock Analysis Tool - a personal Flet app for tracking and screening
Indian (NSE) and US stocks, instead of relying on news-article "tips".

Run locally:
    pip install -r requirements.txt
    flet run main.py            # native desktop window
    flet run --web main.py      # same app in a browser tab

Data source: Yahoo Finance via the `yfinance` library.
  - US stocks: plain ticker, e.g. AAPL, MSFT
  - NSE (India): ticker + ".NS", e.g. RELIANCE.NS, TCS.NS
  - BSE (India): ticker + ".BO", e.g. RELIANCE.BO

This is a personal research tool only - it is not investment advice.
"""

from __future__ import annotations
import flet as ft

import storage
import universe
from data_provider import fetch_quotes, Quote
from analysis import compute_technical_snapshot, screen_quote, TechnicalSnapshot
from formatting import fmt_num, fmt_pct, fmt_compact, currency_symbol
from charting import render_price_chart
from macro import fetch_macro_snapshot

def _border_all(width, color):
    side = ft.border.BorderSide(width=width, color=color)
    return ft.border.Border(top=side, right=side, bottom=side, left=side)


def _padding_symmetric(horizontal=0, vertical=0):
    return ft.padding.Padding(left=horizontal, right=horizontal, top=vertical, bottom=vertical)


CATEGORY_COLORS = {
    "Value Candidate": ft.Colors.GREEN_700,
    "Momentum / Overbought": ft.Colors.ORANGE_700,
    "Watch (Golden Cross)": ft.Colors.BLUE_700,
    "Watch (Death Cross)": ft.Colors.RED_700,
    "Neutral": ft.Colors.GREY_600,
}


def main(page: ft.Page):
    page.title = "Stock Analysis Tool"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 16
    page.window.width = 1200
    page.window.height = 820
    page.window.min_width = 760
    page.window.min_height = 560
    page.scroll = ft.ScrollMode.AUTO

    state = {
        "watchlist": storage.load_watchlist(),
        "quotes_cache": {},   # ticker -> Quote
        "screen_results": [],  # list[ScreenResult]
        "macro_results": [],   # list[MacroSnapshot]
        "macro_loaded": False,
        "view": "watchlist",
    }

    status_text = ft.Text("", size=12, color=ft.Colors.GREY_700)
    progress = ft.ProgressRing(width=16, height=16, visible=False)

    screener_status = ft.Text("", size=12, color=ft.Colors.GREY_700)
    screener_progress = ft.ProgressRing(width=16, height=16, visible=False)

    macro_status = ft.Text("", size=12, color=ft.Colors.GREY_700)
    macro_progress = ft.ProgressRing(width=16, height=16, visible=False)

    body = ft.Container(expand=True)

    # ------------------------------------------------------------------
    # Detail dialog (shared by Watchlist + Screener)
    # ------------------------------------------------------------------
    def show_detail(q: Quote, snap: TechnicalSnapshot):
        sym = currency_symbol(q.currency)
        chart_b64 = render_price_chart(q.history, q.ticker, sym)

        stats_rows = [
            ("Price", f"{sym}{fmt_num(q.price)}"),
            ("Day change", fmt_pct(q.day_change_pct, already_fraction=False)),
            ("Market cap", fmt_compact(q.market_cap)),
            ("P/E (TTM)", fmt_num(q.pe_ratio)),
            ("EPS (TTM)", fmt_num(q.eps)),
            ("Dividend yield", fmt_pct(q.dividend_yield)),
            ("Beta", fmt_num(q.beta)),
            ("Debt/Equity", fmt_num(q.debt_to_equity)),
            ("Profit margin", fmt_pct(q.profit_margin)),
            ("Revenue growth (YoY)", fmt_pct(q.revenue_growth)),
            ("52-week range", f"{sym}{fmt_num(q.week52_low)}  -  {sym}{fmt_num(q.week52_high)}"),
            ("SMA20 / 50 / 200",
             f"{fmt_num(snap.sma20)} / {fmt_num(snap.sma50)} / {fmt_num(snap.sma200)}"),
            ("RSI (14)", fmt_num(snap.rsi14, 1)),
            ("Trend", snap.trend),
            ("Volume / Avg Volume", f"{fmt_compact(q.volume)} / {fmt_compact(q.avg_volume)}"),
            ("Signals", ", ".join(snap.flags) if snap.flags else "None"),
        ]
        stats_col = ft.Column(
            [ft.Row([ft.Text(k, width=170, color=ft.Colors.GREY_700, size=12),
                      ft.Text(v, size=12)])
             for k, v in stats_rows],
            spacing=4, tight=True,
        )

        right_controls = []
        if chart_b64:
            right_controls.append(ft.Image(src=chart_b64, width=420, height=320,
                                            fit=ft.BoxFit.CONTAIN))
        else:
            right_controls.append(ft.Text("No chart data available.", size=12,
                                           color=ft.Colors.GREY_600))

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"{q.name or q.ticker}  ({q.ticker})"),
            content=ft.Row(
                [stats_col, ft.VerticalDivider(), ft.Column(right_controls)],
                vertical_alignment=ft.CrossAxisAlignment.START,
                spacing=16,
            ),
            actions=[ft.TextButton("Close", on_click=lambda e: page.pop_dialog())],
        )
        page.show_dialog(dialog)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------
    def nav_style(active: bool) -> ft.ButtonStyle:
        return ft.ButtonStyle(
            bgcolor=ft.Colors.BLUE_700 if active else ft.Colors.GREY_200,
            color=ft.Colors.WHITE if active else ft.Colors.BLACK,
        )

    nav_watchlist_btn = ft.Button("Watchlist", style=nav_style(True))
    nav_screener_btn = ft.Button("Screener", style=nav_style(False))
    nav_macro_btn = ft.Button("Macro", style=nav_style(False))

    def set_view(view_name):
        state["view"] = view_name
        nav_watchlist_btn.style = nav_style(view_name == "watchlist")
        nav_screener_btn.style = nav_style(view_name == "screener")
        nav_macro_btn.style = nav_style(view_name == "macro")
        refresh_body()
        page.update()
        if view_name == "macro" and not state["macro_loaded"]:
            refresh_macro_data()

    nav_watchlist_btn.on_click = lambda e: set_view("watchlist")
    nav_screener_btn.on_click = lambda e: set_view("screener")
    nav_macro_btn.on_click = lambda e: set_view("macro")

    # ------------------------------------------------------------------
    # Watchlist view
    # ------------------------------------------------------------------
    add_ticker_field = ft.TextField(label="Add ticker (e.g. AAPL or TCS.NS)", width=260)

    def add_ticker(e=None):
        val = (add_ticker_field.value or "").strip().upper()
        if not val:
            return
        if val not in state["watchlist"]:
            state["watchlist"].append(val)
            storage.save_watchlist(state["watchlist"])
        add_ticker_field.value = ""
        refresh_body()
        page.update()
        refresh_watchlist_data([val])

    def remove_ticker(ticker):
        if ticker in state["watchlist"]:
            state["watchlist"].remove(ticker)
            storage.save_watchlist(state["watchlist"])
        state["quotes_cache"].pop(ticker, None)
        refresh_body()
        page.update()

    add_ticker_field.on_submit = add_ticker

    def refresh_watchlist_data(tickers=None):
        targets = tickers or list(state["watchlist"])
        if not targets:
            return
        progress.visible = True
        status_text.value = f"Fetching {len(targets)} ticker(s)..."
        page.update()

        def worker():
            results = fetch_quotes(targets)
            for q in results:
                state["quotes_cache"][q.ticker] = q
            failed = [q.ticker for q in results if q.error]
            progress.visible = False
            msg = f"Updated {len(results) - len(failed)}/{len(results)} ticker(s)."
            if failed:
                msg += f" Failed: {', '.join(failed)}"
            status_text.value = msg
            refresh_body()
            page.update()

        page.run_thread(worker)

    def watchlist_rows():
        rows = []
        for tkr in state["watchlist"]:
            q = state["quotes_cache"].get(tkr)
            if q is None:
                rows.append(ft.DataRow(cells=[ft.DataCell(ft.Text(tkr))] +
                                        [ft.DataCell(ft.Text("loading...")) for _ in range(8)] +
                                        [ft.DataCell(ft.IconButton(icon=ft.Icons.DELETE_OUTLINE,
                                                                    icon_size=16,
                                                                    on_click=lambda e, t=tkr: remove_ticker(t)))]))
                continue
            if q.error:
                rows.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Text(q.ticker)),
                    ft.DataCell(ft.Text(f"Error: {q.error}", color=ft.Colors.RED_700)),
                ] + [ft.DataCell(ft.Text("-")) for _ in range(7)] +
                    [ft.DataCell(ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_size=16,
                                                on_click=lambda e, t=tkr: remove_ticker(t)))]))
                continue
            snap = compute_technical_snapshot(q)
            change_color = ft.Colors.GREEN_700 if (q.day_change_pct or 0) >= 0 else ft.Colors.RED_700
            sym = currency_symbol(q.currency)
            rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(q.ticker)),
                        ft.DataCell(ft.Text(q.name or "", overflow=ft.TextOverflow.ELLIPSIS)),
                        ft.DataCell(ft.Text(f"{sym}{fmt_num(q.price)}")),
                        ft.DataCell(ft.Text(fmt_pct(q.day_change_pct, already_fraction=False),
                                             color=change_color)),
                        ft.DataCell(ft.Text(fmt_num(q.pe_ratio))),
                        ft.DataCell(ft.Text(fmt_pct(q.dividend_yield))),
                        ft.DataCell(ft.Text(fmt_num(snap.rsi14, 1))),
                        ft.DataCell(ft.Text(snap.trend)),
                        ft.DataCell(ft.Text(", ".join(snap.flags) if snap.flags else "-")),
                        ft.DataCell(ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_size=16,
                                                   tooltip="Remove",
                                                   on_click=lambda e, t=tkr: remove_ticker(t))),
                    ],
                    on_select_change=lambda e, qq=q, ss=snap: show_detail(qq, ss),
                )
            )
        return rows

    def build_watchlist_view():
        table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Ticker")),
                ft.DataColumn(ft.Text("Name")),
                ft.DataColumn(ft.Text("Price")),
                ft.DataColumn(ft.Text("Day %")),
                ft.DataColumn(ft.Text("P/E")),
                ft.DataColumn(ft.Text("Div Yield")),
                ft.DataColumn(ft.Text("RSI14")),
                ft.DataColumn(ft.Text("Trend")),
                ft.DataColumn(ft.Text("Signals")),
                ft.DataColumn(ft.Text("")),
            ],
            rows=watchlist_rows(),
            column_spacing=18,
        )
        return ft.Column(
            [
                ft.Row(
                    [
                        add_ticker_field,
                        ft.Button("Add", icon=ft.Icons.ADD, on_click=add_ticker),
                        ft.Button("Refresh All", icon=ft.Icons.REFRESH,
                                          on_click=lambda e: refresh_watchlist_data()),
                        progress,
                        status_text,
                    ],
                    wrap=True,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Divider(),
                ft.Row([table], scroll=ft.ScrollMode.AUTO),
            ],
            expand=True,
        )

    # ------------------------------------------------------------------
    # Screener view
    # ------------------------------------------------------------------
    universe_names = list(universe.UNIVERSE_CHOICES.keys())
    universe_dropdown = ft.Dropdown(
        label="Universe",
        value=universe_names[0],
        options=[ft.DropdownOption(key=n, text=n) for n in universe_names],
        width=220,
    )
    pe_max_field = ft.TextField(label="Max P/E", value="25", width=100)
    rsi_low_field = ft.TextField(label="RSI oversold <", value="35", width=130)
    rsi_high_field = ft.TextField(label="RSI overbought >", value="70", width=140)

    def run_scan(e=None):
        universe_name = universe_dropdown.value
        getter = universe.UNIVERSE_CHOICES.get(universe_name)
        if not getter:
            return
        screener_progress.visible = True
        screener_status.value = "Loading universe list..."
        page.update()

        def worker():
            try:
                tickers = getter()
            except Exception as exc:  # noqa: BLE001
                screener_status.value = f"Failed to load universe: {exc}"
                screener_progress.visible = False
                page.update()
                return

            def progress_cb(done, total):
                screener_status.value = f"Scanning {done}/{total} stocks..."
                page.update()

            quotes = fetch_quotes(tickers, progress_cb=progress_cb)

            def to_float(field, default):
                try:
                    return float(field.value)
                except (TypeError, ValueError):
                    return default

            pe_max = to_float(pe_max_field, 25.0)
            rsi_low = to_float(rsi_low_field, 35.0)
            rsi_high = to_float(rsi_high_field, 70.0)

            results = []
            for q in quotes:
                state["quotes_cache"][q.ticker] = q
                if q.error or q.history is None or q.history.empty:
                    continue
                snap = compute_technical_snapshot(q)
                res = screen_quote(q, snap, pe_max=pe_max, rsi_oversold=rsi_low,
                                    rsi_overbought=rsi_high)
                results.append(res)

            order = {"Value Candidate": 0, "Momentum / Overbought": 1,
                     "Watch (Golden Cross)": 2, "Watch (Death Cross)": 3, "Neutral": 4}
            results.sort(key=lambda r: order.get(r.category, 9))
            state["screen_results"] = results

            flagged = sum(1 for r in results if r.category != "Neutral")
            screener_status.value = (
                f"Scanned {len(results)} stocks ({len(tickers) - len(results)} skipped/errored). "
                f"{flagged} flagged."
            )
            screener_progress.visible = False
            refresh_body()
            page.update()

        page.run_thread(worker)

    def screener_rows():
        rows = []
        for r in state["screen_results"]:
            q, snap = r.quote, r.snapshot
            sym = currency_symbol(q.currency)
            range_pos = (fmt_pct(snap.range_position, 0, already_fraction=True)
                         if snap.range_position is not None else "-")
            rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(q.ticker)),
                        ft.DataCell(ft.Text(q.name or "", overflow=ft.TextOverflow.ELLIPSIS)),
                        ft.DataCell(ft.Text(f"{sym}{fmt_num(q.price)}")),
                        ft.DataCell(ft.Text(fmt_num(q.pe_ratio))),
                        ft.DataCell(ft.Text(fmt_num(snap.rsi14, 1))),
                        ft.DataCell(ft.Text(range_pos)),
                        ft.DataCell(ft.Text(snap.trend)),
                        ft.DataCell(ft.Text(r.category,
                                             color=CATEGORY_COLORS.get(r.category))),
                    ],
                    on_select_change=lambda e, qq=q, ss=snap: show_detail(qq, ss),
                )
            )
        return rows

    def build_screener_view():
        table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Ticker")),
                ft.DataColumn(ft.Text("Name")),
                ft.DataColumn(ft.Text("Price")),
                ft.DataColumn(ft.Text("P/E")),
                ft.DataColumn(ft.Text("RSI14")),
                ft.DataColumn(ft.Text("52wk pos")),
                ft.DataColumn(ft.Text("Trend")),
                ft.DataColumn(ft.Text("Category")),
            ],
            rows=screener_rows(),
            column_spacing=18,
        )
        return ft.Column(
            [
                ft.Row(
                    [universe_dropdown, pe_max_field, rsi_low_field, rsi_high_field,
                     ft.Button("Run Scan", icon=ft.Icons.SEARCH, on_click=run_scan),
                     screener_progress, screener_status],
                    wrap=True,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Text(
                    "Rules are transparent, not a magic score: 'Value Candidate' = RSI "
                    "oversold + near 52-week low + P/E under your max. 'Momentum / "
                    "Overbought' = RSI overbought + near 52-week high. Golden/Death Cross "
                    "= SMA50 crossing SMA200. This is a research starting point, not advice.",
                    size=11, color=ft.Colors.GREY_600,
                ),
                ft.Divider(),
                ft.Row([table], scroll=ft.ScrollMode.AUTO),
            ],
            expand=True,
        )

    # ------------------------------------------------------------------
    # Macro view
    # ------------------------------------------------------------------
    TREND_COLORS = {
        "Rising": ft.Colors.ORANGE_700,
        "Falling": ft.Colors.BLUE_700,
        "Flat": ft.Colors.GREY_600,
        "n/a": ft.Colors.GREY_400,
    }

    def refresh_macro_data(e=None):
        macro_progress.visible = True
        macro_status.value = "Fetching macro indicators..."
        page.update()

        def worker():
            try:
                results = fetch_macro_snapshot()
                state["macro_results"] = results
                state["macro_loaded"] = True
                failed = [r.label for r in results if r.error]
                msg = f"Updated {len(results) - len(failed)}/{len(results)} indicator(s)."
                if failed:
                    msg += f" Failed: {', '.join(failed)}"
                macro_status.value = msg
            except Exception as exc:  # noqa: BLE001
                macro_status.value = f"Failed to fetch macro data: {exc}"
            macro_progress.visible = False
            refresh_body()
            page.update()

        page.run_thread(worker)

    def macro_cards():
        cards = []
        for r in state["macro_results"]:
            if r.error:
                cards.append(
                    ft.Container(
                        content=ft.Row([
                            ft.Text(r.label, weight=ft.FontWeight.BOLD, width=220),
                            ft.Text(f"Unavailable ({r.error})", color=ft.Colors.RED_700, size=12),
                        ]),
                        padding=10, border=_border_all(1, ft.Colors.GREY_300), border_radius=6,
                    )
                )
                continue

            trend_color = TREND_COLORS.get(r.trend, ft.Colors.GREY_600)
            header = ft.Row(
                [
                    ft.Text(r.label, weight=ft.FontWeight.BOLD, width=220),
                    ft.Text(fmt_num(r.price, 2), width=90),
                    ft.Text(fmt_pct(r.day_change_pct, already_fraction=False), width=90,
                            color=ft.Colors.GREEN_700 if (r.day_change_pct or 0) >= 0
                            else ft.Colors.RED_700),
                    ft.Container(
                        content=ft.Text(r.trend, size=11, color=ft.Colors.WHITE),
                        bgcolor=trend_color, padding=_padding_symmetric(8, 3),
                        border_radius=12,
                    ),
                    ft.Text(
                        f"({fmt_pct(r.pct_vs_sma50, 1, already_fraction=False)} vs 50d avg)"
                        if r.pct_vs_sma50 is not None else "",
                        size=11, color=ft.Colors.GREY_600,
                    ),
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
            children = [header]
            if r.note:
                children.append(ft.Text(r.note, size=11, color=ft.Colors.GREY_700, italic=True))
            cards.append(
                ft.Container(
                    content=ft.Column(children, spacing=4, tight=True),
                    padding=10, border=_border_all(1, ft.Colors.GREY_300), border_radius=6,
                )
            )
        return cards

    def build_macro_view():
        cards = macro_cards()
        return ft.Column(
            [
                ft.Row(
                    [
                        ft.Button("Refresh", icon=ft.Icons.REFRESH, on_click=refresh_macro_data),
                        macro_progress,
                        macro_status,
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Text(
                    "A few headline rates/volatility/currency/commodity indicators, fetched the "
                    "same way as the stocks above - no separate API, no news. Rising/Falling is "
                    "just price vs. its own 50-day average. The notes below are generic, "
                    "textbook-style relationships (not predictions, not sentiment) - useful "
                    "context, not a signal to act on by itself.",
                    size=11, color=ft.Colors.GREY_600,
                ),
                ft.Divider(),
                ft.Column(cards, spacing=8, scroll=ft.ScrollMode.AUTO, expand=True)
                if cards else ft.Text("No data yet - click Refresh.", size=12, color=ft.Colors.GREY_600),
            ],
            expand=True,
        )

    # ------------------------------------------------------------------
    # Wiring
    # ------------------------------------------------------------------
    def refresh_body():
        if state["view"] == "watchlist":
            body.content = build_watchlist_view()
        elif state["view"] == "screener":
            body.content = build_screener_view()
        else:
            body.content = build_macro_view()

    page.add(
        ft.Row([nav_watchlist_btn, nav_screener_btn, nav_macro_btn], spacing=10),
        ft.Divider(),
        body,
    )
    refresh_body()
    page.update()
    refresh_watchlist_data()


if __name__ == "__main__":
    try:
        ft.run(main)
    except AttributeError:
        ft.app(target=main)
