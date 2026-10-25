"""The horizon extension cannot reuse a tree built with the old horizon."""

from collections import OrderedDict

import pytest

pytest.importorskip("policyengine_uk")
from policyengine_uk import tax_benefit_system as tbs
from policyengine_uk.parameters.gov.contrib import create_private_pension_uprating

from triple_lock import model_horizon


def test_installed_invalidates_and_restores_every_builder_cache(monkeypatch):
    names = ("_processed_parameters_cache", "_statutory_parameters_cache",
             "_projected_timelines_cache", "_rebuilt_parameters_cache")
    names = tuple(name for name in names if hasattr(tbs, name))
    previous = {name: object() for name in names}
    if "_rebuilt_parameters_cache" in names:
        previous["_rebuilt_parameters_cache"] = OrderedDict([("prior-scenario", object())])
    for name, value in previous.items():
        monkeypatch.setattr(tbs, name, value)
    old_years = create_private_pension_uprating.YEARS
    with model_horizon.installed():
        assert all(getattr(tbs, name) is None for name in names if name != "_rebuilt_parameters_cache")
        if "_rebuilt_parameters_cache" in names:
            assert tbs._rebuilt_parameters_cache == OrderedDict()
            assert tbs._rebuilt_parameters_cache is not previous["_rebuilt_parameters_cache"]
        assert max(create_private_pension_uprating.YEARS) == model_horizon.END_YEAR
    assert create_private_pension_uprating.YEARS is old_years
    assert all(getattr(tbs, name) is value for name, value in previous.items())


def test_uprating_metadata_changes_are_refused(monkeypatch):
    """The September CPI YAML guard, in the map check_upstream reads for the installed cut."""
    guards = {"2.147.2": model_horizon.UPSTREAM_PARAMETERS, "2.153.4": model_horizon.D1727_UPSTREAM_PARAMETERS}
    version = model_horizon.importlib.metadata.version("policyengine-uk")
    if version not in guards:
        pytest.skip(f"policyengine-uk {version} has no September CPI YAML guard")
    path = "parameters/gov/benefit_uprating_cpi.yaml"
    assert path in guards[version]
    monkeypatch.setitem(guards[version], path, "0" * 64)
    with pytest.raises(model_horizon.UpstreamChanged, match="benefit_uprating_cpi.yaml"):
        model_horizon.check_upstream()


def test_unreviewed_versions_are_refused_before_loading_sources(monkeypatch):
    monkeypatch.setattr(model_horizon.importlib.metadata, "version", lambda _: "2.153.5")
    with pytest.raises(model_horizon.UpstreamChanged, match="no reviewed source guards"):
        model_horizon.check_upstream()
