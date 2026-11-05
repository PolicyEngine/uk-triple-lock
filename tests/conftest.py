"""Property tests fail on what they find, never on how long a loaded host took to generate inputs."""

from hypothesis import HealthCheck, settings

settings.register_profile("no_wall_clock", deadline=None, suppress_health_check=[HealthCheck.too_slow])
settings.load_profile("no_wall_clock")
