"""Automated WCAG 2.1 AA scan with axe-core. Needs the axe script: npm i axe-core, then AXE_JS=node_modules/axe-core/axe.min.js"""
import os

import pytest

from test_ui import sign_in, url  # noqa: F401

AXE = os.getenv("AXE_JS")
pytestmark = pytest.mark.skipif(not AXE, reason="set AXE_JS to run the accessibility scan")


def violations(page):
    page.add_script_tag(path=AXE)
    res = page.evaluate("axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}})")
    return [(v["id"], v["impact"], len(v["nodes"])) for v in res["violations"]]


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_main_screens_have_no_axe_violations(page, url, theme):
    page.add_init_script(f"localStorage.theme='{theme}'")
    page.goto(url)
    assert violations(page) == []
    sign_in(page, url, "admin", "adminpass1")
    page.wait_for_selector("#chat:not([hidden])")
    assert violations(page) == []
    page.locator("#admin summary").click()
    assert violations(page) == []
    page.locator("#avatarbtn").click()
    page.get_by_role("button", name="Edit profile").click()
    page.locator("#pf_phone").fill("12")
    assert violations(page) == []
