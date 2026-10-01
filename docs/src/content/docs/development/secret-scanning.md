---
title: Secret scanning
description: How secrets are kept out of the repo, in CI and on your machine.
---

Every PR is scanned for secrets (API keys, private keys, passwords, …) with
[gitleaks](https://github.com/gitleaks/gitleaks); a PR that contains one can't be merged.
You can run the same scan over the whole history locally with `make secrets-scan`
(needs Docker).

## Optional pre-commit hook

CI only sees a secret after it has been pushed — and in a public repo, that means it's
already exposed and must be rotated. The optional pre-commit hook catches it on your
machine first, by scanning your staged changes before each commit.

Git hooks are never cloned or pushed, so this is **opt-in, per clone**:

```sh
brew install gitleaks   # or see https://github.com/gitleaks/gitleaks#installing
make hooks              # turn the hook on for this clone
make hooks-off          # turn it off again
```

- If a secret is found, the commit is stopped and the finding is shown (redacted).
- If the hook is on but gitleaks isn't installed, the commit is stopped with a message
  explaining how to install it or turn the hook off.
- To skip the hook for a single commit: `git commit --no-verify` (CI still checks).
- Genuine false positives can be allow-listed in `.gitleaks.toml`, with a comment
  explaining why.
