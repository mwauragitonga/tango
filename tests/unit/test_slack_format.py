from tagopen.slack_format import strip_reply_artifacts, to_slack_mrkdwn


def test_strip_agent_prefix():
    assert strip_reply_artifacts("[1784572185.10294 @agent] hello") == "hello"


def test_bold_and_strike():
    assert to_slack_mrkdwn("**Redis** and ~~old~~") == "*Redis* and ~old~"


def test_no_double_star_left():
    out = to_slack_mrkdwn("[ts @agent] **PHP** framework")
    assert "**" not in out
    assert out == "*PHP* framework"
