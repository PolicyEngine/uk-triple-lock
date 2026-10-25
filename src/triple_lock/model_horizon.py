"""Extend the one policyengine-uk parameter builder that stops before the final year, in memory.

policyengine-uk builds several derived series at parameter-load time
(``tax_benefit_system.process_parameter_tree``). Under 2.147.2 (and 2.151.0,
whose builders and parameter processing are byte-identical) every one the
engine relies on reaches fiscal 2039-40 by itself except one:

* ``lag_cpi.add_lagged_cpi`` and ``lag_average_earnings.add_lagged_earnings``
  (through ``lagged_series.add_lagged_parameter``) run to the year after their
  source's last value. The OBR growth series now run to 2073, so these reach
  2074. (2.90.2 stopped lagged CPI at 2029, so benefit rates stopped following
  the path after April 2029.)
* ``create_statutory_uprating_inputs.add_statutory_uprating_inputs`` fills
  September CPI and May-July earnings to the last year of the calendar series
  (2073), and ``create_triple_lock.add_triple_lock`` builds the model's own
  triple lock from them to the year after (2.90.2 stopped it at 2034).
* ``create_economic_assumption_indices`` builds every growth index to 2039, and
  ``utils.parameters.convert_to_fiscal_year_parameters`` converts fiscal years
  2015 to 2040: both cover the final year, 2039-40, whose parameters a
  simulation reads at 1 January 2039.
* ``create_private_pension_uprating.add_private_pension_uprating_factor``
  (min(RPI growth the year before, 5%), which uprates private pension income)
  still covers only the module-level ``YEARS``, 2020 to 2034. After that it
  holds its 2034 value, so private pension income would stop following the
  path's RPI from 2035-36. ``install()`` extends ``YEARS`` to ``END_YEAR``.

A one-off check when porting (built for the central path, every parameter on
five dates a year) found the processed tree identical with and without the
old extensions of the indices, the fiscal-year conversion and the lagged
series on every date to 2039 (they first differ in 2040), and changed from
2036 by extending the private pension uprating. tests/test_model.py checks
the extension changes nothing else to the final year, and that every derived
series follows a path to it. A Scenario cannot
do this: its parameter changes are applied after ``reset_parameters()`` and
before ``process_parameters()``, which rebuilds these series from the builders.

``install()`` first checks the upstream files whose horizons this relies on,
those whose formulas the engine mirrors (gov_balance's tax and spending
lists, engine.fiscal_variables; the State Pension formulas,
engine.actual_law_denominators and the additional State Pension pin), those it
reads State Pension age and type through, and how a Scenario and a reform
reach a simulation, against the versions read here (SHA-256), so a
policyengine-uk upgrade that changes any of them fails here instead of
silently. The trajectory runs then
check, in every year, that the series built on these follow the path (benefit
uprating, a CPI-indexed threshold, employment income, the model's triple lock
from the path's statutory inputs), and record private pension income's growth.
"""

import contextlib
import hashlib
import importlib
import importlib.metadata
from pathlib import Path

END_YEAR = 2042  # the private pension uprating covers at least fiscal year 2041-42

