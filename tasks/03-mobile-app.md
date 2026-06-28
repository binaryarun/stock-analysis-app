# Phase 2 — Mobile app (Android first)

Goal: ship the existing Flet app as an installable Android APK without
rewriting app logic, building on the data source/cache work from Phase 1.

## Build environment

- [ ] Install Flutter SDK (Flet's build step depends on it)
- [ ] Install Android SDK + NDK + a recent JDK
- [ ] Confirm `flet build apk` runs end-to-end on a trivial change and
      produces an installable `.apk` under `build/`
- [ ] Document the exact toolchain versions that worked in `README.md`

## UI/layout audit for mobile

- [ ] Review `main.py` for desktop-only assumptions (fixed widths, side-by-side
      panels, hover-only interactions) and adapt to narrow/portrait layouts
- [ ] Check the detail view dialog (price chart + RSI subplot) renders
      legibly on a phone-sized screen; resize/scroll as needed
- [ ] Check the screener results table/list is usable with touch (tap to
      open detail, no reliance on right-click or hover tooltips)
- [ ] Verify on-screen keyboard behavior for watchlist add/remove and
      threshold input fields

## Background work & performance on Android

- [ ] Confirm `ThreadPoolExecutor`-based concurrent fetching in
      `data_provider.py` behaves correctly under Android's process/thread
      model (no UI freezing during a full index scan)
- [ ] Test app behavior when backgrounded mid-fetch and resumed
- [ ] Confirm `storage.py`'s watchlist JSON path resolves to a valid writable
      location on Android (not the desktop home-dir assumption)
- [ ] Sanity-check matplotlib chart rendering performance on a real device
      (not just an emulator)

## Networking on mobile

- [ ] Confirm whichever data providers are active (yfinance / NSE / NASDAQ
      from Phase 1) work over a mobile network/cellular, not just wifi
- [ ] Handle offline/no-connectivity gracefully (clear error state instead
      of a silent hang)

## Packaging & distribution

- [ ] Decide on app icon / splash screen for the build
- [ ] Produce a signed release `.apk` (or `.aab`) for sideloading/testing
- [ ] Decide distribution path: sideload only, or Play Store listing later
- [ ] Note iOS (`flet build ipa`) as explicitly deferred — requires a Mac +
      Apple developer account, already called out in `README.md`

## Validation

- [ ] Install on a real Android device and run through: watchlist add/remove,
      a full Nifty 50 scan, a full S&P 500 scan, opening a detail view/chart
- [ ] Confirm watchlist persists across app restarts on-device
