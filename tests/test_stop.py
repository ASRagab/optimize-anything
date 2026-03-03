from optimize_anything.stop import plateau_stop_callback


class DummyState:
    def __init__(self, scores):
        self.program_full_scores_val_set = scores


def test_plateau_callback_triggers_after_flat_window():
    stopper = plateau_stop_callback(window=3, threshold=0.001)
    assert stopper(DummyState([0.50])) is False
    assert stopper(DummyState([0.50])) is False
    assert stopper(DummyState([0.50])) is False
    assert stopper(DummyState([0.50])) is True


def test_plateau_callback_does_not_trigger_when_improving():
    stopper = plateau_stop_callback(window=3, threshold=0.001)
    assert stopper(DummyState([0.50])) is False
    assert stopper(DummyState([0.51])) is False
    assert stopper(DummyState([0.52])) is False
    assert stopper(DummyState([0.53])) is False
