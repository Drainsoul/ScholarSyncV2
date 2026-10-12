import build


def test_steps_order():
    assert build.steps("npm", "py") == [
        ["npm", "--prefix", "frontend", "ci"],
        ["npm", "--prefix", "frontend", "run", "build"],
        ["py", "manage.py", "collectstatic", "--noinput"],
        ["py", "manage.py", "migrate", "--noinput"],
        ["py", "manage.py", "createcachetable"],
    ]


def test_migration_env_prefers_unpooled_url():
    env = build.migration_env(
        {"DATABASE_URL": "postgres://pooled", "DATABASE_URL_UNPOOLED": "postgres://direct"}
    )
    assert env["DATABASE_URL"] == "postgres://direct"


def test_migration_env_falls_back_to_pooled_url():
    env = build.migration_env({"DATABASE_URL": "postgres://pooled", "DATABASE_URL_UNPOOLED": ""})
    assert env["DATABASE_URL"] == "postgres://pooled"
