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
    guards = {"2.147.2": model_horizon.UPSTREAM_PARAMETERS, "2.151.0": model_horizon.UPSTREAM_2151_PARAMETERS,
              "2.153.4": model_horizon.D1727_UPSTREAM_PARAMETERS}
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


def test_the_2151_guards_differ_from_the_2147_guards_only_where_its_wheel_does():
    """Each 2.151.0 guard names that wheel's bytes; a guard left at the 2.147.2 value is a file 2.151.0 did not
    change. Both lists were read file by file (docs/d2011-upstream.md)."""
    changed = {name for name, digest in model_horizon.UPSTREAM_2151.items()
               if model_horizon.UPSTREAM[name] != digest}
    changed_parameters = {path for path, digest in model_horizon.UPSTREAM_2151_PARAMETERS.items()
                          if model_horizon.UPSTREAM_PARAMETERS[path] != digest}
    assert set(model_horizon.UPSTREAM_2151) == set(model_horizon.UPSTREAM)
    assert set(model_horizon.UPSTREAM_2151_PARAMETERS) == set(model_horizon.UPSTREAM_PARAMETERS)
    assert changed == {"policyengine_uk.variables.gov.gov_tax", "policyengine_uk.variables.gov.gov_spending",
                       "policyengine_uk.simulation"}
    assert changed_parameters == set(model_horizon.UPSTREAM_PARAMETERS)


@pytest.mark.parametrize("path", model_horizon.UPSTREAM_ABSENT)
def test_a_2151_install_with_a_linked_builder_or_the_age_addition_is_refused(monkeypatch, tmp_path, path):
    """#2576's builders, the Savings Credit maximum and #2340's age addition are absent from 2.151.0 too."""
    version = model_horizon.importlib.metadata.version("policyengine-uk")
    if version != "2.151.0":
        pytest.skip(f"policyengine-uk {version} is not 2.151.0")
    root = model_horizon.Path(model_horizon.importlib.import_module("policyengine_uk").__file__).parent
    real_exists = model_horizon.Path.exists
    monkeypatch.setattr(model_horizon.Path, "exists",
                        lambda self: str(self) == str(root / path) or real_exists(self))
    with pytest.raises(model_horizon.UpstreamChanged, match=path.split("/")[-1]):
        model_horizon.check_upstream()
