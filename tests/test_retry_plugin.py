from pytest import mark

pytest_plugins = ["pytester"]


def check_outcome_field(outcomes, field_name, expected_value):
    field_value = outcomes.get(field_name, 0)
    assert field_value == expected_value, (
        f"outcomes.{field_name} has unexpected value. "
        f"Expected '{expected_value}' but got '{field_value}'"
    )


def assert_outcomes(
    result,
    passed=1,
    skipped=0,
    failed=0,
    errors=0,
    xfailed=0,
    xpassed=0,
    retried=0,
):
    outcomes = result.parseoutcomes()
    check_outcome_field(outcomes, "passed", passed)
    check_outcome_field(outcomes, "skipped", skipped)
    check_outcome_field(outcomes, "failed", failed)
    check_outcome_field(outcomes, "errors", errors)
    check_outcome_field(outcomes, "xfailed", xfailed)
    check_outcome_field(outcomes, "xpassed", xpassed)
    check_outcome_field(outcomes, "retried", retried)


def test_no_retry_on_pass(testdir):
    testdir.makepyfile("def test_success(): assert 1 == 1")
    result = testdir.runpytest("--retries", "1")

    assert_outcomes(result)


def test_no_retry_on_fail_without_plugin(testdir):
    testdir.makepyfile("def test_success(): assert False")
    result = testdir.runpytest()

    assert_outcomes(result, passed=0, failed=1, retried=0)


def test_no_retry_on_skip_mark(testdir):
    testdir.makepyfile(
        """
        import pytest
        @pytest.mark.skip(reason="do not run me")
        def test_skip():
            assert 1 == 1
        """
    )
    result = testdir.runpytest("--retries", "1")

    assert_outcomes(result, passed=0, skipped=1)


def test_no_retry_on_skip_call(testdir):
    testdir.makepyfile(
        """
        import pytest
        def test_skip():
            pytest.skip(reason="Don't test me")
        """
    )
    result = testdir.runpytest("--retries", "1")

    assert_outcomes(result, passed=0, skipped=1)


def test_no_retry_on_xfail_mark(testdir):
    testdir.makepyfile(
        """
        import pytest
        @pytest.mark.xfail()
        def test_xfail():
            assert False
        """
    )
    result = testdir.runpytest("--retries", "1")

    assert_outcomes(result, passed=0, xfailed=1)


def test_no_retry_on_xpass(testdir):
    testdir.makepyfile(
        """
        import pytest
        @pytest.mark.xfail()
        def test_xpass():
            assert 1 == 1
        """
    )
    result = testdir.runpytest("--retries", "1")

    assert_outcomes(result, passed=0, xpassed=1)


def test_retry_fails_after_consistent_setup_failure(testdir):
    testdir.makepyfile("def test_pass(): pass")
    testdir.makeconftest(
        """
        def pytest_runtest_setup(item):
            raise Exception("Setup failure")
        """
    )
    result = testdir.runpytest("--retries", "1")

    assert_outcomes(result, passed=0, errors=1, retried=0)


@mark.skip(reason="Not worrying about setup failures for now, maybe later")
def test_retry_passes_after_temporary_setup_failure(testdir):
    testdir.makepyfile("def test_pass(): pass")
    testdir.makeconftest(
        """
        a = []
        def pytest_runtest_setup(item):
            a.append(1)
            if len(a) < 2:
                raise ValueError("Setup failed!")
        """
    )
    result = testdir.runpytest("--retries", "1")

    assert_outcomes(result, passed=1, retried=1)


def test_retry_fails_after_consistent_test_failure(testdir):
    testdir.makepyfile("def test_fail(): assert False")
    result = testdir.runpytest("--retries", "1")

    assert_outcomes(result, passed=0, failed=1, retried=1)


