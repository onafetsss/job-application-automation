"""One-off capture: open the Easy Apply (SDUI) flow and dump its real structure.

SAFE: this script clicks the Easy Apply trigger to open the apply flow, then
DUMPS the form structure and STOPS. It NEVER clicks a submit/send button.
You can close the window without submitting anything.

Usage:
    PYTHONPATH=. LINKEDIN_PROFILE_DIR=data/linkedin_profile uv run python \
        scripts/capture_sdui_apply.py "<linkedin-easy-apply-job-url>"
"""

import asyncio
import os
import sys

# Robust, locale/class-independent trigger locator:
#  - anchor/button containing a span whose text is exactly "Easy Apply", OR
#  - anchor/button whose aria-label contains "Apply" (any case).
TRIGGER_XPATH = (
    "//a[.//span[normalize-space()='Easy Apply']]"
    " | //button[.//span[normalize-space()='Easy Apply']]"
    " | //a[contains(translate(@aria-label,'APPLY','apply'),'apply')]"
    " | //button[contains(translate(@aria-label,'APPLY','apply'),'apply')]"
)

DUMP_JS = """() => {
    const scope = document.querySelector('[role=dialog]') || document.body;
    const inputs = [];
    for (const el of scope.querySelectorAll('input, select, textarea')) {
        let labelText = '';
        if (el.id) {
            const lab = scope.querySelector(`label[for="${el.id}"]`);
            if (lab) labelText = (lab.innerText || '').trim();
        }
        inputs.push({
            tag: el.tagName,
            type: el.getAttribute('type'),
            name: el.getAttribute('name'),
            id: el.id,
            ariaLabel: el.getAttribute('aria-label'),
            required: el.required,
            label: labelText,
            options: el.tagName === 'SELECT'
                ? Array.from(el.options).map(o => o.text).slice(0, 8) : undefined,
        });
    }
    const buttons = [];
    for (const b of scope.querySelectorAll('button, a[role=button]')) {
        const t = (b.innerText || '').trim();
        const aria = b.getAttribute('aria-label');
        if (t || aria) buttons.push({text: t, ariaLabel: aria});
    }
    return {
        inUsedDialog: !!document.querySelector('[role=dialog]'),
        url: location.href,
        title: document.title,
        progressText: (scope.querySelector('progress, [role=progressbar], .artdeco-completeness-meter')||{}).outerHTML || null,
        inputs,
        buttons,
    };
}"""


async def main() -> None:
    from camoufox.async_api import AsyncCamoufox

    if len(sys.argv) < 2:
        print("ERROR: pass a LinkedIn Easy Apply job URL as the first argument.", file=sys.stderr)
        sys.exit(1)

    url = sys.argv[1]
    profile_dir = os.environ.get("LINKEDIN_PROFILE_DIR", "data/linkedin_profile")
    print(f"Job URL: {url}\n")

    async with AsyncCamoufox(
        headless=False,
        persistent_context=True,
        user_data_dir=profile_dir,
        os="windows",
    ) as context:
        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded")

        trigger = page.locator(f"xpath={TRIGGER_XPATH}")
        try:
            await trigger.first.wait_for(state="visible", timeout=20000)
        except Exception:
            print("Could not find the Easy Apply trigger within 20s. Aborting.")
            await asyncio.get_event_loop().run_in_executor(None, input, "Press Enter to close: ")
            return

        label = await trigger.first.get_attribute("aria-label")
        print(f"Clicking Easy Apply trigger (aria-label={label!r})...")
        await trigger.first.click()

        # Wait for the apply flow to render (modal dialog or navigation).
        await asyncio.sleep(5)
        try:
            await page.wait_for_selector("[role=dialog], form", timeout=10000)
        except Exception:
            pass

        shot = "data/sdui_apply_debug.png"
        await page.screenshot(path=shot, full_page=False)
        print(f"Screenshot saved: {shot}\n")

        # The apply modal renders inside an iframe — dump EVERY frame so we
        # find the one hosting the form.
        print(f"Total frames: {len(page.frames)}\n")
        for idx, frame in enumerate(page.frames):
            try:
                data = await frame.evaluate(DUMP_JS)
            except Exception as exc:
                print(f"--- frame[{idx}] {frame.url[:70]!r}: eval failed ({exc})")
                continue
            if not data["inputs"] and not data["buttons"]:
                continue
            print(f"=== frame[{idx}] url={frame.url[:90]!r} ===")
            print(f"    dialog={data['inUsedDialog']} title={data['title']!r}")
            print(f"    progress={data['progressText']}")
            print(f"    FORM FIELDS ({len(data['inputs'])}):")
            for i in data["inputs"]:
                print(f"      <{i['tag']}> type={i['type']!r} required={i['required']}"
                      f" name={i['name']!r} id={i['id']!r}")
                print(f"        label={i['label']!r} aria-label={i['ariaLabel']!r}")
                if i.get("options"):
                    print(f"        options={i['options']}")
            print(f"    BUTTONS ({len(data['buttons'])}):")
            for b in data["buttons"]:
                print(f"      text={b['text']!r}  aria-label={b['ariaLabel']!r}")
            print()

        print("\n*** NOT submitting. Inspect/close the window freely. ***")
        await asyncio.get_event_loop().run_in_executor(
            None, input, "\nPress Enter to close (nothing is submitted): "
        )


if __name__ == "__main__":
    asyncio.run(main())