# SHA-256 of the upstream files whose horizons or formulas the engine relies on,
# read for the historical d1727 policyengine-uk 2.153.4 route.
# Retained as history; the binding cut below is audited in docs/d1983-upstream.md.
D1727_UPSTREAM = {
    "policyengine_uk.parameters.gov.economic_assumptions.lag_cpi":
        "73135eebeb353f6f5c6debadde76d3988636c3277ecbd13881ec3fde53114128",
    "policyengine_uk.parameters.gov.economic_assumptions.lag_average_earnings":
        "18ea4ed4763b5d0ddd86f0d6b3365d016514f276ade9133340c10da7368ed252",
    "policyengine_uk.parameters.gov.economic_assumptions.lagged_series":
        "ead387b033f3d5d2a6c6dd41980bb418d1bf39378b6c8601ae9192c532b19917",
    "policyengine_uk.parameters.gov.economic_assumptions.create_statutory_uprating_inputs":
        "d0d1f73c43de6e0d64d08d54ba560e0e2e23a24f6f7ca80d578524bb1462af50",
    "policyengine_uk.parameters.gov.dwp.state_pension.triple_lock.create_triple_lock":
        "f09e1e8c0eb780160bc82cdad6395166157c50a8526d9c1c39cbf9f2d7c8e48d",
    "policyengine_uk.parameters.gov.contrib.create_private_pension_uprating":
        "3507c03c7388ea0cd2c45dd6368a5b4ac390a670dbf6e57567d84c6488b92ae2",
    "policyengine_uk.parameters.gov.economic_assumptions.create_economic_assumption_indices":
        "30a4da9498bff121f2e704884b4716687a4d356cff6d750ba7bfb258dd5ccbad",
    "policyengine_uk.utils.parameters":
        "8ed13881276d1b9a1c72ce8810f9b4fcaba28252c6cfd0761a0c5f2a45ba1793",
    "policyengine_uk.tax_benefit_system":
        "003d176278399cd51d895e0d8184b9d31d451e232d0ee619d08459128fe3e972",
    # Formulas the engine mirrors.
    "policyengine_uk.variables.gov.gov_tax":
        "3d3c151d58a5ede6c7c01dcbdef15012fa24100da40947d5769b156dd31988a9",
    "policyengine_uk.variables.gov.gov_spending":
        "14829a2571a1baa187deab4a6859da1e24815735e318fb837da7e874dbe81e17",
    "policyengine_uk.variables.gov.gov_balance":
        "7cda3e7be35cdd221502809047455430a8f7faaadef48a5871fcfe284624439c",
    "policyengine_uk.variables.input.state_pension":
        "549bb8157bc8275364391210ca098f329d761d6b3288eacd2ff52b21a0d46352",
    "policyengine_uk.variables.gov.dwp.basic_state_pension":
        "477a158655fc1d74d59eb9a97e3fce69870fe7415aed34846f316ecc562ea407",
    "policyengine_uk.variables.gov.dwp.new_state_pension":
        "f5ff9f73cfb267a1fa69e635089e0b6a6518405824c9bc549210aba0050f812e",
    "policyengine_uk.variables.gov.dwp.additional_state_pension":
        "59756afa1279d478bcc94983f27c7c7076e80cfd9c915f5abdb85af1cf07ef5e",
    # What the engine reads State Pension age and type through, and how a Scenario and a reform reach a simulation.
    "policyengine_uk.variables.gov.dwp.state_pension_type":
        "8da2f941fdead378366c11ef1580d3ca405bdd97c0553e921d380a36a1b1e3e9",
    "policyengine_uk.utils.state_pension_age":
        "63fcbd25fdc68585cf6229987951a8798249390835ca413035b2604b48840a8c",
    "policyengine_uk.variables.gov.dwp.state_pension_age":
        "efcf7033fe4a671754e6dd448bd7ed19c9c98a38a94194d8fb2496c9de5f3abf",
    "policyengine_uk.variables.gov.dwp.months_since_state_pension_age":
        "99da2f90986157e6c496ebe93b9991bc5cc759fb437ffafd4a4325bfec5f4979",
    "policyengine_uk.utils.dates":
        "f0da56854b6c7f0a8405162c06747a4a4f98c6b917494e46f5388102076428c6",
    "policyengine_uk.variables.household.demographic.date_of_birth":
        "a0ca5f40993a6e2d6e78006fe61e8489dab26601736dd897646e5a496d4227db",
    # The birthday draw and the State Pension input static ageing mirrors (cohorts.within_year_birth_months,
    # cohorts.birth_dates_from_age, demography.payable_reported).
    "policyengine_uk.variables.household.demographic.months_since_last_birthday":
        "aac44746d7996e6dc721b8ccd4fede455f867732e20d301cc433b25a49ac1212",
    "policyengine_uk.utils.stochastic":
        "582bf5a0b5310bb8e5b5be362135e20425425d71f112b74c2b75e43f3c70f3df",
    "policyengine_uk.variables.gov.dwp.state_pension_reported":
        "dc70cf5c11237f9c70adf0474086502282096c4b28eee75b35dee430d7fd6d6a",
    "policyengine_uk.variables.gov.dwp.is_SP_age":
        "e6ad740b675db92b635f2e34d056175e277aa947ca34e09f7d53631e7bd7b332",
    # The head used by fiscal programmes and the engine's household breakdowns (#2062).
    "policyengine_uk.variables.household.demographic.is_household_head":
        "bfeb22996dea201ee5177be72b2a717a62598db1f4e12e10029f7881554f31a8",
    "policyengine_uk.variables.household.demographic.is_resolved_household_head":
        "4e2583c98cc765bcef0c78b4f61fc02cbaf6c0bcde14b8653f7d14da93580ab5",
    "policyengine_uk.simulation":
        "f7a677923f9358e44a50523e6fc3bc7e17417ed30f3b7557ca1b8d5f625bc105",
    "policyengine_uk.utils.scenario":
        "ecdc5358b553ca56ea7090ab9d64acef5b71b593c61548285cf6c3bf9fcb9d48",
    # Statutory uprating and the #2576 guarantees derived before fiscal conversion.
    "policyengine_uk.parameters.gov.economic_assumptions.create_earnings_uprating":
        "0709ea90289aa981dd6de27e340a455c5c75f9bba46c8860dfc8df846e6aad8b",
    "policyengine_uk.parameters.gov.economic_assumptions.create_september_cpi_uprating":
        "a356e6204091211975009db5b5b4179da7c441a15c92fe21bc554a0501757229",
    "policyengine_uk.parameters.gov.dwp.pension_credit.savings_credit.create_savings_credit_threshold":
        "bda6098aef63c353fbffea9a64b80708ad70c2cc3afb84f662dda3d63d4d42c6",
    "policyengine_uk.parameters.gov.dwp.housing_benefit.allowances.create_pension_age_allowances":
        "244857c3ac6b1d1d1d3bb8c60336a9282226aeab056eab967cdeb81c34291f34",
}

