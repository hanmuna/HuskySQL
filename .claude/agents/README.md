# Agents

## Local (written for this repo)

- `paper-scout` — literature / leaderboard survey, keeps cross-session memory.
- `bird-analyst` — zero-token analysis over saved run artifacts.
- `exp-runner` — long paid or mechanical runs.

## Vendored reviewer agents

Copied from [flonat/flonat-research](https://github.com/flonat/flonat-research)
(MIT, v0.3.0). Only the reviewer subset was taken; the upstream installer
(`scripts/setup.sh`) was deliberately not run — it rewrites the global Claude
config and installs 93 skills, 18 rules and three always-on hooks.

- `blindspot` — audits empirical results for what the author cannot see.
- `referee2-reviewer` — adversarial reviewer over claims, design and code.
- `claim-verify` — checks that cited claims match what the sources say.
- `reproducibility-auditor` — checks the repo can be rerun by someone else.

Their relative `skills/shared/...` references were repointed to
`.claude/skills/shared/`, where the referenced protocol files are vendored.
Reports are written under `reviews/` (gitignored).

Upstream also ships `paper-critic` and `fatal-error-check`; both assume a
compiled LaTeX paper, so they were left out until there is a draft.
