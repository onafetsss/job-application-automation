"""One-time LinkedIn session persistence script.

Run this script once to log in to LinkedIn manually using a Camoufox browser window.
After you complete the login (including any 2FA), press Enter in this terminal.
Camoufox will persist the session into the profile directory so all subsequent
automated runs can reuse it without re-authentication.

Usage:
    LINKEDIN_PROFILE_DIR=data/linkedin_profile uv run python scripts/linkedin_session_save.py

Environment variables:
    LINKEDIN_PROFILE_DIR  Path to the Camoufox persistent profile directory.
                          Defaults to 'data/linkedin_profile' (relative to project root).

Session storage:
    Primary:  Camoufox persistent profile directory (user_data_dir) — this is the
              main session store and survives across runs. LinkedIn's __Host- prefixed
              cookies persist correctly in this mode (unlike storage_state JSON).
    Fallback: data/linkedin_session.json — Playwright storage_state JSON export.
              Wrapped in try/except because __Host- cookies may not serialize correctly.
              Non-fatal if it fails; the profile directory is the reliable store.

Security: T-03-12 — No credentials are stored in this file. Login is performed manually
          in the browser window. The profile directory must remain git-ignored (data/).
"""

import asyncio
import os
import sys


async def save_session() -> None:
    """Open a Camoufox browser for manual LinkedIn login and persist the session."""
    try:
        from camoufox.async_api import AsyncCamoufox
    except ImportError:
        print(
            "ERROR: camoufox is not installed. Run: uv add camoufox && python -m camoufox fetch",
            file=sys.stderr,
        )
        sys.exit(1)

    profile_dir = os.environ.get("LINKEDIN_PROFILE_DIR", "data/linkedin_profile")
    os.makedirs(profile_dir, exist_ok=True)

    print(f"\n{'='*60}")
    print("LinkedIn Session Save Script")
    print(f"{'='*60}")
    print(f"\nProfile directory: {os.path.abspath(profile_dir)}")
    print("\nA Camoufox browser window will open to the LinkedIn login page.")
    print("Steps:")
    print("  1. Log in to LinkedIn with your credentials in the browser window.")
    print("  2. Complete any 2FA or CAPTCHA prompts.")
    print("  3. Wait until you are fully logged in (feed page loads).")
    print("  4. Return to this terminal and press Enter to save the session.")
    print("\nDo NOT close the browser window manually — press Enter here to save.\n")

    async with AsyncCamoufox(
        headless=False,
        persistent_context=True,
        user_data_dir=profile_dir,
        os="windows",
    ) as context:
        page = await context.new_page()
        await page.goto("https://www.linkedin.com/login")
        print("Browser opened. Log in to LinkedIn, then press Enter here...")

        # Wait for the human to log in and press Enter
        await asyncio.get_event_loop().run_in_executor(None, input)

        current_url = page.url
        print(f"\nCurrent URL: {current_url}")

        # Best-effort storage_state JSON export as fallback (non-fatal)
        storage_state_path = "data/linkedin_session.json"
        try:
            await page.context.storage_state(path=storage_state_path)
            print(f"Fallback session JSON saved to: {storage_state_path}")
            print("(Note: __Host- cookies may not serialize correctly in JSON format.")
            print(" The profile directory is the primary session store.)")
        except Exception as exc:
            print(f"Fallback JSON export skipped (non-fatal): {exc}")

    print(f"\nSession saved to profile directory: {os.path.abspath(profile_dir)}")
    print("The profile directory contains the persistent session.")
    print("Subsequent automated runs will load the session from this directory.")
    print("\nNext steps:")
    print("  1. Verify the session: run the fingerprint check (bot.sannysoft.com).")
    print("  2. Import linkedin-easy-apply.json into the n8n UI.")
    print("  3. Activate the workflow when you are ready for autonomous runs.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(save_session())