# Metadata that selects the reviewed uprating and derivation rules. Keeping
# these YAML files guarded also catches a rule change without a builder edit.
D1727_UPSTREAM_PARAMETERS = {
    "parameters/gov/benefit_uprating_cpi.yaml":
        "860e8aa55c5456588823cf572027048ab90ab42e2a3c9a2eabce35c6777341b1",
    "parameters/gov/dwp/pension_credit/guarantee_credit/minimum_guarantee.yaml":
        "586508c61dd837f7f860c6c11198fc7b52b4514a083af4f7117a1acfeb89bd0d",
    "parameters/gov/dwp/pension_credit/savings_credit/threshold.yaml":
        "27d3c9cb20d05ee52bf3f717aa8b09330db99b44b699566407cae3b6c598a8ac",
    "parameters/gov/dwp/pension_credit/savings_credit/maximum.yaml":
        "3504c55ccf415d76e8663b567f972439807b3e4cdb89366ea136d2f9afe06dd6",
    "parameters/gov/economic_assumptions/statutory_uprating_inputs/cpi_september.yaml":
        "35fecf09e37ea8c02d4c805d0fc0bea0f0183254e6407b2e9399be0b45bb3e42",
    "parameters/gov/economic_assumptions/statutory_uprating_inputs/awe_total_pay_may_july.yaml":
        "1ea1e805e8adca251dfe1469874ce3129c835e45c1fff1a4351207dd593ef10a",
    "parameters/gov/dwp/housing_benefit/allowances/single/aged.yaml":
        "1f7ba83d6559f4d1eae473498131ad0dc5579cda4db56e572db21d4e652e4cf1",
    "parameters/gov/dwp/housing_benefit/allowances/single/aged_from_cutoff.yaml":
        "57680b6cd750c17a3ab53d99c8fc32f22b96ce5b389dced86fd2df7162fb275a",
    "parameters/gov/dwp/housing_benefit/allowances/couple/aged.yaml":
        "fd423fa6eee72731e369a62be673bcd45807b15aa59c4d8decf4c411e585696e",
    "parameters/gov/dwp/housing_benefit/allowances/couple/aged_from_cutoff.yaml":
        "841cbad73c4f2c676423f1545ee8f1da51c22bd736b0f214296e9dd5633e1d6d",
    "parameters/gov/dwp/housing_benefit/allowances/lone_parent/aged.yaml":
        "dc67325f6cfff721e26771e4a7d285ca449e75d9902578160102b2c1dab34313",
    "parameters/gov/dwp/housing_benefit/allowances/lone_parent/aged_from_cutoff.yaml":
        "7141a92f5006078b9849306df2c76595533e8ec8ad9a1b5ab02df573564b3c44",
}

