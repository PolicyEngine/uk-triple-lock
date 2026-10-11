# Model v2 part J checkpoint

Started 11 October 2026, pre-Budget. Assigned checkout was clean at ee02c8d808ae; work advanced without rewriting history to origin/model-v2 3323c351caa53d5719c496cf9e0fde2940413ada.

The sandbox refuses writes to the original external worktree Git metadata. This job uses workspace-local `.cache/J-git` (`GIT_DIR=$PWD/.cache/J-git`, worktree remains the assigned workspace), branch `subfleet/model-v2-j` tracking origin/model-v2. No caller files have been changed. Checkpoints push HEAD:model-v2.

In progress: certified release verification and pins; upstream engine audit; isolated non-publishing C2 rehearsal adapter; full-run version bridge orchestration.

No new model figures exist yet. All committed pilot records remain uncertified. No binding C2 score or publication is authorized before the post-Budget inputs; data/results.json must remain untouched by this rehearsal.

Pending: full-run bridge and coverage, timings, pytest/dashboard checks, independent HARD review until APPROVE, exact-head CI, draft PR body update and final unposted note.

Certified pins and dataset verification complete. policyengine[uk] 6.2.6 pins policyengine-uk 2.125.1 and core 3.33.0. HF manifest fdeba38517bd86067f34c0a5d8ed8923efb3b10a certifies Enhanced FRS 1.58.0 sha256 5ba399ea5ab9a6c7d4e9aaf6c623080beb34d9ad5f330f6244dbad72b8d960b6. Certified, pilot and Microcosm dataset files are downloaded and hashed. Certification tests: 13 passed (129.25s). Full pytest and dashboard checks running; bridge model-step preflight started.

Engine guard and synthetic passport pass on 2.125.1 (all 17 checks). Retain private-pension horizon extension and CPI additional-pension override; use upstream resolved household head. Historical pilot sources archived for receipt verification; no certified-port identity claim. Bridge helper tests: 11 passed (26.58s). Source archive/receipt suites: 84 passed (59.91s), broader 159 passed (64.36s). First model-step attempt was stopped with both children terminated when host load rose above twice CPU count; no fiscal aggregates completed. Restart must cap numeric-library threads and recheck host. Initial full pytest also interrupted during collection to reduce host load; it is not validation evidence.
