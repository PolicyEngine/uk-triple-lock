# Calibration anchor and certified-input bridge

> **Integration (part D).** The anchor is now part of each dataset's registry entry (`datasets.ageing_anchor`: 2025 for Enhanced FRS 1.56.16 and 1.57.4, read from `frs_release.py` at each tag; Microcosm has no published calibration year, so its anchor is 2024, the first year the ONS projection covers). The rake keeps the dataset's own weights in the anchor year and every year before it (`demography.annual_weights`). The level difference described below, runtime 2025 weights = calibrated weights × 1.0072 × 1.027 / 1.039 = 0.9956, is reported upstream as policyengine-uk-data#538. Re-checked on policyengine-uk 2.120.0: every 2025 weight is its 2024 weight × 1.0072.

The pilot uses **2025**, the calibration year configured in the exact source release for its certified Enhanced FRS. It anchors to the runtime's native 2025 weights. Those weights do not restore the builder's original calibrated weights, so preserved Housing Benefit and Pension Credit calibration remains an acceptance gate.

## Exact release provenance

The [policyengine 5.3.0 bundle manifest](https://github.com/PolicyEngine/policyengine.py/blob/3c3b4f6442f4a5adc47274734d71a6ca10103b43/src/policyengine/data/bundle/manifest.json) matches the installed manifest. It maps the UK dataset to data package/build `policyengine-uk-data-1.56.16`, certified model 2.90.2 and dataset `enhanced_frs_2024_25`. Its artifact SHA-256 is `e433e532b17bd8ce76030156285816e33d44e93edabd2204adbef71d19a68712`.

The [official 1.56.16 tag](https://api.github.com/repos/PolicyEngine/policyengine-uk-data/git/refs/tags/1.56.16) resolves to commit `12a1e028afeef08d8b2d74ee03fd9de3a78b2dd3`. Its [release configuration](https://github.com/PolicyEngine/policyengine-uk-data/blob/12a1e028afeef08d8b2d74ee03fd9de3a78b2dd3/policyengine_uk_data/datasets/frs_release.py#L53-L57) declares survey/base year 2024 and calibration year 2025.

The bundle does not expose a calibration-year field. Its pinned [artifact release manifest](https://huggingface.co/policyengine/policyengine-uk-data-private/resolve/2966541fca275ab5ccb6cfb659b010b1db37ad49/releases/1.56.16/release_manifest.json) was gated and could not be read. The exact-version public source establishes the configured year; artifact-specific build diagnostics remain unverified.

## Builder and runtime weights

The [builder materializes 2025 before calibration](https://github.com/PolicyEngine/policyengine-uk-data/blob/12a1e028afeef08d8b2d74ee03fd9de3a78b2dd3/policyengine_uk_data/datasets/create_datasets.py#L218-L260), using that year for the target period and saved weight key. It then [materializes the calibrated dataset back to 2024 and saves it](https://github.com/PolicyEngine/policyengine-uk-data/blob/12a1e028afeef08d8b2d74ee03fd9de3a78b2dd3/policyengine_uk_data/datasets/create_datasets.py#L303-L345).

The builder's [fixed household-weight index](https://github.com/PolicyEngine/policyengine-uk-data/blob/12a1e028afeef08d8b2d74ee03fd9de3a78b2dd3/policyengine_uk_data/utils/uprating.py#L17-L24) is 1.027 in 2024 and 1.039 in 2025. Its [uprating operation](https://github.com/PolicyEngine/policyengine-uk-data/blob/12a1e028afeef08d8b2d74ee03fd9de3a78b2dd3/policyengine_uk_data/utils/uprating.py#L251-L269) multiplies by the ratio of target-year to source-year indices. Back-materialization therefore uses 1.027/1.039. These are public input indices, not fiscal estimates.

Policyengine-uk 2.90.2 [extends the saved dataset with annual model growth factors](https://github.com/PolicyEngine/policyengine-uk/blob/3d12d26a12ccf1501ae3b3ae3522eaa80d4aa15a/policyengine_uk/data/economic_assumptions.py#L35-L98). [Household weights follow ONS population growth](https://github.com/PolicyEngine/policyengine-uk/blob/3d12d26a12ccf1501ae3b3ae3522eaa80d4aa15a/policyengine_uk/data/uprating_indices.yaml#L84-L85), with [2025 growth of 0.0072 and 2026 growth of 0.0038](https://github.com/PolicyEngine/policyengine-uk/blob/3d12d26a12ccf1501ae3b3ae3522eaa80d4aa15a/policyengine_uk/parameters/gov/economic_assumptions/yoy_growth.yaml#L817). The inspected extension does not recalibrate weights annually.

Private boolean checks on the existing native-weight caches confirmed that runtime 2025 weights follow 2024 weights multiplied by 1.0072, rather than by 1.039/1.027. Runtime 2026 weights follow 2025 weights multiplied by 1.0038. No record values or weights are published. Year 2025 is stored and supported by the demographic API.

## Interpretation and part C

The bounded rake preserves runtime-native weights exactly at the 2025 anchor because its targets equal that year's margins. It applies ONS cell growth in other years. The API requires an explicit anchor or verified dataset metadata and fails when neither is supplied.

This weight identity does not establish preserved calibrated awards. Part C needs certified calibrated-period inputs, artifact build metadata and a verified income/weight materialization contract. It must compare State Pension, Pension Credit and Housing Benefit with identical ages, pension types and claimant/head inputs to isolate the calibration bridge, then measure the effect of represented ages and cohort retyping in full model runs. The pilot does not reconstruct supposed certified weights from the public factor ratios.