# Exact wheel source guards for the binding Budget model, 2.147.2.
# Every changed file was read against 2.125.1; see docs/d1983-upstream.md.
UPSTREAM = {
    'policyengine_uk.parameters.gov.economic_assumptions.lag_cpi':
        '73135eebeb353f6f5c6debadde76d3988636c3277ecbd13881ec3fde53114128',
    'policyengine_uk.parameters.gov.economic_assumptions.lag_average_earnings':
        '18ea4ed4763b5d0ddd86f0d6b3365d016514f276ade9133340c10da7368ed252',
    'policyengine_uk.parameters.gov.economic_assumptions.lagged_series':
        'ead387b033f3d5d2a6c6dd41980bb418d1bf39378b6c8601ae9192c532b19917',
    'policyengine_uk.parameters.gov.economic_assumptions.create_statutory_uprating_inputs':
        'd0d1f73c43de6e0d64d08d54ba560e0e2e23a24f6f7ca80d578524bb1462af50',
    'policyengine_uk.parameters.gov.dwp.state_pension.triple_lock.create_triple_lock':
        'f09e1e8c0eb780160bc82cdad6395166157c50a8526d9c1c39cbf9f2d7c8e48d',
    'policyengine_uk.parameters.gov.contrib.create_private_pension_uprating':
        '3507c03c7388ea0cd2c45dd6368a5b4ac390a670dbf6e57567d84c6488b92ae2',
    'policyengine_uk.parameters.gov.economic_assumptions.create_economic_assumption_indices':
        '1fc2852d367db53d35b032606fff1424a9f797e6703c6344a73e75592389cbf9',
    'policyengine_uk.utils.parameters':
        '8ed13881276d1b9a1c72ce8810f9b4fcaba28252c6cfd0761a0c5f2a45ba1793',
    'policyengine_uk.tax_benefit_system':
        '180971d8914639ee9b5103317cf3cf9c7cadde0bd78042c355488de99aa92194',
    'policyengine_uk.variables.gov.gov_tax':
        '7b4b90ed5515315a94a1080c400ed5bf7fcff4e3395d963f8d8fd2ca78ce11b4',
    'policyengine_uk.variables.gov.gov_spending':
        '7e3efd4a02f0d3559ba325681ea2b3e993ff1859a65ec06f5fba7ae4edc577a9',
    'policyengine_uk.variables.gov.gov_balance':
        '7cda3e7be35cdd221502809047455430a8f7faaadef48a5871fcfe284624439c',
    'policyengine_uk.variables.input.state_pension':
        '549bb8157bc8275364391210ca098f329d761d6b3288eacd2ff52b21a0d46352',
    'policyengine_uk.variables.gov.dwp.basic_state_pension':
        '477a158655fc1d74d59eb9a97e3fce69870fe7415aed34846f316ecc562ea407',
    'policyengine_uk.variables.gov.dwp.new_state_pension':
        'f5ff9f73cfb267a1fa69e635089e0b6a6518405824c9bc549210aba0050f812e',
    'policyengine_uk.variables.gov.dwp.additional_state_pension':
        '59756afa1279d478bcc94983f27c7c7076e80cfd9c915f5abdb85af1cf07ef5e',
    'policyengine_uk.variables.gov.dwp.state_pension_type':
        '8da2f941fdead378366c11ef1580d3ca405bdd97c0553e921d380a36a1b1e3e9',
    'policyengine_uk.utils.state_pension_age':
        '63fcbd25fdc68585cf6229987951a8798249390835ca413035b2604b48840a8c',
    'policyengine_uk.variables.gov.dwp.state_pension_age':
        'efcf7033fe4a671754e6dd448bd7ed19c9c98a38a94194d8fb2496c9de5f3abf',
    'policyengine_uk.variables.gov.dwp.months_since_state_pension_age':
        '99da2f90986157e6c496ebe93b9991bc5cc759fb437ffafd4a4325bfec5f4979',
    'policyengine_uk.utils.dates':
        'f0da56854b6c7f0a8405162c06747a4a4f98c6b917494e46f5388102076428c6',
    'policyengine_uk.variables.household.demographic.date_of_birth':
        'a0ca5f40993a6e2d6e78006fe61e8489dab26601736dd897646e5a496d4227db',
    'policyengine_uk.variables.household.demographic.months_since_last_birthday':
        'aac44746d7996e6dc721b8ccd4fede455f867732e20d301cc433b25a49ac1212',
    'policyengine_uk.utils.stochastic':
        '582bf5a0b5310bb8e5b5be362135e20425425d71f112b74c2b75e43f3c70f3df',
    'policyengine_uk.variables.gov.dwp.state_pension_reported':
        'dc70cf5c11237f9c70adf0474086502282096c4b28eee75b35dee430d7fd6d6a',
    'policyengine_uk.variables.gov.dwp.is_SP_age':
        'e6ad740b675db92b635f2e34d056175e277aa947ca34e09f7d53631e7bd7b332',
    'policyengine_uk.variables.household.demographic.is_household_head':
        'bfeb22996dea201ee5177be72b2a717a62598db1f4e12e10029f7881554f31a8',
    'policyengine_uk.variables.household.demographic.is_resolved_household_head':
        '4e2583c98cc765bcef0c78b4f61fc02cbaf6c0bcde14b8653f7d14da93580ab5',
    'policyengine_uk.simulation':
        '8b8d17e6db0c3556a2d28564582e9fb622925753cd1bdb1c4a7d4ca05de6d1bf',
    'policyengine_uk.utils.scenario':
        'ecdc5358b553ca56ea7090ab9d64acef5b71b593c61548285cf6c3bf9fcb9d48',
    'policyengine_uk.parameters.gov.economic_assumptions.create_september_cpi_uprating':
        'a356e6204091211975009db5b5b4179da7c441a15c92fe21bc554a0501757229',
}

