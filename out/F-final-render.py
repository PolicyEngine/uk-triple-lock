"""Render the requested final report from committed part F artifacts."""
import argparse
import re
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--head', required=True)
parser.add_argument('--review', type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parent
assert len(args.head) == 40 and all(c in '0123456789abcdef' for c in args.head)
review = args.review.read_text()
assert re.search(r"(?im)^\s*(?:\*\*)?APPROVE\b", review), "final report requires an explicit independent APPROVE"
validation = (root / 'F-validation.md').read_text()
routing = validation.split('## Required routing and rule checks\n', 1)[1].split('## Dry-run verification', 1)[0]
text = f'''# Model v2, part F — completed

Pre-registration: **65343e2ee43a359f056ce5a027739509d32ab49f**. It changed `docs/METHOD.md` alone and was committed and pushed before every C2 implementation/scoring commit; the SHA annotation followed separately.

Final `model-v2` head: **{args.head}**, pushed only as `HEAD:model-v2`. PR #24 remains OPEN and draft. No merge, GitHub comment, PolicyEngine simulation or survey-data run occurred. Existing untracked part D audit is preserved.

C2 dry-run primary passes: **4/6 terminal coverage; 80.0% annual coverage on 20 eligible cells; four legal exclusions**. The annual form fails switch CRPS; other alternatives pass and are reported separately. Published primary terminal coverage remains 1/6 as a sensitivity. Binding authorization remains pending after the September CPI and 28 October Budget inputs. The code automatically takes (a) after a failing binding primary and refuses a mismatched rule SHA or dry-run authorization.

Validation: focused C2/adapter/parser **102 passed**; historical E source/input checks **54 passed**; final full pytest collection **869 passed, three documented stale failures, 59 skipped**, 176.93s. The no-simulation guard accounts for 58 skips; one is the existing historical assumptions-block skip. This is not an unguarded full-suite pass. Dashboard **83 tests passed**, lint and build exit 0. No new F cold-run proof is claimed.

Independent STANDARD Subfleet review: **APPROVE**. Full verdict below. [History](F-history.txt), [registration audit](F-registration-audit.json), [validation](F-validation.md), [runbook and counts](../docs/REBUILD.md).

Unposted #14 draft: `{root / 'F-comment-14.md'}`. The requested `~/reviews/uk-triple-lock-2026-09-29/out/F-comment-14.md` lies outside writable roots, so the draft remains in the assigned workspace.

## C2 rule as committed

'''
text += (root / 'F-rule.md').read_text()
text += '\n## Dry-run results and published sensitivity\n\n' + (root / 'F-dry-run.md').read_text()
text += '\n## Routing and rule tests\n\n' + routing
text += '\n## Independent review verdict\n\n' + review
(root / 'F-final.md').write_text(text)