def test_retry_passes_after_temporary_test_failure(testdir):
    testdir.makepyfile(
        """
        a = []
        def test_eventually_passes():
            a.append(1)
            assert len(a) > 1
        """
    )
    result = testdir.runpytest("--retries", "1")

    assert_outcomes(result, passed=1, retried=1)


def test_retry_passes_after_temporary_test_failure_with_flaky_mark(testdir):
    testdir.makepyfile(
        """
        import pytest

        a = []

        @pytest.mark.flaky(retries=2)
        def test_eventually_passes():
            a.append(1)
            assert len(a) > 2
        """
    )
    result = testdir.runpytest()

    assert_outcomes(result, passed=1, retried=1)


def test_retries_if_flaky_mark_is_called_without_options(testdir):
    testdir.makepyfile(
        """
        import pytest

        a = []

        @pytest.mark.flaky()
        def test_eventually_passes():
            a.append(1)
            assert len(a) > 1
        """
    )
    result = testdir.runpytest()

    assert_outcomes(result, passed=1, retried=1)


def test_retry_fails_if_temporary_failures_exceed_retry_limit(testdir):
    testdir.makepyfile(
        """
        a = []
        def test_eventually_passes():
            a.append(1)
            assert len(a) > 3
        """
    )
    result = testdir.runpytest("--retries", "2")

    assert_outcomes(result, passed=0, failed=1, retried=1)


def test_retry_delay_from_mark_between_attempts(testdir):
    testdir.makepyfile(
        """
        import pytest

        a = []

        @pytest.mark.flaky(retries=2, delay=2)
        def test_eventually_passes():
            a.append(1)
            assert len(a) > 2
        """
    )
    result = testdir.runpytest()

    assert_outcomes(result, passed=1, retried=1)
    assert result.duration > 4


def test_retry_delay_from_command_line_between_attempts(testdir):
    testdir.makepyfile(
        """
        import pytest

        a = []

        def test_eventually_passes():
            a.append(1)
            assert len(a) > 2
        """
    )
    result = testdir.runpytest("--retries", "2", "--retry-delay", "2")

    assert_outcomes(result, passed=1, retried=1)
    assert result.duration > 4


def test_passing_outcome_is_available_from_item_stash(testdir):
    testdir.makepyfile("def test_success(): assert 1 == 1")
    testdir.makeconftest(
        """
        import pytest
        from pytest_retry import outcome_key

        @pytest.fixture(autouse=True)
        def report_check(request):
            yield
            assert request.node.stash[outcome_key] == "passed"
        """
    )
    result = testdir.runpytest()

    assert_outcomes(result, passed=1)


def test_failed_outcome_is_available_from_item_stash(testdir):
    testdir.makepyfile("def test_success(): assert 1 == 2")
    testdir.makeconftest(
        """
        import pytest
        from pytest_retry import outcome_key

        @pytest.fixture(autouse=True)
        def report_check(request):
            yield
            assert request.node.stash[outcome_key] == "failed"
        """
    )
    result = testdir.runpytest()

    assert_outcomes(result, passed=0, failed=1)


def test_skipped_outcome_is_available_from_item_stash(testdir):
    testdir.makepyfile(
        """
        import pytest

        @pytest.mark.skip
        def test_success(): assert 1 == 2
        """
    )
    testdir.makeconftest(
        """
        import pytest
        from pytest_retry import outcome_key, attempts_key, duration_key

        def pytest_sessionfinish(session: pytest.Session) -> None:
            for item in session.items:
                assert item.stash[outcome_key] == "skipped"
                assert item.stash[attempts_key] == 0
                assert item.stash[duration_key] < 0.1
        """
    )
    result = testdir.runpytest()

    assert_outcomes(result, passed=0, skipped=1)


def test_duration_is_available_from_item_stash(testdir):
    testdir.makepyfile("""def test_success(): assert 1 == 1""")
    testdir.makeconftest(
        """
        import pytest
        from pytest_retry import duration_key

        def pytest_sessionfinish(session: pytest.Session) -> None:
            for item in session.items:
                assert item.stash[duration_key] > 0
        """
    )
    result = testdir.runpytest()

    assert_outcomes(result, passed=1)