UPSTREAM_PARAMETERS = {
    'parameters/gov/benefit_uprating_cpi.yaml':
        'fbbd09cc0472ef62b568e8c77446d24bcf2ceb0216d261d40a1d0ec5d1fc0b4e',
    'parameters/gov/dwp/pension_credit/guarantee_credit/minimum_guarantee.yaml':
        '51c303376c0c248b262846b50e4224b1cbd351a6f7b18740b4340982f35d494a',
    'parameters/gov/dwp/pension_credit/savings_credit/threshold.yaml':
        '1e134a13c39e78c1cdf1ace6193de11ad95d0d5511062917ce6d117b8e0db085',
    'parameters/gov/economic_assumptions/statutory_uprating_inputs/cpi_september.yaml':
        '05b09fbb5221da8c02f3cdad51809d8278112217624d340508af00426f07cadc',
    'parameters/gov/economic_assumptions/statutory_uprating_inputs/awe_total_pay_may_july.yaml':
        '43dac776f382c79dcee8c7e5a94a139ab3636976e420bed42cd66bc1b0e104f8',
    'parameters/gov/dwp/housing_benefit/allowances/single/aged.yaml':
        '20ea2a642b610b6d6221f6a0126841f8bf48bd22bd86867ad10e45241ab38f29',
    'parameters/gov/dwp/housing_benefit/allowances/single/aged_from_cutoff.yaml':
        '51bb8072097e1996528e7ddd0261b5cc287f87f71eed4c8d544e5c52316c0d9e',
    'parameters/gov/dwp/housing_benefit/allowances/couple/aged.yaml':
        '4e1f0f491678a54944237d844fff04f34621250243038ac0f6ba5ee850f88953',
    'parameters/gov/dwp/housing_benefit/allowances/couple/aged_from_cutoff.yaml':
        'ac2573ed6948c8ec866e0aeb019c0e93fed2459deb6e491d0bc161c3f915038b',
    'parameters/gov/dwp/housing_benefit/allowances/lone_parent/aged.yaml':
        '783fef5735740612446e43d755fe59021d36213cf929776a026f175617629624',
    'parameters/gov/dwp/housing_benefit/allowances/lone_parent/aged_from_cutoff.yaml':
        '8eea06e267c1e50cb81a4609eed5de70cca6c152a80eadab4a4dc1ac169047ae',
}

UPSTREAM_ABSENT = (
    "parameters/gov/economic_assumptions/create_earnings_uprating.py",
    "parameters/gov/dwp/pension_credit/savings_credit/create_savings_credit_threshold.py",
    "parameters/gov/dwp/housing_benefit/allowances/create_pension_age_allowances.py",
    "parameters/gov/dwp/pension_credit/savings_credit/maximum.yaml",
    "variables/gov/dwp/state_pension_age_addition.py",
)

