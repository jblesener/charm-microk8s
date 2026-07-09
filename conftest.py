#
# Copyright 2026 Canonical, Ltd.
#


def pytest_addoption(parser):
    parser.addoption("--model", action="store", default=None, help="Existing Juju model to use")
