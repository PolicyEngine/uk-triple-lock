"""The assumptions strip explains an automatic C2 fallback from its provenance."""
import pytest
from triple_lock import pipeline


@pytest.mark.parametrize('automatic', [False, True])
def test_scenarios_only_assumptions_use_the_recorded_omission_reason(monkeypatch, automatic):
    monkeypatch.setattr(pipeline, '_population_item', lambda result: {'key': 'population'})
    reason = 'Original primary failed C2 terminal coverage; automatic d955(a) scenario-only fallback.'
    ruling = {'decision': 'd955', 'ruling': 'a'}
    if automatic:
        ruling.update(requested_ruling='c', effective_ruling='a', fallback_reason=reason)
    block = pipeline.assumptions({'uncertainty_ruling': ruling})
    assert [item['key'] for item in block] == ['population', 'paths']
    assert block[1]['title'] == 'Scenario envelope'
    assert block[1]['facts']['uncertainty_ruling'] == ruling
    assert 'Mean-path variants are scenarios, not probability claims.' in block[1]['text']
    if automatic:
        assert block[1]['text'].startswith(reason)
    else:
        assert block[1]['text'].startswith('The recorded d955 ruling omits an expected value.')


def test_automatic_fallback_cannot_publish_an_assumption_without_its_reason(monkeypatch):
    monkeypatch.setattr(pipeline, '_population_item', lambda result: {'key': 'population'})
    with pytest.raises(pipeline.MissingFigure, match='fallback_reason'):
        pipeline.assumptions({'uncertainty_ruling': {'requested_ruling': 'c', 'effective_ruling': 'a'}})