def test_failed_outcome_after_successful_teardown(testdir):
    testdir.makepyfile("def test_success(): assert 1 == 2")
    testdir.makeconftest(
        """
        import pytest
        from pytest_retry import outcome_key

        @pytest.fixture(autouse=True)
        def successful_teardown(request):
            yield
            assert 1 == 1

        def pytest_sessionfinish(session: pytest.Session) -> None:
            for item in session.items:
                assert item.stash[outcome_key] == "failed"
        """
    )
    result = testdir.runpytest()

    assert_outcomes(result, passed=0, failed=1)


def test_failed_outcome_after_unsuccessful_setup(testdir):
    testdir.makepyfile("def test_success(): assert 1 == 1")
    testdir.makeconftest(
        """
        import pytest
        from pytest_retry import outcome_key

        @pytest.fixture(autouse=True)
        def failed_setup(request):
            assert 1 == 2

        def pytest_sessionfinish(session: pytest.Session) -> None:
            for item in session.items:
                assert item.stash[outcome_key] == "failed"
        """
    )
    result = testdir.runpytest()

    assert_outcomes(result, passed=0, errors=1)


def test_failed_outcome_after_unsuccessful_teardown(testdir):
    testdir.makepyfile("def test_success(): assert 1 == 1")
    testdir.makeconftest(
        """
        import pytest
        from pytest_retry import outcome_key

        @pytest.fixture(autouse=True)
        def failed_teardown(request):
            yield
            assert 1 == 2

        def pytest_sessionfinish(session: pytest.Session) -> None:
            for item in session.items:
                assert item.stash[outcome_key] == "failed"
        """
    )
    result = testdir.runpytest()

    assert_outcomes(result, passed=1, errors=1)


def test_attempts_are_always_available_from_item_stash(testdir):
    testdir.makepyfile("def test_success(): assert 1 == 1")
    testdir.makeconftest(
        """
        import pytest
        from pytest_retry import attempts_key

        def pytest_sessionfinish(session: pytest.Session) -> None:
            for item in session.items:
                assert item.stash[attempts_key] == 1
        """
    )
    result = testdir.runpytest()

    assert_outcomes(result, passed=1)


def test_global_filtered_exception_is_retried(testdir):
    testdir.makepyfile(
        """
        a = []
        def test_eventually_passes():
            a.append(1)
            if not len(a) > 1:
                raise AssertionError
        """
    )
    testdir.makeconftest(
        """
        import pytest

        def pytest_set_filtered_exceptions():
            return [AssertionError]

        """
    )
    result = testdir.runpytest("--retries", "1")

    assert_outcomes(result, passed=1, retried=1)


def test_temporary_filtered_exception_fails_when_attempts_exceeded(testdir):
    testdir.makepyfile(
        """
        a = []
        def test_eventually_passes():
            a.append(1)
            if not len(a) > 4:
                raise IndexError
        """
    )
    testdir.makeconftest(
        """
        import pytest

        def pytest_set_filtered_exceptions():
            return [IndexError]

        """
    )
    result = testdir.runpytest("--retries", "3")

    assert_outcomes(result, passed=0, failed=1, retried=1)


def test_temporary_exception_is_not_retried_if_filter_not_matched(testdir):
    testdir.makepyfile(
        """
        a = []
        def test_eventually_passes():
            a.append(1)
            if not len(a) > 1:
                raise ValueError
        """
    )
    testdir.makeconftest(
        """
        import pytest

        def pytest_set_filtered_exceptions():
            return [IndexError]

        """
    )
    result = testdir.runpytest("--retries", "1")

    assert_outcomes(result, passed=0, failed=1, retried=0)


