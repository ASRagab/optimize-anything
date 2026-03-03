from optimize_anything.stop import plateau_stop_callback


class DummyState:
    """Minimal state shim matching GEPAState score surface."""

    def __init__(self, per_program_scores):
        self.prog_candidate_val_subscores = [
            {idx: score} for idx, score in enumerate(per_program_scores)
        ]

    @property
    def program_full_scores_val_set(self):
        return [
            sum(scores.values()) / len(scores)
            for scores in self.prog_candidate_val_subscores
        ]


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
