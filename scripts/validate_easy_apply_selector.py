"""One-off validation: confirm the Easy Apply button XPath resolves on a live job.

Usage:
    LINKEDIN_PROFILE_DIR=data/linkedin_profile uv run python \
        scripts/validate_easy_apply_selector.py "<linkedin-job-url>"

Opens the job URL using the persisted LinkedIn session and reports how many
elements match the EASY_APPLY_TEXT_SELECTOR the applier relies on, plus the button
text, so the live-SDUI selector can be confirmed (or flagged as drifted).
"""

import asyncio
import os
import sys

from src.browser.linkedin_applier import EASY_APPLY_TEXT_SELECTOR


async def main() -> None:
    from camoufox.async_api import AsyncCamoufox

    if len(sys.argv) < 2:
        print("ERROR: pass a LinkedIn job URL as the first argument.", file=sys.stderr)
        sys.exit(1)

    url = sys.argv[1]
    profile_dir = os.environ.get("LINKEDIN_PROFILE_DIR", "data/linkedin_profile")

    print(f"Selector under test: {EASY_APPLY_TEXT_SELECTOR}")
    print(f"Job URL: {url}\n")

    async with AsyncCamoufox(
        headless=False,
        persistent_context=True,
        user_data_dir=profile_dir,
        os="windows",
    ) as context:
        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded")

        # LinkedIn renders the apply button lazily — wait for it explicitly.
        try:
            await page.wait_for_selector(EASY_APPLY_TEXT_SELECTOR, timeout=20000)
        except Exception:
            print("(button did not appear within 20s — introspecting anyway)\n")

        # Ground-truth diagnostics: what is automation actually seeing?
        print(f"Page title: {await page.title()!r}")
        print(f"Final URL:  {page.url}")
        shot = "data/li_debug.png"
        await page.screenshot(path=shot, full_page=False)
        print(f"Screenshot saved: {shot}")

        diag = await page.evaluate(
            """() => {
                const btns = Array.from(document.querySelectorAll('button'));
                return {
                    totalButtons: btns.length,
                    iframes: document.querySelectorAll('iframe').length,
                    hasEasyApplyText: document.body.innerText.includes('Easy Apply')
                        || document.body.innerText.includes('Mag-apply'),
                    sampleButtonTexts: btns.slice(0, 40).map(b => (b.innerText || '').trim()).filter(Boolean),
                };
            }"""
        )
        print(f"Total <button> elements: {diag['totalButtons']}")
        print(f"iframes on page: {diag['iframes']}")
        print(f"'Easy Apply' text present in body: {diag['hasEasyApplyText']}")
        print(f"First button texts: {diag['sampleButtonTexts']}\n")

        # Pinpoint the real Easy Apply control by its visible text / aria-label.
        found = await page.evaluate(
            """() => {
                const out = [];
                const all = document.querySelectorAll('*');
                for (const el of all) {
                    const t = (el.innerText || '').trim();
                    const aria = el.getAttribute && el.getAttribute('aria-label') || '';
                    const isApply = /easy apply/i.test(aria) ||
                        (t.toLowerCase() === 'easy apply');
                    if (isApply && ['BUTTON','A','DIV','SPAN'].includes(el.tagName)) {
                        out.push({
                            tag: el.tagName,
                            className: el.className && el.className.toString(),
                            id: el.id,
                            ariaLabel: aria,
                            role: el.getAttribute('role'),
                            outerHTML: el.outerHTML.slice(0, 240),
                        });
                    }
                }
                return out.slice(0, 6);
            }"""
        )
        print("=== Elements matching 'Easy Apply' (text or aria-label) ===")
        if not found:
            print("  none found in main frame — checking iframe...")
            for frame in page.frames:
                try:
                    fcount = await frame.locator(
                        "xpath=//*[contains(@aria-label,'Easy Apply') or normalize-space(text())='Easy Apply']"
                    ).count()
                    if fcount:
                        print(f"  frame {frame.url[:60]!r}: {fcount} match(es)")
                except Exception:
                    pass
        else:
            for f in found:
                print(f"  <{f['tag']}> role={f['role']!r} id={f['id']!r}")
                print(f"    class={f['className']!r}")
                print(f"    aria-label={f['ariaLabel']!r}")
                print(f"    html={f['outerHTML']!r}")
        print()

        locator = page.locator(EASY_APPLY_TEXT_SELECTOR)
        count = await locator.count()
        print(f"Matched elements: {count}")
        if count > 0:
            try:
                text = (await locator.first.inner_text()).strip()
                print(f"Button text: {text!r}")
                print("RESULT: PASS — selector resolves.")
            except Exception as exc:
                print(f"Button found but text read failed: {exc}")
                print("RESULT: PASS (element present).")
        else:
            print("RESULT: selector did not match — introspecting page for apply buttons...\n")
            candidates = await page.evaluate(
                """() => {
                    const out = [];
                    for (const b of document.querySelectorAll('button')) {
                        const t = (b.innerText || '').trim();
                        if (/apply/i.test(t) || /apply/i.test(b.className)) {
                            out.push({text: t, className: b.className, ariaLabel: b.getAttribute('aria-label')});
                        }
                    }
                    return out;
                }"""
            )
            if not candidates:
                print("No apply-related buttons found at all — likely not an Easy Apply job,")
                print("or the page did not finish rendering. Confirm the job shows 'Easy Apply'.")
            else:
                print(f"Found {len(candidates)} apply-related button(s):")
                for c in candidates:
                    print(f"  text={c['text']!r}")
                    print(f"    class={c['className']!r}")
                    print(f"    aria-label={c['ariaLabel']!r}")

        await asyncio.get_event_loop().run_in_executor(
            None, input, "\nInspect the browser, then press Enter to close: "
        )


if __name__ == "__main__":
    asyncio.run(main())
