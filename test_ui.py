"""Comprehensive UI tests for pyflate2 visualizer.
Tests hover highlighting, tab switching, scroll centering, compression stats,
input changes, and edge cases across mobile and desktop viewports.
"""
import http.server
import threading
import pathlib
import sys

from playwright.sync_api import sync_playwright

PORT = 18938

# Prepare local version
html = pathlib.Path("index.html").read_text()
html = html.replace(
    "https://cdn.jsdelivr.net/npm/brython@3.12.4/brython.min.js", "brython.min.js"
).replace(
    "https://cdn.jsdelivr.net/npm/brython@3.12.4/brython_stdlib.js", "brython_stdlib.js"
)
pathlib.Path("index_local.html").write_text(html)

handler = http.server.SimpleHTTPRequestHandler
httpd = http.server.HTTPServer(("127.0.0.1", PORT), handler)
threading.Thread(target=httpd.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{PORT}/index_local.html"

FAILS = []
PASSES = 0


def check(condition, msg):
    global PASSES
    if condition:
        PASSES += 1
    else:
        FAILS.append(msg)
    print(f"  {'PASS' if condition else 'FAIL'}: {msg}")


def wait_for_brython(page):
    page.wait_for_function(
        "() => document.getElementById('loading_label').textContent.trim() === ''",
        timeout=30000,
    )
    page.wait_for_timeout(500)


def find_bit_span(page, message_num):
    """Find a hexdump bit span with given message number."""
    for el in page.query_selector_all("#hexdump span"):
        classes = el.get_attribute("class") or ""
        if f"message-{message_num}" in classes and "bit-" in classes:
            return el
    return None


with sync_playwright() as p:
    browser = p.firefox.launch()

    # ================================================================
    # MOBILE TESTS (390x844)
    # ================================================================
    print("\n" + "=" * 60)
    print("MOBILE PORTRAIT (390x844)")
    print("=" * 60)

    ctx = browser.new_context(
        viewport={"width": 390, "height": 844},
        locale="en-US",
        has_touch=True,
    )
    page = ctx.new_page()
    page.goto(URL)
    wait_for_brython(page)

    # --- Compression stats coloring ---
    print("\n--- Compression stats ---")
    comp_el = page.query_selector("#compression_result")
    comp_html = comp_el.inner_html()
    check("f06868" in comp_html or "240, 104, 104" in comp_html or "red" in comp_html.lower(),
          "compression diff colored red for expansion (Hello,world -> bigger)")

    # Change to something that compresses well (long repeated text)
    inp = page.query_selector("#input")
    inp.fill("A" * 200)
    page.wait_for_timeout(2000)
    comp_html2 = page.query_selector("#compression_result").inner_html()
    comp_text2 = page.inner_text("#compression_result")
    check("5ccf8a" in comp_html2 or "92, 207, 138" in comp_html2 or "green" in comp_html2.lower(),
          f"compression diff colored green for actual compression: {comp_text2}")
    check("-" in comp_text2,
          f"negative diff shown: {comp_text2}")

    # Reset to default
    inp.fill("Hello, world!")
    page.wait_for_timeout(2000)

    # --- Hexdump fits viewport ---
    print("\n--- Hexdump width ---")
    hd_overflow = page.evaluate(
        "() => document.getElementById('hexdump').scrollWidth <= document.getElementById('hexdump').clientWidth + 2"
    )
    check(hd_overflow, "hexdump does not overflow on mobile")

    bpl = page.evaluate("""() => {
        var lines = document.getElementById('hexdump').textContent.split('\\n').filter(l => l.trim());
        // count hex bytes on first line: between offset and '['
        var m = lines[0].match(/^[0-9a-f]+\\s+([0-9a-f ]+)\\[/);
        if (!m) return -1;
        return m[1].trim().split(/\\s+/).length;
    }""")
    check(bpl == 2, f"mobile uses 2 bytes per hexdump line (got {bpl})")

    # --- Tab switching ---
    print("\n--- Huffman tabs ---")
    t1_vis = page.evaluate(
        "!document.getElementById('huffman_browser_table1').classList.contains('huff-hidden')"
    )
    t2_hid = page.evaluate(
        "document.getElementById('huffman_browser_table2').classList.contains('huff-hidden')"
    )
    check(t1_vis, "tab1 (literals) visible by default")
    check(t2_hid, "tab2 (distances) hidden by default")

    page.click('.huffman-tab[data-tab="2"]')
    page.wait_for_timeout(200)
    t1_hid = page.evaluate(
        "document.getElementById('huffman_browser_table1').classList.contains('huff-hidden')"
    )
    t2_vis = page.evaluate(
        "!document.getElementById('huffman_browser_table2').classList.contains('huff-hidden')"
    )
    check(t1_hid, "tab1 hidden after clicking tab2")
    check(t2_vis, "tab2 visible after clicking tab2")

    # --- Auto tab switch on hover ---
    print("\n--- Auto tab switch on hover ---")
    # Currently on tab 2. Hover a literal bit -> should switch to tab 1.
    bit_el = find_bit_span(page, 91)
    check(bit_el is not None, "found bit span for message-91 (literal H)")
    if bit_el:
        bit_el.hover()
        page.wait_for_timeout(400)
        active = page.evaluate(
            "document.querySelector('.huffman-tab.active').getAttribute('data-tab')"
        )
        check(active == "1", f"auto-switched to tab 1 on literal hover (got {active})")

    # --- Huffman highlight + center scroll ---
    print("\n--- Huffman highlight & scroll ---")
    highlighted = page.query_selector_all("tr.huffman-highlight")
    check(len(highlighted) > 0, f"huffman row highlighted ({len(highlighted)} rows)")

    # Check centering - find a highlighted row that's in a visible container
    if highlighted:
        for hl_row in highlighted:
            row_box = hl_row.bounding_box()
            if row_box and row_box["height"] > 0:
                # Find which visible container it's in
                in_t1 = page.evaluate(
                    "(el) => document.getElementById('huffman_browser_table1').contains(el)",
                    hl_row,
                )
                cid = "huffman_browser_table1" if in_t1 else "huffman_browser_table2"
                container = page.query_selector(f"#{cid}")
                cont_box = container.bounding_box()
                if cont_box and cont_box["height"] > 0:
                    row_mid = row_box["y"] + row_box["height"] / 2
                    cont_mid = cont_box["y"] + cont_box["height"] / 2
                    offset = abs(row_mid - cont_mid)
                    check(
                        offset < cont_box["height"] * 0.4,
                        f"row centered: offset={offset:.0f}px in {cont_box['height']:.0f}px container",
                    )
                    break

    # --- Highlight clears on mouse leave ---
    page.mouse.move(0, 0)
    page.wait_for_timeout(300)
    hl_after = page.query_selector_all("tr.huffman-highlight")
    check(len(hl_after) == 0, "huffman highlight cleared on mouseleave")
    sel_text = page.inner_text("#selected_bits")
    check(sel_text.strip() in ("", "\u2014"), "selected bits cleared on mouseleave")

    # --- Selected bits display ---
    print("\n--- Selected bits ---")
    if bit_el:
        bit_el.hover()
        page.wait_for_timeout(300)
        sel = page.inner_text("#selected_bits")
        check("0x" in sel, f"selected bits shows hex: {sel.strip()[:50]}")
        check("(" in sel, "selected bits shows decimal in parens")

    # --- Modal open/close ---
    print("\n--- Modal ---")
    page.mouse.move(0, 0)
    page.wait_for_timeout(200)
    page.click("#help_button")
    page.wait_for_timeout(300)
    modal_vis = page.evaluate(
        "getComputedStyle(document.querySelector('.modal')).display !== 'none'"
    )
    check(modal_vis, "modal opens on button click")

    # Help sections don't overflow
    overflows = page.evaluate("""() => {
        var secs = document.querySelectorAll('.help-section');
        var bad = [];
        for (var s of secs) if (s.scrollWidth > s.clientWidth + 2) bad.push(s.scrollWidth - s.clientWidth);
        return bad;
    }""")
    check(len(overflows) == 0, f"no help section overflow ({overflows})")

    # Close with Escape
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)
    modal_hid = page.evaluate(
        "getComputedStyle(document.querySelector('.modal')).display === 'none'"
    )
    check(modal_hid, "modal closes on Escape")

    # Close with backdrop click
    page.click("#help_button")
    page.wait_for_timeout(200)
    page.mouse.click(5, 5)
    page.wait_for_timeout(200)
    modal_hid2 = page.evaluate(
        "getComputedStyle(document.querySelector('.modal')).display === 'none'"
    )
    check(modal_hid2, "modal closes on backdrop click")

    # --- No body overflow ---
    print("\n--- Layout ---")
    no_overflow = page.evaluate(
        "document.body.scrollHeight <= window.innerHeight + 2"
    )
    check(no_overflow, "body doesn't overflow viewport")

    ctx.close()

    # ================================================================
    # DESKTOP TESTS (1280x800)
    # ================================================================
    print("\n" + "=" * 60)
    print("DESKTOP (1280x800)")
    print("=" * 60)

    ctx = browser.new_context(
        viewport={"width": 1280, "height": 800}, locale="en-US"
    )
    page = ctx.new_page()
    page.goto(URL)
    wait_for_brython(page)

    # --- Hexdump uses 4 bytes per line ---
    print("\n--- Hexdump ---")
    bpl_d = page.evaluate("""() => {
        var lines = document.getElementById('hexdump').textContent.split('\\n').filter(l => l.trim());
        var m = lines[0].match(/^[0-9a-f]+\\s+([0-9a-f ]+)\\[/);
        if (!m) return -1;
        return m[1].trim().split(/\\s+/).length;
    }""")
    check(bpl_d == 4, f"desktop uses 4 bytes per hexdump line (got {bpl_d})")

    # --- Both Huffman tables visible ---
    print("\n--- Huffman tables ---")
    t1_d = page.evaluate(
        "getComputedStyle(document.getElementById('huffman_browser_table1')).display !== 'none'"
    )
    t2_d = page.evaluate(
        "getComputedStyle(document.getElementById('huffman_browser_table2')).display !== 'none'"
    )
    check(t1_d, "both tables visible: table1")
    check(t2_d, "both tables visible: table2")

    # Tab click should NOT hide on desktop
    page.click('.huffman-tab[data-tab="2"]')
    page.wait_for_timeout(200)
    t1_still = page.evaluate(
        "getComputedStyle(document.getElementById('huffman_browser_table1')).display !== 'none'"
    )
    check(t1_still, "tab click doesn't hide tables on desktop")

    # --- Hover highlight works ---
    print("\n--- Hover interactions ---")
    bit_el_d = find_bit_span(page, 91)
    if bit_el_d:
        bit_el_d.hover()
        page.wait_for_timeout(400)
        hl_d = page.query_selector_all("tr.huffman-highlight")
        check(
            len(hl_d) >= 1,
            f"huffman rows highlighted on desktop ({len(hl_d)})",
        )
        # Both tables should have the highlighted row
        hl_in_t1 = page.evaluate("""() => {
            var t1 = document.getElementById('huffman_browser_table1');
            return t1.querySelectorAll('tr.huffman-highlight').length;
        }""")
        hl_in_t2 = page.evaluate("""() => {
            var t2 = document.getElementById('huffman_browser_table2');
            return t2.querySelectorAll('tr.huffman-highlight').length;
        }""")
        check(hl_in_t1 > 0, f"highlight in table1: {hl_in_t1}")
        check(hl_in_t2 > 0, f"highlight in table2: {hl_in_t2}")

    # --- Cross-scroll: log hover scrolls hexdump ---
    print("\n--- Cross-scroll ---")
    log_spans = page.query_selector_all("#output span.log-message-91")
    if log_spans:
        log_spans[0].hover()
        page.wait_for_timeout(400)
        sel_d = page.inner_text("#selected_bits")
        check("0x" in sel_d, f"hovering log entry shows selected bits: {sel_d.strip()[:40]}")

    ctx.close()

    # ================================================================
    # EDGE CASES
    # ================================================================
    print("\n" + "=" * 60)
    print("EDGE CASES")
    print("=" * 60)

    ctx = browser.new_context(
        viewport={"width": 390, "height": 844},
        locale="en-US",
        has_touch=True,
    )
    page = ctx.new_page()
    page.goto(URL)
    wait_for_brython(page)

    # --- Empty input ---
    print("\n--- Empty input ---")
    inp = page.query_selector("#input")
    inp.click()
    inp.press("Control+a")
    inp.press("Backspace")
    page.wait_for_timeout(2000)
    comp_empty = page.inner_text("#compression_result")
    check(
        "0B" in comp_empty or len(comp_empty.strip()) > 0,
        f"empty input shows stats: {comp_empty.strip()[:40]}",
    )

    # --- Single character ---
    print("\n--- Single character ---")
    inp.fill("X")
    page.wait_for_timeout(2000)
    comp_single = page.inner_text("#compression_result")
    check("1B" in comp_single, f"single char shows 1B input: {comp_single.strip()}")

    # --- Long input ---
    print("\n--- Long input ---")
    inp.fill("The quick brown fox jumps over the lazy dog. " * 10)
    page.wait_for_timeout(3000)
    comp_long = page.inner_text("#compression_result")
    check(
        "\u2192" in comp_long,
        f"long input shows compression: {comp_long.strip()[:60]}",
    )
    # Should actually compress (green)
    comp_html_long = page.query_selector("#compression_result").inner_html()
    check(
        "5ccf8a" in comp_html_long or "92, 207, 138" in comp_html_long,
        "long repeated text compresses (green color)",
    )

    # --- Special characters ---
    print("\n--- Special characters ---")
    inp.fill("\u00e9\u00e8\u00ea\u00eb")  # accented chars
    page.wait_for_timeout(2000)
    hex_special = page.inner_text("#hexdump")
    check(len(hex_special.strip()) > 0, "special chars produce hexdump")

    # --- Distance tab auto-switch ---
    print("\n--- Distance tab auto-switch ---")
    inp.fill("ABCABCABCABCABCABC")  # repeated pattern -> LZ77 distance codes
    page.wait_for_timeout(3000)
    # Find a log entry mentioning "dist" or "r1="
    dist_cls = page.evaluate("""() => {
        var spans = document.querySelectorAll('#output span');
        for (var s of spans) {
            var t = s.textContent;
            if (t.includes('extra bits for dist') || t.includes('r1=')) {
                return Array.from(s.classList).find(c => c.startsWith('message-')) || null;
            }
        }
        return null;
    }""")
    if dist_cls:
        dist_el = page.query_selector(f"span.log-{dist_cls}")
        if dist_el:
            dist_el.scroll_into_view_if_needed()
            dist_el.hover()
            page.wait_for_timeout(400)
            active_tab_dist = page.evaluate(
                "document.querySelector('.huffman-tab.active').getAttribute('data-tab')"
            )
            check(active_tab_dist == "2",
                  f"distance log hover switches to tab 2 (got tab {active_tab_dist})")
            page.mouse.move(0, 0)
            page.wait_for_timeout(200)
        else:
            check(False, "could not find distance log span element")
    else:
        check(False, "no distance log entry found for ABCABC input")

    inp.fill("Hello, world!")
    page.wait_for_timeout(2000)

    # --- Tab auto-switch persistence: switch tab, change input, check tab resets ---
    print("\n--- Tab persistence on input change ---")
    inp.fill("Hello")
    page.wait_for_timeout(2000)
    page.click('.huffman-tab[data-tab="2"]')
    page.wait_for_timeout(200)
    active_before = page.evaluate(
        "document.querySelector('.huffman-tab.active').getAttribute('data-tab')"
    )
    check(active_before == "2", "tab2 active before input change")
    # Change input - Brython reruns, tables rebuild
    inp.fill("World")
    page.wait_for_timeout(2000)
    # Tab state should persist (JS tabs are independent of Brython)
    active_after = page.evaluate(
        "document.querySelector('.huffman-tab.active').getAttribute('data-tab')"
    )
    check(
        active_after == "2",
        f"tab persists after input change (got tab {active_after})",
    )

    ctx.close()

    # ================================================================
    # LANDSCAPE (844x390)
    # ================================================================
    print("\n" + "=" * 60)
    print("LANDSCAPE (844x390)")
    print("=" * 60)

    ctx = browser.new_context(
        viewport={"width": 844, "height": 390}, locale="en-US"
    )
    page = ctx.new_page()
    page.goto(URL)
    wait_for_brython(page)

    print("\n--- Layout fits ---")
    no_overflow_l = page.evaluate(
        "document.body.scrollHeight <= window.innerHeight + 2"
    )
    check(no_overflow_l, "body fits in landscape viewport")

    # Hexdump should use 4 bytes (>500px width)
    bpl_l = page.evaluate("""() => {
        var lines = document.getElementById('hexdump').textContent.split('\\n').filter(l => l.trim());
        var m = lines[0].match(/^[0-9a-f]+\\s+([0-9a-f ]+)\\[/);
        if (!m) return -1;
        return m[1].trim().split(/\\s+/).length;
    }""")
    check(bpl_l == 4, f"landscape uses 4 bytes per line (got {bpl_l})")

    ctx.close()

    browser.close()

httpd.shutdown()

# ================================================================
# SUMMARY
# ================================================================
total = PASSES + len(FAILS)
print(f"\n{'=' * 60}")
print(f"RESULTS: {PASSES}/{total} passed")
if FAILS:
    print(f"\nFAILED ({len(FAILS)}):")
    for f in FAILS:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("ALL TESTS PASSED")
