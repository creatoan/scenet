# Security Policy

## Supported versions

This project is pre-alpha. Only the `main` branch receives fixes.

## Reporting a vulnerability

Please report privately through GitHub's
[private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
on this repository, rather than opening a public issue.

## Scope

Scenet is an offline compiler. It reads YAML describing a comic panel and writes SVG. It performs
no network access and executes no user-supplied code.

The realistic risks are therefore:

- **Untrusted input.** Panel sources are parsed with `yaml.safe_load` — never `yaml.load` — so a
  malicious document cannot construct arbitrary Python objects. All input is then validated through
  pydantic models before reaching the solver.
- **Denial of service.** A crafted panel could in principle drive the constraint solver or balloon
  placement search into pathological running time. Reports of inputs causing runaway CPU or memory
  use are in scope.
- **Output injection.** Dialogue text is escaped before being emitted into SVG. An input that
  escapes its context and injects markup or script into generated SVG is in scope and would be
  treated as a real vulnerability, since SVG files are frequently opened in browsers.

## How dependencies and code are watched

All of this is GitHub's own tooling, configured in this repository; there is nothing to host.

- **Dependabot alerts** watch the
  [dependency graph](https://github.com/creatoan/scenet/network/dependencies), which GitHub
  builds from `uv.lock` and both `package-lock.json` files, transitive dependencies included.
  **Dependabot security updates** open a pull request for an alert when a fixed version
  exists. Version updates are separate, in `.github/dependabot.yml`.
- **Dependency review** fails a pull request that adds a dependency with a known high or
  critical vulnerability, development dependencies included
  (`.github/workflows/dependency-review.yml`).
- **CodeQL** analyses the Python, the TypeScript and the workflows on every pull request, on
  `main` and weekly (`.github/workflows/codeql.yml`). Its results share the
  [code-scanning page](https://github.com/creatoan/scenet/security/code-scanning) with the
  gallery diagnostics `ci.yml` uploads.
- **Secret scanning**, with push protection, rejects a push that contains a recognised
  credential.

One gap is GitHub's, not this repository's: actions are pinned to commit SHAs, and Dependabot
raises no alert for an action pinned that way. It still proposes their updates every week.
