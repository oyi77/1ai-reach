import subprocess
import time
import pytest
from playwright.sync_api import sync_playwright


@pytest.fixture
def streamlit_server():
    """
    Fixture that starts Streamlit server on port 8502 for testing.
    Yields the subprocess, then cleans it up.
    """
    proc = subprocess.Popen(
        [
            ".venv/bin/streamlit",
            "run",
            "ui/app.py",
            "--server.port",
            "8502",
            "--logger.level=error",
        ],
        cwd="/home/openclaw/.openclaw/workspace/1ai-reach",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for server to start (max 10 seconds)
    for _ in range(10):
        try:
            import socket

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(("127.0.0.1", 8502))
            sock.close()
            if result == 0:
                break
        except Exception:
            pass
        time.sleep(1)

    yield proc

    # Cleanup
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def test_app_page_title(streamlit_server):
    """
    Test that the Streamlit app page title contains "1ai-reach".
    Launches browser, navigates to app, and asserts title.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        try:
            page.goto("http://localhost:8502", wait_until="networkidle", timeout=10000)

            # Wait for title to be set
            page.wait_for_load_state("networkidle")

            heading = page.locator("h1").first
            heading.wait_for(state="visible", timeout=10000)

            heading_text = heading.text_content()
            assert "1ai-reach" in heading_text, (
                f"Expected '1ai-reach' in heading, got: {heading_text}"
            )

            title = page.title()
            assert "1ai-reach" in title, (
                f"Expected '1ai-reach' in title, got: {title}"
            )

            page.get_by_role("tab", name="📊 Funnel").wait_for(
                state="visible", timeout=5000
            )
            page.get_by_role("tab", name="🚀 Run Pipeline").wait_for(
                state="visible", timeout=5000
            )
            page.get_by_role("tab", name="✏️ Draft Editor").wait_for(
                state="visible", timeout=5000
            )

        finally:
            browser.close()
