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
import uuid
from datetime import datetime

import flet as ft

import storage
import universe
from data_provider import fetch_quotes, Quote
from analysis import compute_technical_snapshot, screen_quote, TechnicalSnapshot
from formatting import fmt_num, fmt_pct, fmt_compact, currency_symbol
from charting import render_price_chart
from macro import fetch_macro_snapshot
import llm_summary

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
        "watchlist_filter": "All",
        # General chat: a list of saved sessions (persisted to disk) plus
        # which one is currently open. Each session:
        # {"id", "title", "created_at", "messages": [{"role", "content"}]}
        "chat_sessions": storage.load_chat_sessions(),
        "current_chat_id": None,
        "chat_panel_collapsed": False,
    }

    def _new_chat_session() -> dict:
        return {
            "id": uuid.uuid4().hex,
            "title": "New chat",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "messages": [],
        }

    def _bump_to_top(chat_id: str) -> None:
        """Keeps the active/just-updated session pinned at the top of the
        history list, so it doesn't sink down as it accumulates replies."""
        sessions = state["chat_sessions"]
        for i, s in enumerate(sessions):
            if s["id"] == chat_id:
                if i != 0:
                    sessions.insert(0, sessions.pop(i))
                break

    def get_current_chat() -> dict:
        """Returns the active chat session, creating one if none exists yet."""
        cid = state["current_chat_id"]
        for s in state["chat_sessions"]:
            if s["id"] == cid:
                return s
        # No active session (first run, or it was deleted) - start a fresh one.
        session = _new_chat_session()
        state["chat_sessions"].insert(0, session)
        state["current_chat_id"] = session["id"]
        return session

    def start_new_chat(e=None):
        session = _new_chat_session()
        state["chat_sessions"].insert(0, session)
        state["current_chat_id"] = session["id"]
        storage.save_chat_sessions(state["chat_sessions"])
        refresh_body()
        page.update()

    def toggle_chat_panel(e=None):
        state["chat_panel_collapsed"] = not state["chat_panel_collapsed"]
        refresh_body()
        page.update()

    def select_chat(chat_id: str):
        state["current_chat_id"] = chat_id
        refresh_body()
        page.update()

    def delete_chat(chat_id: str, e=None):
        state["chat_sessions"] = [s for s in state["chat_sessions"] if s["id"] != chat_id]
        if state["current_chat_id"] == chat_id:
            state["current_chat_id"] = None
        storage.save_chat_sessions(state["chat_sessions"])
        refresh_body()
        page.update()

    status_text = ft.Text("", size=12, color=ft.Colors.GREY_700)
    progress = ft.ProgressRing(width=16, height=16, visible=False)

    screener_status = ft.Text("", size=12, color=ft.Colors.GREY_700)
    screener_progress = ft.ProgressRing(width=16, height=16, visible=False)

    macro_status = ft.Text("", size=12, color=ft.Colors.GREY_700)
    macro_progress = ft.ProgressRing(width=16, height=16, visible=False)

    chat_input_field = ft.TextField(hint_text="Ask about market concepts, indicators, strategy...",
                                     expand=True, dense=True)
    chat_send_btn = ft.Button("Send", icon=ft.Icons.SEND)
    chat_progress = ft.ProgressRing(width=16, height=16, visible=False)

    body = ft.Container(expand=True)

    # ------------------------------------------------------------------
    # Detail dialog (shared by Watchlist + Screener)
    # ------------------------------------------------------------------
    def show_detail(q: Quote, snap: TechnicalSnapshot, category: str | None = None):
        sym = currency_symbol(q.currency)
        chart_b64 = render_price_chart(q.history, q.ticker, sym)
        category = category or screen_quote(q, snap).category

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

        # -- "Explain this" chat (local LLM, optional feature) -----------
        chat_history: list[dict] = []  # [{"role": "user"/"assistant", "content": ...}]
        chat_transcript = ft.Column(spacing=6, tight=True)
        chat_progress = ft.ProgressRing(width=14, height=14, visible=False)
        chat_disclaimer = ft.Text(llm_summary.DISCLAIMER, size=10,
                                   color=ft.Colors.GREY_600, visible=False)
        chat_input = ft.TextField(hint_text="Ask a follow-up question about this stock...",
                                   expand=True, dense=True)
        send_button = ft.IconButton(icon=ft.Icons.SEND)
        explain_button = ft.TextButton("Explain this", icon=ft.Icons.AUTO_AWESOME,
                                        visible=False)
        chat_row = ft.Row([chat_input, send_button, chat_progress], visible=False)

        def send_chat(e=None, preset_question: str | None = None):
            question = preset_question or chat_input.value.strip()
            if not question:
                return
            chat_input.value = ""
            chat_history.append({"role": "user", "content": question})
            chat_transcript.controls.append(
                ft.Text(f"You: {question}", size=12, weight=ft.FontWeight.BOLD))
            chat_input.disabled = True
            send_button.disabled = True
            explain_button.disabled = True
            chat_progress.visible = True
            page.update()

            def worker():
                reply = llm_summary.chat_reply(list(chat_history), q, snap, category)
                chat_progress.visible = False
                chat_input.disabled = False
                send_button.disabled = False
                explain_button.disabled = False
                if reply:
                    chat_history.append({"role": "assistant", "content": reply})
                    chat_transcript.controls.append(ft.Text(reply, size=12, selectable=True))
                    chat_disclaimer.visible = True
                else:
                    chat_transcript.controls.append(
                        ft.Text("Local model unavailable right now.", size=12,
                                italic=True, color=ft.Colors.RED_400))
                page.update()

            page.run_thread(worker)

        def start_chat(e=None):
            explain_button.visible = False
            chat_row.visible = True
            send_chat(preset_question="Explain this stock in plain language based on the data above.")

        explain_button.on_click = start_chat
        send_button.on_click = send_chat
        chat_input.on_submit = send_chat
        if llm_summary.is_ollama_available():
            explain_button.visible = True

        explain_col = ft.Column(
            [ft.Row([explain_button]), chat_transcript, chat_row, chat_disclaimer],
            spacing=6, tight=True,
        )

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"{q.name or q.ticker}  ({q.ticker})"),
            content=ft.Container(
                width=760,
                height=480,
                content=ft.Column(
                    [
                        ft.Row(
                            [stats_col, ft.VerticalDivider(), ft.Column(right_controls)],
                            vertical_alignment=ft.CrossAxisAlignment.START,
                            spacing=16,
                        ),
                        ft.Divider(),
                        explain_col,
                    ],
                    scroll=ft.ScrollMode.AUTO,
                    tight=True,
                ),
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
    nav_chat_btn = ft.Button("Chat", style=nav_style(False))
    nav_setup_btn = ft.Button("LLM Setup", style=nav_style(False))

    def set_view(view_name):
        state["view"] = view_name
        nav_watchlist_btn.style = nav_style(view_name == "watchlist")
        nav_screener_btn.style = nav_style(view_name == "screener")
        nav_macro_btn.style = nav_style(view_name == "macro")
        nav_chat_btn.style = nav_style(view_name == "chat")
        nav_setup_btn.style = nav_style(view_name == "setup")
        refresh_body()
        page.update()
        if view_name == "macro" and not state["macro_loaded"]:
            refresh_macro_data()

    nav_watchlist_btn.on_click = lambda e: set_view("watchlist")
    nav_screener_btn.on_click = lambda e: set_view("screener")
    nav_macro_btn.on_click = lambda e: set_view("macro")
    nav_chat_btn.on_click = lambda e: set_view("chat")
    nav_setup_btn.on_click = lambda e: set_view("setup")

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

    def _ticker_market(ticker: str) -> str:
        return "India" if ticker.upper().endswith((".NS", ".BO")) else "US"

    def _visible_watchlist() -> list[str]:
        market = state["watchlist_filter"]
        if market == "All":
            return list(state["watchlist"])
        return [t for t in state["watchlist"] if _ticker_market(t) == market]

    def set_watchlist_filter(market: str) -> None:
        state["watchlist_filter"] = market
        refresh_body()
        page.update()

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
        for tkr in _visible_watchlist():
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

    def market_filter_style(active: bool):
        return ft.ButtonStyle(
            bgcolor=ft.Colors.BLUE_700 if active else ft.Colors.GREY_100,
            color=ft.Colors.WHITE if active else ft.Colors.BLACK,
        )

    def build_market_filter_row():
        current = state["watchlist_filter"]
        counts = {
            "All": len(state["watchlist"]),
            "US": sum(1 for t in state["watchlist"] if _ticker_market(t) == "US"),
            "India": sum(1 for t in state["watchlist"] if _ticker_market(t) == "India"),
        }
        return ft.Row(
            [
                ft.Button(f"All ({counts['All']})", style=market_filter_style(current == "All"),
                          on_click=lambda e: set_watchlist_filter("All")),
                ft.Button(f"US ({counts['US']})", style=market_filter_style(current == "US"),
                          on_click=lambda e: set_watchlist_filter("US")),
                ft.Button(f"India ({counts['India']})", style=market_filter_style(current == "India"),
                          on_click=lambda e: set_watchlist_filter("India")),
            ],
            spacing=8,
        )

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
                build_market_filter_row(),
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
                    on_select_change=lambda e, qq=q, ss=snap, cat=r.category: show_detail(qq, ss, cat),
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
    # Chat view (general market/investing discussion, local LLM)
    # ------------------------------------------------------------------
    def send_general_chat(e=None):
        question = (chat_input_field.value or "").strip()
        if not question:
            return
        session = get_current_chat()
        chat_input_field.value = ""
        session["messages"].append({"role": "user", "content": question})
        if session["title"] == "New chat":
            session["title"] = question[:48] + ("…" if len(question) > 48 else "")
        _bump_to_top(session["id"])
        storage.save_chat_sessions(state["chat_sessions"])
        chat_progress.visible = True
        chat_input_field.disabled = True
        chat_send_btn.disabled = True
        refresh_body()
        page.update()

        def worker():
            reply = llm_summary.general_chat_reply(list(session["messages"]))
            session["messages"].append({
                "role": "assistant",
                "content": reply or "Local model unavailable right now.",
            })
            _bump_to_top(session["id"])
            storage.save_chat_sessions(state["chat_sessions"])
            chat_progress.visible = False
            chat_input_field.disabled = False
            chat_send_btn.disabled = False
            refresh_body()
            page.update()

        page.run_thread(worker)

    chat_input_field.on_submit = send_general_chat
    chat_send_btn.on_click = send_general_chat

    def build_chat_history_panel():
        # Collapsed: a thin strip on the left with just an expand handle
        # and a "new chat" shortcut, so the transcript gets full width.
        if state["chat_panel_collapsed"]:
            return ft.Column(
                [
                    ft.IconButton(
                        icon=ft.Icons.CHEVRON_RIGHT, tooltip="Show chat history",
                        on_click=toggle_chat_panel,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.ADD_COMMENT_OUTLINED, tooltip="New chat",
                        on_click=start_new_chat,
                    ),
                ],
                width=44,
                spacing=4,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            )

        items = []
        for s in state["chat_sessions"]:
            is_active = s["id"] == state["current_chat_id"]
            items.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Text(
                                s["title"], size=12, no_wrap=True,
                                overflow=ft.TextOverflow.ELLIPSIS,
                                weight=ft.FontWeight.BOLD if is_active else ft.FontWeight.NORMAL,
                                expand=True,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.DELETE_OUTLINE, icon_size=14,
                                tooltip="Delete chat",
                                on_click=lambda e, cid=s["id"]: delete_chat(cid),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    padding=_padding_symmetric(horizontal=8, vertical=6),
                    border_radius=6,
                    bgcolor=ft.Colors.BLUE_50 if is_active else None,
                    on_click=lambda e, cid=s["id"]: select_chat(cid),
                    ink=True,
                )
            )
        return ft.Column(
            [
                ft.Row(
                    [
                        ft.Button("+ New chat", on_click=start_new_chat, expand=True),
                        ft.IconButton(
                            icon=ft.Icons.CHEVRON_LEFT, tooltip="Hide chat history",
                            on_click=toggle_chat_panel,
                        ),
                    ],
                ),
                ft.Divider(),
                ft.Column(items, spacing=2, scroll=ft.ScrollMode.AUTO, expand=True)
                if items else ft.Text("No past chats yet.", size=11, color=ft.Colors.GREY_600),
            ],
            width=220,
            spacing=8,
        )

    def build_ollama_status_panel(available: bool):
        models = llm_summary.list_installed_models() if available else []
        model_names = ", ".join(m["name"] for m in models) if models else "none installed"

        def refresh_status(e=None):
            refresh_body()
            page.update()

        status_row = ft.Row(
            [
                ft.Icon(
                    ft.Icons.CIRCLE, size=10,
                    color=ft.Colors.GREEN if available else ft.Colors.RED,
                ),
                ft.Text(
                    f"Ollama: {'running — ' + model_names if available else 'not reachable'}",
                    size=12, weight=ft.FontWeight.BOLD,
                ),
                ft.IconButton(
                    icon=ft.Icons.REFRESH, icon_size=16, tooltip="Re-check status",
                    on_click=refresh_status,
                ),
            ],
            spacing=6,
        )

        command_rows = []
        for cmd in llm_summary.quick_commands():
            command_rows.append(
                ft.Column(
                    [
                        ft.Text(cmd["title"], size=12, weight=ft.FontWeight.W_500),
                        ft.Row(
                            [
                                ft.Container(
                                    content=ft.Text(
                                        cmd["command"], size=12, selectable=True,
                                        font_family="monospace",
                                    ),
                                    bgcolor=ft.Colors.GREY_100,
                                    padding=_padding_symmetric(horizontal=10, vertical=6),
                                    border_radius=6,
                                    expand=True,
                                ),
                                ft.IconButton(
                                    icon=ft.Icons.COPY_OUTLINED, icon_size=16,
                                    tooltip="Copy command",
                                    action=ft.CopyToClipboard(cmd["command"]),
                                ),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.START,
                        ),
                    ],
                    spacing=4,
                )
            )

        is_android = llm_summary.is_android()
        tile_title = "Run / verify qwen in Termux" if is_android else "Run / verify qwen"
        tile_controls = [
            ft.Container(
                content=ft.Column(command_rows, spacing=10),
                padding=_padding_symmetric(horizontal=8, vertical=8),
            ),
        ]
        if is_android:
            tile_controls.append(
                ft.Container(
                    content=ft.Text(
                        llm_summary.ANDROID_CHAT_TIMING_NOTE, size=11,
                        color=ft.Colors.GREY_700, italic=True,
                    ),
                    padding=_padding_symmetric(horizontal=8, vertical=4),
                )
            )
            tile_controls.append(
                ft.Container(
                    content=ft.Button(
                        "First-time setup instead? Open LLM Setup",
                        on_click=lambda e: set_view("setup"),
                    ),
                    padding=_padding_symmetric(horizontal=8, vertical=4),
                )
            )

        return ft.Column(
            [
                status_row,
                ft.ExpansionTile(
                    title=ft.Text(tile_title, size=12),
                    expanded=not available,
                    controls=tile_controls,
                ),
            ],
            spacing=6,
        )

    def build_chat_view():
        ollama_available = llm_summary.is_ollama_available()
        status_panel = build_ollama_status_panel(ollama_available)

        if not ollama_available:
            return ft.Column(
                [
                    status_panel,
                    ft.Divider(),
                    ft.Text(
                        llm_summary.unavailable_message(),
                        size=13, color=ft.Colors.GREY_700,
                    ),
                ],
                spacing=10,
                expand=True,
            )

        session = get_current_chat()
        messages_col = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO, expand=True)
        if not session["messages"]:
            messages_col.controls.append(ft.Text(
                "Ask about market/investing concepts, technical indicators, or how to think "
                "about screening strategy. This chat isn't connected to live prices, news, or "
                "your own Watchlist/Screener data — use those tabs for that.",
                size=12, color=ft.Colors.GREY_600,
            ))
        for msg in session["messages"]:
            is_user = msg["role"] == "user"
            messages_col.controls.append(
                ft.Column(
                    [
                        ft.Text("You" if is_user else "Assistant", size=11,
                                weight=ft.FontWeight.BOLD, color=ft.Colors.GREY_600),
                        ft.Text(msg["content"], size=13, selectable=True),
                    ],
                    spacing=2,
                )
            )

        chat_pane = ft.Column(
            [
                status_panel,
                ft.Text(
                    "General stock market chat, powered by a local model — not connected to "
                    "live data or your portfolio.",
                    size=11, color=ft.Colors.GREY_600,
                ),
                ft.Divider(),
                ft.Container(content=messages_col, expand=True),
                ft.Row([chat_input_field, chat_send_btn, chat_progress],
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Text(llm_summary.GENERAL_CHAT_DISCLAIMER, size=10, color=ft.Colors.GREY_600),
            ],
            expand=True,
        )

        return ft.Row(
            [
                build_chat_history_panel(),
                ft.VerticalDivider(width=1),
                chat_pane,
            ],
            expand=True,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

    def build_setup_view():
        step_rows = []
        for step in llm_summary.TERMUX_SETUP_STEPS:
            controls = [ft.Text(step["title"], size=14, weight=ft.FontWeight.BOLD)]
            if step.get("detail"):
                controls.append(ft.Text(step["detail"], size=12, color=ft.Colors.GREY_700))
            if step.get("command"):
                controls.append(
                    ft.Row(
                        [
                            ft.Container(
                                content=ft.Text(
                                    step["command"], size=12, selectable=True,
                                    font_family="monospace",
                                ),
                                bgcolor=ft.Colors.GREY_100,
                                padding=_padding_symmetric(horizontal=10, vertical=8),
                                border_radius=6,
                                expand=True,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.COPY_OUTLINED,
                                tooltip="Copy command",
                                action=ft.CopyToClipboard(step["command"]),
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.START,
                    )
                )
            step_rows.append(ft.Column(controls, spacing=6))
            step_rows.append(ft.Divider())

        return ft.Column(
            [
                ft.Text("Run Ollama locally via Termux (Android)", size=18,
                        weight=ft.FontWeight.BOLD),
                ft.Text(
                    "Run each command below in Termux, in order. Tap the copy icon, "
                    "then paste into Termux and press Enter. Once step 9 succeeds, "
                    "come back and reopen the Chat tab.",
                    size=12, color=ft.Colors.GREY_700,
                ),
                ft.Divider(),
                ft.Column(step_rows, scroll=ft.ScrollMode.AUTO, expand=True, spacing=4),
            ],
            expand=True,
            spacing=10,
        )

    # ------------------------------------------------------------------
    # Wiring
    # ------------------------------------------------------------------
    def refresh_body():
        if state["view"] == "watchlist":
            body.content = build_watchlist_view()
        elif state["view"] == "screener":
            body.content = build_screener_view()
        elif state["view"] == "chat":
            body.content = build_chat_view()
        elif state["view"] == "setup":
            body.content = build_setup_view()
        else:
            body.content = build_macro_view()

    nav_buttons = [nav_watchlist_btn, nav_screener_btn, nav_macro_btn, nav_chat_btn]
    if llm_summary.is_android():
        # The "LLM Setup" tab only has Termux/Android instructions - on
        # desktop, Ollama is just a normal local install, so it doesn't apply.
        nav_buttons.append(nav_setup_btn)

    page.add(
        ft.SafeArea(
            ft.Column(
                [
                    ft.Row(nav_buttons, spacing=10, scroll=ft.ScrollMode.AUTO),
                    ft.Divider(),
                    body,
                ],
                expand=True,
            ),
            expand=True,
        ),
    )
    refresh_body()
    page.update()
    refresh_watchlist_data()


if __name__ == "__main__":
    try:
        ft.run(main)
    except AttributeError:
        ft.app(target=main)
