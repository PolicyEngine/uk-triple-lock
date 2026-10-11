# Part J certified-bundle verification

Verified on **11 October 2026**, before the Budget. This is release and input provenance; it authorizes neither a binding C2 score nor publication of rehearsal fiscal figures. The committed **policyengine-uk 2.120.0 / Enhanced FRS 1.56.16** pilot remains an uncertified pilot, with its original figures and labels.

The project now pins **`policyengine[uk]==6.2.6`**. Its released PyPI metadata pins **policyengine-uk 2.125.1** and **policyengine-core 3.33.0** under the UK extra. All three distributions are installed at these exact versions from the regenerated `requirements-lock.txt`. Unrelated existing lock versions were retained by `uv pip compile`; the carrier adds its required JSON-schema packages. The following non-yanked wheels were checked against PyPI release metadata:

| Distribution | PyPI wheel upload (UTC) | Wheel SHA-256 |
| --- | --- | --- |
| [policyengine 6.2.6](https://pypi.org/project/policyengine/6.2.6/) | 2026-10-10 11:31:54 | `9ac20a2599cc1f4b50c128c2245042b105c40592e07fc25d39c99a529c9f410b` |
| [policyengine-uk 2.125.1](https://pypi.org/project/policyengine-uk/2.125.1/) | 2026-10-10 00:21:17 | `a0983b4cef868467578a4fd0d163a977a0da8f710dd5194ec01c75f66d512c5a` |
| [policyengine-core 3.33.0](https://pypi.org/project/policyengine-core/3.33.0/) | 2026-10-10 09:43:10 | `2e32d02a8910ab683a2b7600987904b351d058fc2bd5910a8ea6641438bcd789` |

PyPI's `policyengine-uk-data/1.58.0` JSON endpoint returned **HTTP 404**. The data package version is an artifact release in the authenticated Hugging Face manifest, rather than an installed PyPI distribution. Its [GitHub release tag](https://github.com/PolicyEngine/policyengine-uk-data/tree/1.58.0) points to `4cbedbecca352f52dffe47e849553c2759a00711`.

[PolicyEngine/policyengine.py #555](https://github.com/PolicyEngine/policyengine.py/pull/555), “Certify policyengine-uk-data 1.58.0 with policyengine-uk 2.125.1 and core 3.33.0”, is **MERGED**. Its merge commit is `37d25c423e9541b4ca86adbdd8687738b49ab8ec`, merged at **2026-10-10 10:58:18 UTC**. The merged source manifest still names the preceding carrier version 6.2.5; the subsequently published wheel's own manifest correctly names **6.2.6** and **`uk-6.2.6`**. Verification uses the released wheel, whose bundled manifest SHA-256 is `8633ad814c9c85e53c7c513f69c4c7b1500a03cd2f6ef133d6e2ea8346b2db54`.

The released wheel names the [HF release manifest](https://huggingface.co/policyengine/policyengine-uk-data-private/resolve/fdeba38517bd86067f34c0a5d8ed8923efb3b10a/releases/1.58.0/release_manifest.json) at immutable commit **`fdeba38517bd86067f34c0a5d8ed8923efb3b10a`**, path `releases/1.58.0/release_manifest.json`. That authenticated manifest was fetched separately and hashes to `ddd63e1f7755ee358c4ede9050bfdde09f3a80f48a5c0d8ee9d1fb531e4a1a07`. It records:

| Field | Verified value |
| --- | --- |
| Data package / build ID | `policyengine-uk-data 1.58.0` / `policyengine-uk-data-1.58.0` |
| Artifact | `enhanced_frs_2024_25.h5`, revision `1.58.0` |
| Artifact SHA-256 | `5ba399ea5ab9a6c7d4e9aaf6c623080beb34d9ad5f330f6244dbad72b8d960b6` |
| Artifact bytes | `128369110` |
| Build model / core | `policyengine-uk 2.122.2` / `policyengine-core 3.32.13` |
| Build fingerprint | `sha256:c094d7006fdd81df220090284212f16bbffb15624643bc442c4bb3e1b1e5dac8` |
| Compatible model versions | `2.122.2`, `2.123.4`, **`2.125.1`** |
| Compatible core versions | `3.32.13`, `3.32.21`, **`3.33.0`** |

The `built_with_model_package.git_sha` in the release manifest is the uk-data release commit, an existing publisher metadata defect documented by #555; it is not treated as evidence of a model-source commit. The manifest and bundle carry the same value unchanged.

[The release-tag `frs_release.py`](https://github.com/PolicyEngine/policyengine-uk-data/blob/1.58.0/policyengine_uk_data/datasets/frs_release.py) sets `survey_year=2024`, `base_year=2024`, and **`calibration_year=2025`**. The new registry pin therefore preserves the 2025 static-ageing anchor.

All three run inputs were downloaded into the workspace's ignored `.cache/datasets` and independently hashed after download. The certified artifact matches the manifest; the pilot input matches `e433e532b17bd8ce76030156285816e33d44e93edabd2204adbef71d19a68712`; Microcosm matches `f17306ccb2aad7ff0130be3589b560afb2e2a12a943570911cd0c77f07934833`. No survey values are included here.

`datasets.provenance` records the installed bundle, model and core versions, dataset SHA-256, release-manifest identity and build metadata. It emits `certified: true` only if all exact versions match, the installed released bundle manifest hashes to its checked pin, and that manifest certifies the registry's exact artifact URI, SHA-256 and data-package version. A different model, core, carrier, artifact or changed manifest stays uncertified. The pilot dataset and the `populace_uk_2023` overlay stay **`certified: false`** under this carrier. Microcosm load/run status is recorded separately by the part J execution receipts.

Validation: `.venv/bin/python -m pytest -q tests/test_datasets.py` completed with **13 passed in 129.25 seconds**. It checks released pins and metadata, the certified provenance, fail-closed version/artifact/manifest mismatches, historical pilot and Microcosm status, and byte verification. No model jobs are started by these checks. `git diff --check` passed for these changes.

The retained E cold-run source checks now read the hash-bound [uncertified pilot source archive](../../tests/fixtures/model-v2-uncertified-pilot-source.tar.gz), derived from `3323c351caa53d5719c496cf9e0fde2940413ada` and bound by SHA-256 `2b2abafcd055bb22d62c17e8c03b40c69123d0da6ea0b7d40fd01eab1999af54` in [cold-source-binding.json](../../data/pilot/cold-source-binding.json). Its one input-metadata redaction is described below; all other 31 members remain byte-identical. No member is extracted or imported by the verifier. The original scientific-source, fiscal-input, protected-AST, privacy-normalization and execution-recipe checks remain in force against that archive, with the separately pinned diagnostic-removal transform for the recipe. These historical checks make **no correspondence claim for the certified port**; the actual retained cold receipts and fiscal figures remain unchanged. New regressions reject changed archive bytes and verify both retained datasets independently of the new tree's certified pin and engine bytes.

The updated determinism and Enhanced FRS source suites passed **84 tests in 59.91 seconds**. The broader receipt suite, including resume and pilot evidence, passed **159 tests in 64.36 seconds** before the three new archive regressions were added; the updated source suites cover those additions. These checks start no model jobs.

The old macro recipe carried a single-record diagnostic field, `largest_record_bn_v0`, in four `concentrated` rows. Part J removes only those fields from [d_macro_specs.json](../../data/pilot/d_macro_specs.json) and its archived copy. Every surviving original JSON value was compared directly and retained, including all central, paired, OBR and extra engine specifications, stratum labels, draw indices, multiplicities and probabilities. All fiscal aggregates and historical receipts remain unchanged. The original raw recipe SHA-256 **`9b940b203a4e6466e5972888c58b2bbefe99c92ad96d2f6b08a2209c63b4af36`** stays immutable historical provenance; it is not the sanitized file's hash.

The exact reviewed transform is `remove_concentrated_largest_record_bn_v0_v1` in `input_redactions` of the source binding. The sanitized recipe SHA-256 is **`4afca787b20b8515a0b372650e8e080d9827535d69c63068f0de97b95cc86117`**. Its `runnable_recipe_sha256`, hashing every surviving JSON value with sorted keys and compact separators, is **`35a6c7e7e3ed46942e2187c8460147b14fabb6deafadfc6a30a06b7ddc12b061`**. The verifier independently pins that latter hash, checks the original raw hash against each historical receipt, and requires the current and archived sanitized recipes to match. Thus updating the redaction metadata cannot authorize changed model inputs. The saved cold receipts' complete central argument hashes still reproduce exactly. Tests also reject reintroduced diagnostic fields and changed central, paired, OBR, concentrated or probability inputs even if their metadata digests are refreshed.

The focused historical-source, redaction and pilot-privacy regressions passed **45 tests in 63.33 seconds** (91 unrelated cases deselected), with no model jobs. Historical diagnostic tests retain the original receipt bytes and accept the sanitized recipe only through this exact reviewed transform.
