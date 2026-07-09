"""Testes do fluxo de login com driver falso."""
import unittest
from types import SimpleNamespace
from unittest import mock

from selenium.common.exceptions import TimeoutException

from login import LoginError, is_logged_in, is_login_page, login

SELECTORS = {
    "login_username": ("#user",),
    "login_password": ("#pass",),
    "login_submit": ("#submit",),
    "login_form": ("form.login",),
    "logged_in_marker": (".user-menu",),
}


def _config():
    return SimpleNamespace(
        credentials=SimpleNamespace(username="piloto", password="senha"),
        selenium=SimpleNamespace(
            base_url="https://saga.example.com/login", element_timeout_seconds=1
        ),
        selectors=SELECTORS,
    )


class FakeField:
    def __init__(self):
        self.sent = []
        self.cleared = False
        self.clicked = False

    def clear(self):
        self.cleared = True

    def send_keys(self, value):
        self.sent.append(value)

    def click(self):
        self.clicked = True

    def is_displayed(self):
        return True


class FakeDriver:
    def __init__(self, elements_by_selector=None):
        self.elements_by_selector = elements_by_selector or {}
        self.visited = []

    def get(self, url):
        self.visited.append(url)

    def find_elements(self, by, selector):
        return self.elements_by_selector.get(selector, [])


class DetectionTest(unittest.TestCase):
    def test_is_login_page(self):
        driver = FakeDriver({"form.login": [FakeField()]})
        self.assertTrue(is_login_page(driver, SELECTORS))
        self.assertFalse(is_login_page(FakeDriver(), SELECTORS))

    def test_is_logged_in(self):
        driver = FakeDriver({".user-menu": [FakeField()]})
        self.assertTrue(is_logged_in(driver, SELECTORS))
        self.assertFalse(is_logged_in(FakeDriver(), SELECTORS))


class LoginFlowTest(unittest.TestCase):
    def test_session_reuse_skips_form(self):
        driver = FakeDriver({".user-menu": [FakeField()]})
        with mock.patch("login.wait_for_any_visible") as wait:
            login(driver, _config())
        wait.assert_not_called()
        self.assertEqual(driver.visited, ["https://saga.example.com/login"])

    def test_full_login_fills_and_submits(self):
        driver = FakeDriver({"form.login": [FakeField()]})
        user_field, pass_field, submit = FakeField(), FakeField(), FakeField()
        marker = FakeField()

        def fake_wait(drv, selectors, timeout):
            return {
                ("#user",): user_field,
                ("#pass",): pass_field,
                ("#submit",): submit,
                (".user-menu",): marker,
            }[tuple(selectors)]

        with mock.patch("login.wait_for_any_visible", side_effect=fake_wait):
            login(driver, _config())
        self.assertEqual(user_field.sent, ["piloto"])
        self.assertEqual(pass_field.sent, ["senha"])
        self.assertTrue(user_field.cleared)
        self.assertTrue(submit.clicked)

    def test_login_error_when_marker_never_appears(self):
        driver = FakeDriver({"form.login": [FakeField()]})
        field = FakeField()

        def fake_wait(drv, selectors, timeout):
            if tuple(selectors) == (".user-menu",):
                raise TimeoutException("timeout")
            return field

        with mock.patch("login.wait_for_any_visible", side_effect=fake_wait):
            with self.assertRaises(LoginError):
                login(driver, _config())


if __name__ == "__main__":
    unittest.main()
