Read-only coordination for an already authorized task; do not review or implement anything.
Work only in /Users/maxghenis/.subfleet/worktrees/20261005-080931-model-v2-e.
Parent writable job20261005-080931-model-v2-e cannot admit another writer here.
Wait until that parent becomes terminal using subfleet wait --timeout30; repeat
only as needed, never stop/cancel parent or change any operator/account policy.
While parent is active do not edit files, start model jobs or submit a writer.
After parent is terminal, first read out/E-STATE.md. If it says the original
Model v2 partE task is complete, do not dispatch continuation. Otherwise submit
ONE continuation with this exact command from the assigned workspace:
subfleet run --task build --tier hard --in-place --independent -C "$PWD" -n model-v2-e-continue -p out/E-continuation-prompt.md -o "$PWD/out/E-continuation-report.md" --json --detach
This is authorized ongoing work after the original job's runtime limit. Preserve
privateGit .git-e and every file; never create another checkout/workspace or
write in the caller repository. Report the submitted job ID and output path.
If admission still reports a live writer, wait for it; do not bypass the lock.
If service capacity is unavailable, leave the admitted continuation queued.
Do not post GitHub messages. Do not print survey logs, credentials or records.
