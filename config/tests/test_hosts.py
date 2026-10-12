from config.hosts import vercel_hosts


def test_vercel_hosts_collects_set_values_in_order():
    environ = {
        "VERCEL_URL": "scholarsync-abc.vercel.app",
        "VERCEL_BRANCH_URL": "",
        "VERCEL_PROJECT_PRODUCTION_URL": "scholarsync.vercel.app",
    }
    assert vercel_hosts(environ) == ["scholarsync-abc.vercel.app", "scholarsync.vercel.app"]


def test_vercel_hosts_empty_outside_vercel():
    assert vercel_hosts({}) == []