# Exact wheel source guards for policyengine-uk 2.151.0, the model of d2011's recommended Budget pair
# (microcosm#1396). Only the files named here differ from 2.147.2, and each was read in full against it:
# see docs/d2011-upstream.md. The 2.147.2 absence guards apply too (#2576 and #2340 are not in it).
UPSTREAM_2151 = {
    **UPSTREAM,
    'policyengine_uk.variables.gov.gov_tax':
        '3d3c151d58a5ede6c7c01dcbdef15012fa24100da40947d5769b156dd31988a9',
    'policyengine_uk.variables.gov.gov_spending':
        '14829a2571a1baa187deab4a6859da1e24815735e318fb837da7e874dbe81e17',
    'policyengine_uk.simulation':
        '0aadac70bd31d62fb23fbb81363ffecea5aac6ca98ac4a0d6bf391727204ea71',
}

UPSTREAM_2151_PARAMETERS = {
    **UPSTREAM_PARAMETERS,
    'parameters/gov/benefit_uprating_cpi.yaml':
        '860e8aa55c5456588823cf572027048ab90ab42e2a3c9a2eabce35c6777341b1',
    'parameters/gov/dwp/pension_credit/guarantee_credit/minimum_guarantee.yaml':
        'a0dec724311b165bd5cc060a1cbcccd6953b5ac6f5fb18bd8ed1690c5df45b8d',
    'parameters/gov/dwp/pension_credit/savings_credit/threshold.yaml':
        'efafcca3b8b63181cf233ae67755382c774b3b4b626855e776393c8da801b5fd',
    'parameters/gov/economic_assumptions/statutory_uprating_inputs/cpi_september.yaml':
        '35fecf09e37ea8c02d4c805d0fc0bea0f0183254e6407b2e9399be0b45bb3e42',
    'parameters/gov/economic_assumptions/statutory_uprating_inputs/awe_total_pay_may_july.yaml':
        '1ea1e805e8adca251dfe1469874ce3129c835e45c1fff1a4351207dd593ef10a',
    'parameters/gov/dwp/housing_benefit/allowances/single/aged.yaml':
        '22a9275e8c9e2a0b2f029ff91c0614e3bbcaea8a272d18b14d9bcdc1f922ef69',
    'parameters/gov/dwp/housing_benefit/allowances/single/aged_from_cutoff.yaml':
        '5d1f60d3ec20e8f0bcae0720fc7f6195055ae21613da6b25f344089df13089df',
    'parameters/gov/dwp/housing_benefit/allowances/couple/aged.yaml':
        '501227fbe44764ac4ed3783e69a0edf44df7f2ffa6778055c2ef678b53d23a89',
    'parameters/gov/dwp/housing_benefit/allowances/couple/aged_from_cutoff.yaml':
        '9f10e1f2f8f93701a47e9976ebb51f37c68d2800f8518098721a687e515670bc',
    'parameters/gov/dwp/housing_benefit/allowances/lone_parent/aged.yaml':
        '57237318c506ec19d14c31f42128263331356ca9430412df443405af91465c6d',
    'parameters/gov/dwp/housing_benefit/allowances/lone_parent/aged_from_cutoff.yaml':
        'd2e737038eca2b338e96fc9b230c0e133a304db61c75175c64172b2f131af0c3',
}

