#!/usr/bin/env python3

import pytest


# 1. Stash marks on report object during test execution
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()

    reqs = [m.args[0] for m in item.iter_markers("requirement") if m.args]
    report.requirement = "<br>".join(reqs)


# 2. Add "Marks" column header
def pytest_html_results_table_header(cells):
    cells.insert(2, "<th>Marks</th>")


# 3. Inject mark data per row
def pytest_html_results_table_row(report, cells):
    cells.insert(2, f"<td>{getattr(report, 'requirement', '')}</td>")


@pytest.hookimpl(optionalhook=True)
def pytest_json_runtest_metadata(item, call):
    if call.when != "call":
        return {}
    reqs = [m.args[0] for m in item.iter_markers("requirement") if m.args]
    return {"requirements": reqs}
