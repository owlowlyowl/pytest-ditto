import datetime

import ditto


@ditto.pickle
def test_schedule(snapshot):
    """The README example: a value JSON can't hold matches its pickle snapshot."""
    schedule = {"days": {"mon", "wed"}, "start": datetime.time(9, 30)}
    assert snapshot(schedule, key="schedule") == schedule