# Exact guards retained for the committed pre-Budget bundle while ledger
# qualification is pending. Neither version admits the other version's bytes.
LEGACY_UPSTREAM = {
    "policyengine_uk.parameters.gov.economic_assumptions.lag_cpi":
        "73135eebeb353f6f5c6debadde76d3988636c3277ecbd13881ec3fde53114128",
    "policyengine_uk.parameters.gov.economic_assumptions.lag_average_earnings":
        "18ea4ed4763b5d0ddd86f0d6b3365d016514f276ade9133340c10da7368ed252",
    "policyengine_uk.parameters.gov.economic_assumptions.lagged_series":
        "ead387b033f3d5d2a6c6dd41980bb418d1bf39378b6c8601ae9192c532b19917",
    "policyengine_uk.parameters.gov.economic_assumptions.create_statutory_uprating_inputs":
        "e8e745b6d9a36d73d529b558df33ad6b2936fbd880279bb97961d9e8b405360a",
    "policyengine_uk.parameters.gov.dwp.state_pension.triple_lock.create_triple_lock":
        "33473e3652ed22b6bd7f90e2e9649fafecad86ac1aec2bbec9181613d4439f30",
    "policyengine_uk.parameters.gov.contrib.create_private_pension_uprating":
        "3507c03c7388ea0cd2c45dd6368a5b4ac390a670dbf6e57567d84c6488b92ae2",
    "policyengine_uk.parameters.gov.economic_assumptions.create_economic_assumption_indices":
        "7ad33ae7b0e6d8fa12ac7149aa8a33b2b01024208fc5538f5cae39a0bdf89244",
    "policyengine_uk.utils.parameters":
        "a8b40d995666e3658e836bba2d0304478d1a9ae3a29429c82105ba9b4738383a",
    "policyengine_uk.tax_benefit_system":
        "e9ac5e7ac02fcf303ed51356a1ab133e034e71117385e1a663a099d5ecf9183d",
    # Formulas the engine mirrors.
    "policyengine_uk.variables.gov.gov_tax":
        "7b4b90ed5515315a94a1080c400ed5bf7fcff4e3395d963f8d8fd2ca78ce11b4",
    "policyengine_uk.variables.gov.gov_spending":
        "1f57caad0a12f33bb9916437f18a220177f83c4c2ebfbedea20ad25e6fe0173e",
    "policyengine_uk.variables.gov.gov_balance":
        "7cda3e7be35cdd221502809047455430a8f7faaadef48a5871fcfe284624439c",
    "policyengine_uk.variables.input.state_pension":
        "549bb8157bc8275364391210ca098f329d761d6b3288eacd2ff52b21a0d46352",
    "policyengine_uk.variables.gov.dwp.basic_state_pension":
        "88a7799f2868b84f33b78157d6717f16abf9246cdef7d0c5e27f4f183e8c937d",
    "policyengine_uk.variables.gov.dwp.new_state_pension":
        "acdffc776e9aca1ff67533bbdc6760302fefce08738d4544508c4703cd8acabf",
    "policyengine_uk.variables.gov.dwp.additional_state_pension":
        "2b8c694eb4e58efde45dec01bbfedd682fb0e26458d72f9ec97cf6f53e4f8c9d",
    # What the engine reads State Pension age and type through, and how a Scenario and a reform reach a simulation.
    "policyengine_uk.variables.gov.dwp.state_pension_type":
        "8da2f941fdead378366c11ef1580d3ca405bdd97c0553e921d380a36a1b1e3e9",
    "policyengine_uk.utils.state_pension_age":
        "63fcbd25fdc68585cf6229987951a8798249390835ca413035b2604b48840a8c",
    "policyengine_uk.variables.gov.dwp.state_pension_age":
        "efcf7033fe4a671754e6dd448bd7ed19c9c98a38a94194d8fb2496c9de5f3abf",
    "policyengine_uk.variables.gov.dwp.months_since_state_pension_age":
        "99da2f90986157e6c496ebe93b9991bc5cc759fb437ffafd4a4325bfec5f4979",
    "policyengine_uk.utils.dates":
        "fb670783db97daa01a0599c49f3aff4103ff8121168076be3836812e79b99d14",
    "policyengine_uk.variables.household.demographic.date_of_birth":
        "a0ca5f40993a6e2d6e78006fe61e8489dab26601736dd897646e5a496d4227db",
    # The birthday draw and the State Pension input static ageing mirrors (cohorts.within_year_birth_months,
    # cohorts.birth_dates_from_age, demography.payable_reported).
    "policyengine_uk.variables.household.demographic.months_since_last_birthday":
        "93081c94f2b1209761af43fe7e92f5b0e52d62388431827b1a30d1100c9acb98",
    "policyengine_uk.utils.stochastic":
        "582bf5a0b5310bb8e5b5be362135e20425425d71f112b74c2b75e43f3c70f3df",
    "policyengine_uk.variables.gov.dwp.state_pension_reported":
        "dc70cf5c11237f9c70adf0474086502282096c4b28eee75b35dee430d7fd6d6a",
    "policyengine_uk.variables.gov.dwp.is_SP_age":
        "e6ad740b675db92b635f2e34d056175e277aa947ca34e09f7d53631e7bd7b332",
    # The head used by fiscal programmes and the engine's household breakdowns (#2062).
    "policyengine_uk.variables.household.demographic.is_household_head":
        "bfeb22996dea201ee5177be72b2a717a62598db1f4e12e10029f7881554f31a8",
    "policyengine_uk.variables.household.demographic.is_resolved_household_head":
        "4e2583c98cc765bcef0c78b4f61fc02cbaf6c0bcde14b8653f7d14da93580ab5",
    "policyengine_uk.simulation":
        "77691dce9d172a1486f89352e5cb080b9636f74711fba57423fad8be04b4276b",
    "policyengine_uk.utils.scenario":
        "a5a3f688891177b2895fd93e5f016a0bcad14ba6b9da5db52f889f0ea0a117d4",
}


