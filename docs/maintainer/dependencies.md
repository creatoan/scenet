# Dependencies

**The maintainer looks at the open Dependabot alerts once a week**, on the day the weekly
version updates arrive, and whenever GitHub notifies a new one. There is also a check
before every release: a release does not go out with an alert open.

```bash
gh api repos/creatoan/scenet/dependabot/alerts --jq '[.[] | select(.state=="open")] | length'
```

That prints `0`, or there is work to do. An alert open longer than a week is never
"Dependabot will get to it": if Dependabot could, it already has.

## Why an alert can stay open

A security update is not held to the `[minor, patch]` limit in
`.github/dependabot.yml`: that limit belongs to the groups, and the groups apply to
version updates only. A security fix that needs a new major version gets its own pull
request.

What stops one is the dependency graph. When the vulnerable package is pulled in by
another, Dependabot has to stay inside that parent's version range, or bump the parent,
and it cannot when no release of the parent admits the fix yet. The update job then fails
without opening anything. The failure is visible only under **Actions → Dependabot
Updates**, as a run named after the package (`npm_and_yarn in /editor for minimatch`),
whose log says:

```text
The latest possible version that can be installed is 10.2.6 because of the following conflicting dependencies:
```

Dependabot retries a failed security update now and then, not when the parent it was
waiting for is released. The one for `@azure/msal-node` ran on 2026-10-28, a day before
`@azure/identity` 4.14.1 admitted the fix, and never ran again
([#344](https://github.com/creatoan/scenet/issues/344)).

## What to do

1. Find the path: `npm ls <package> --all` in `editor/` or `playground/`, or
   `uv tree --invert --package <package>` for Python.
2. If a newer release of the parent admits the fix within its range, refresh it:
   `npm update <parent>`.
3. If none does, override the one package under that parent alone, in `package.json`,
   so nothing else that depends on it is forced onto a new major too:

   ```json
   "overrides": {
     "@vscode/vsce": {
       "minimatch": "^11.0.1"
     }
   }
   ```

   For Python, the equivalent is `[tool.uv] constraint-dependencies` in `pyproject.toml`.
   Check that the parent still works with the new major: read how it calls the package,
   then run what exercises it (for `vsce`, `vsce ls` before and after must list the same
   files).
4. `package.json` holds no comments, so the pull request that adds an override says why.
   Remove the override once the parent's own range admits the fix.