def test_temporary_exception_is_retried_if_not_globally_excluded(testdir):
    testdir.makepyfile(
        """
        a = []
        def test_eventually_passes():
            a.append(1)
            if not len(a) > 1:
                raise ValueError
        """
    )
    testdir.makeconftest(
        """
        import pytest

        def pytest_set_excluded_exceptions():
            return [AssertionError]

        """
    )
    result = testdir.runpytest("--retries", "1")

    assert_outcomes(result, passed=1, retried=1)


def test_temporary_exception_fails_if_not_excluded_and_attempts_exceeded(testdir):
    testdir.makepyfile(
        """
        a = []
        def test_eventually_passes():
            a.append(1)
            if not len(a) > 4:
                raise ValueError
        """
    )
    testdir.makeconftest(
        """
        import pytest

        def pytest_set_excluded_exceptions():
            return [AssertionError]

        """
    )
    result = testdir.runpytest("--retries", "3")

    assert_outcomes(result, passed=0, failed=1, retried=1)


def test_temporary_exception_is_not_retried_if_excluded(testdir):
    testdir.makepyfile(
        """
        a = []
        def test_eventually_passes():
            a.append(1)
            if not len(a) > 1:
                raise ValueError
        """
    )
    testdir.makeconftest(
        """
        import pytest

        def pytest_set_excluded_exceptions():
            return [ValueError]

        """
    )
    result = testdir.runpytest("--retries", "1")

    assert_outcomes(result, passed=1, retried=1)


def test_flaky_mark_exception_filter_param_overrides_global_filter(testdir):
    testdir.makepyfile(
        """
        import pytest

        a = []

        @pytest.mark.flaky(only_on=[IndexError])
        def test_eventually_passes():
            a.append(1)
            if not len(a) > 1:
                raise ValueError
        """
    )
    testdir.makeconftest(
        """
        import pytest

        def pytest_set_excluded_exceptions():
            return [IndexError]

        """
    )
    result = testdir.runpytest("--retries", "1")

    assert_outcomes(result, passed=0, failed=1, retried=0)


def test_attempt_count_is_correct(testdir):
    testdir.makepyfile(
        """
        import pytest

        a = []

        @pytest.mark.flaky(retries=2)
        def test_eventually_passes():
            a.append(1)
            assert len(a) > 2
        """
    )
    testdir.makeconftest(
        """
        import pytest
        from pytest_retry import attempts_key

        def pytest_sessionfinish(session: pytest.Session) -> None:
            for item in session.items:
                assert item.stash[attempts_key] == 3
        """
    )
    result = testdir.runpytest()

    assert_outcomes(result, passed=1, retried=1)


def test_duration_in_overwrite_timings_mode(testdir):
    testdir.makepyfile(
        """
        import pytest
        from time import sleep

        a = []

        @pytest.mark.flaky(retries=2)
        def test_eventually_passes():
            sleep(2 - len(a))
            a.append(1)
            assert len(a) > 1
        """
    )
    testdir.makeconftest(
        """
        import pytest
        from pytest_retry import attempts_key

        def pytest_report_teststatus(report: pytest.TestReport):
            if report.when == "call" and report.outcome != "retried":
                assert report.duration < 2
        """
    )
    result = testdir.runpytest()

    assert_outcomes(result, passed=1, retried=1)


def test_duration_in_cumulative_timings_mode(testdir):
    testdir.makepyfile(
        """
        import pytest
        from time import sleep

        a = []

        def test_eventually_passes():
            sleep(2 - len(a))
            a.append(1)
            assert len(a) > 1
        """
    )
    testdir.makeconftest(
        """
        import pytest
        from pytest_retry import attempts_key

        def pytest_report_teststatus(report: pytest.TestReport):
            if report.when == "call" and report.outcome != "retried":
                assert report.duration > 3
        """
    )
    result = testdir.runpytest("--retries", "2", "--cumulative-timing", "1")

    assert_outcomes(result, passed=1, retried=1)