class UpstreamChanged(RuntimeError):
    """policyengine-uk's builders differ from the versions read here."""


def check_upstream():
    """Raise UpstreamChanged unless every upstream file relied on is byte-identical to the recorded version."""
    version = importlib.metadata.version("policyengine-uk")
    if version == "2.147.2":
        modules, parameter_files = UPSTREAM, UPSTREAM_PARAMETERS
    elif version == "2.151.0":
        modules, parameter_files = UPSTREAM_2151, UPSTREAM_2151_PARAMETERS
    elif version == "2.153.4":
        modules, parameter_files = D1727_UPSTREAM, D1727_UPSTREAM_PARAMETERS
    elif version == "2.125.1":
        modules, parameter_files = LEGACY_UPSTREAM, {}
    else:
        raise UpstreamChanged(f"policyengine-uk {version} has no reviewed source guards; "
                              "supported exact versions are 2.125.1, 2.147.2, 2.151.0 and historical 2.153.4")
    changed = []
    for module, expected in modules.items():
        path = Path(importlib.import_module(module).__file__)
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            changed.append(module)
    root = Path(importlib.import_module("policyengine_uk").__file__).parent
    for relative, expected in parameter_files.items():
        if hashlib.sha256((root / relative).read_bytes()).hexdigest() != expected:
            changed.append(relative)
    if version in ("2.147.2", "2.151.0"):
        changed.extend(relative for relative in UPSTREAM_ABSENT if (root / relative).exists())
    if changed:
        raise UpstreamChanged(f"policyengine-uk changed {changed}; re-read them and update model_horizon.py")


def extensions(end_year=END_YEAR):
    """What ``install`` extends: the series' upstream first and last years, and the new last year."""
    return {
        "upstream": f"policyengine-uk {importlib.metadata.version('policyengine-uk')}",
        "end_year": end_year,
        "upstream_years": {"private_pension_index": [2020, 2034]},
    }


def install(end_year=END_YEAR):
    """Extend the private pension uprating to ``end_year`` for every system built from here on; returns what changed."""
    import policyengine_uk.tax_benefit_system as tbs
    from policyengine_uk.parameters.gov.contrib import create_private_pension_uprating

    check_upstream()
    # add_private_pension_uprating_factor reads this module-level list when called.
    create_private_pension_uprating.YEARS = list(range(2020, end_year + 1))
    # Systems built from here on process with the list above. In 2.147.2 and 2.151.0,
    # a Scenario may also read a memoised rebuild, whose key has no builder
    # horizon. Discard every tree/timeline built with the old YEARS list.
    tbs._processed_parameters_cache = None
    for name in ("_statutory_parameters_cache", "_projected_timelines_cache"):
        if hasattr(tbs, name):
            setattr(tbs, name, None)
    if hasattr(tbs, "_rebuilt_parameters_cache"):
        tbs._rebuilt_parameters_cache = type(tbs._rebuilt_parameters_cache)()
    return extensions(end_year)


@contextlib.contextmanager
def installed(end_year=END_YEAR):
    """``install()`` for the duration of a block, then restore the upstream list (for tests)."""
    import policyengine_uk.tax_benefit_system as tbs
    from policyengine_uk.parameters.gov.contrib import create_private_pension_uprating

    years = create_private_pension_uprating.YEARS
    caches = {name: getattr(tbs, name) for name in (
        "_processed_parameters_cache", "_statutory_parameters_cache",
        "_projected_timelines_cache", "_rebuilt_parameters_cache") if hasattr(tbs, name)}
    try:
        yield install(end_year)
    finally:
        create_private_pension_uprating.YEARS = years
        for name, value in caches.items():
            setattr(tbs, name, value)
