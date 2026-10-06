"""Part F's full-suite safety constraint; no PolicyEngine simulations.

This temporary plugin is not a source/test change. It skips a test when its
existing fixture tries to instantiate PolicyEngine, leaving full collection
and all pure, artifact and mocked-runner checks enabled.
"""
import pytest


def pytest_sessionstart(session):
    import policyengine_uk
    def prohibited(*args, **kwargs):
        pytest.skip('Part F: no PolicyEngine simulation runs; synthetic model test not executed')
    policyengine_uk.Simulation.__init__ = prohibited
    policyengine_uk.Microsimulation.__init__ = prohibited
