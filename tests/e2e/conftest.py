import os

import pytest


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    """Use a system Chromium when PLAYWRIGHT_CHROMIUM_EXECUTABLE is set (e.g. where `playwright install` is blocked)."""
    exe = os.getenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
    return {**browser_type_launch_args, "executable_path": exe, "args": ["--no-sandbox"]} if exe else browser_type_launch_args
