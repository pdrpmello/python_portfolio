"""Testes dos helpers Selenium com driver falso (sem browser real)."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock

from selenium.common.exceptions import TimeoutException

from browser import (
    create_driver,
    element_exists,
    find_all_first_match,
    read_text_from_selectors,
    save_debug_artifacts,
    wait_for_any_visible,
)


class FakeElement:
    def __init__(self, text="", displayed=True):
        self.text = text
        self._displayed = displayed

    def is_displayed(self):
        return self._displayed


class FakeDriver:
    """Duck type mínimo de WebDriver/WebElement para os helpers."""

    def __init__(self, elements_by_selector=None, page_source="<html></html>"):
        self.elements_by_selector = elements_by_selector or {}
        self.page_source = page_source
        self.screenshots = []

    def find_elements(self, by, selector):
        return self.elements_by_selector.get(selector, [])

    def save_screenshot(self, path):
        self.screenshots.append(path)
        Path(path).write_bytes(b"PNG")
        return True


class FindHelpersTest(unittest.TestCase):
    def test_first_matching_selector_wins(self):
        first, second = FakeElement("a"), FakeElement("b")
        driver = FakeDriver({".x": [], ".y": [first, second]})
        self.assertEqual(find_all_first_match(driver, [".x", ".y"]), [first, second])

    def test_no_match_returns_empty(self):
        self.assertEqual(find_all_first_match(FakeDriver(), [".x"]), [])

    def test_read_text_skips_empty_and_falls_through(self):
        driver = FakeDriver({".a": [FakeElement("  ")], ".b": [FakeElement("texto")]})
        self.assertEqual(read_text_from_selectors(driver, [".a", ".b"]), "texto")

    def test_read_text_none_when_nothing(self):
        self.assertIsNone(read_text_from_selectors(FakeDriver(), [".a"]))

    def test_element_exists(self):
        driver = FakeDriver({".a": [FakeElement()]})
        self.assertTrue(element_exists(driver, [".a"]))
        self.assertFalse(element_exists(driver, [".zzz"]))


class WaitForAnyVisibleTest(unittest.TestCase):
    def test_returns_first_visible(self):
        visible = FakeElement(displayed=True)
        driver = FakeDriver({".a": [FakeElement(displayed=False)], ".b": [visible]})
        self.assertIs(wait_for_any_visible(driver, [".a", ".b"], 1), visible)

    def test_timeout_lists_selectors(self):
        with self.assertRaises(TimeoutException) as ctx:
            wait_for_any_visible(FakeDriver(), [".a", ".b"], 0.3)
        self.assertIn(".a", str(ctx.exception))
        self.assertIn(".b", str(ctx.exception))


class DebugArtifactsTest(unittest.TestCase):
    def test_saves_screenshot_and_html(self):
        driver = FakeDriver(page_source="<html>debug</html>")
        with TemporaryDirectory() as tmp:
            save_debug_artifacts(driver, tmp, tag="teste")
            files = sorted(p.name for p in Path(tmp).iterdir())
        self.assertEqual(len(files), 2)
        self.assertTrue(files[0].endswith("-teste.html"))
        self.assertTrue(files[1].endswith("-teste.png"))

    def test_never_raises(self):
        class BrokenDriver:
            def save_screenshot(self, path):
                raise RuntimeError("browser morto")

            page_source = ""

        with TemporaryDirectory() as tmp:
            save_debug_artifacts(BrokenDriver(), tmp)  # não deve levantar


class CreateDriverTest(unittest.TestCase):
    """create_driver com webdriver.Chrome mockado (sem browser real)."""

    def _cfg(self, **kw):
        base = dict(
            headless=True,
            page_load_timeout_seconds=30,
            chrome_binary="",
            chrome_extra_args=(),
        )
        base.update(kw)
        return SimpleNamespace(**base)

    def test_chrome_binary_and_extra_args_applied(self):
        with mock.patch("browser.webdriver.Chrome") as chrome_cls:
            create_driver(
                self._cfg(
                    chrome_binary="/opt/chrome-linux64/chrome",
                    chrome_extra_args=("--no-sandbox", "--disable-dev-shm-usage"),
                )
            )
        options = chrome_cls.call_args.kwargs["options"]
        self.assertEqual(options.binary_location, "/opt/chrome-linux64/chrome")
        self.assertIn("--no-sandbox", options.arguments)
        self.assertIn("--disable-dev-shm-usage", options.arguments)

    def test_defaults_leave_binary_unset(self):
        with mock.patch("browser.webdriver.Chrome") as chrome_cls:
            create_driver(self._cfg())
        options = chrome_cls.call_args.kwargs["options"]
        self.assertEqual(options.binary_location, "")
        self.assertIn("--headless=new", options.arguments)
        self.assertNotIn("--no-sandbox", options.arguments)


if __name__ == "__main__":
    unittest.main()
