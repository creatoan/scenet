# Build and check a comic in CI

Keep the source comic in your repository, then have GitHub Actions check it, upload
findings as pull-request annotations, build SVGs and retain them as an artifact. This
example assumes the source is `comics/issue-01.scene.yaml`; replace that path with yours.

```{code-block} yaml
:caption: .github/workflows/comic.yml

name: Check and build comic

on:
  push:
  pull_request:

permissions:
  contents: read
  actions: read
  security-events: write

jobs:
  comic:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1

      - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0
        with:
          python-version: "3.12"

      - name: Install Scenet
        id: install
        run: python -m pip install "scenet==0.13.0"

      - name: Check source
        id: check
        continue-on-error: true
        run: scenet check --format sarif -o scenet.sarif comics/issue-01.scene.yaml

      - name: Upload findings to code scanning
        if: >-
          always()
          && steps.check.outcome != 'skipped'
          && (github.event_name != 'pull_request'
          || github.event.pull_request.head.repo.full_name == github.repository)
        uses: github/codeql-action/upload-sarif@24c54180a607b1449ed407dd24f251e4e9147c8d # v4
        with:
          sarif_file: scenet.sarif
          category: scenet

      - name: Build SVGs
        id: build
        if: always() && steps.install.outcome == 'success'
        run: |
          mkdir -p dist
          scenet build comics/issue-01.scene.yaml -o dist/

      - name: Upload SVG artifact
        if: always() && steps.build.outcome != 'skipped'
        uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2
        with:
          name: comic-svgs
          path: dist/*.svg
          if-no-files-found: ignore

      - name: Fail if the check found diagnostics
        if: steps.check.outcome == 'failure'
        run: exit 1
```

The check step uses `continue-on-error` so its SARIF report can be uploaded even when it
finds problems. The final step restores the failing status after the report and build
steps have run. The upload runs with `if: always()`; it is skipped for pull requests
from forks because their token cannot write code-scanning results. The SVGs are available
from the workflow run's **Artifacts** section.

Each finding includes a stable `ruleId` and fingerprint, allowing code scanning to track
alerts across runs.

## Code scanning availability

Code scanning is free for public repositories. Private and internal repositories need
[GitHub Code Security enabled](https://docs.github.com/en/code-security/code-scanning/integrating-with-code-scanning/uploading-a-sarif-file-to-github).
The workflow grants `security-events: write`, which the SARIF upload requires.

If Code Security is not available, use `--format text` instead. It prints one
`file:line:column: rule: message` finding per line; a [GitHub Actions problem matcher](https://github.com/actions/toolkit/blob/main/docs/problem-matchers.md)
can turn those lines into annotations. Save this as
`.github/scenet-problem-matcher.json`:

```json
{
  "problemMatcher": [
    {
      "owner": "scenet-note",
      "severity": "warning",
      "pattern": [
        {
          "regexp": "^(.*):(\\d+):(\\d+): note: ([^:]+): (.*)$",
          "file": 1,
          "line": 2,
          "column": 3,
          "code": 4,
          "message": 5
        }
      ]
    },
    {
      "owner": "scenet",
      "pattern": [
        {
          "regexp": "^(.*):(\\d+):(\\d+): (?!note: )([^:]+): (.*)$",
          "file": 1,
          "line": 2,
          "column": 3,
          "code": 4,
          "message": 5
        }
      ]
    }
  ]
}
```

The first matcher reports `note` diagnostics as warnings; the second handles other
findings without interpreting `note` as a rule name.

Replace the SARIF check and upload steps with these steps; keep the final failure step
above unchanged:

```{code-block} yaml
:caption: Part of .github/workflows/comic.yml

      - name: Register Scenet problem matcher
        run: echo "::add-matcher::.github/scenet-problem-matcher.json"

      - name: Check source
        id: check
        continue-on-error: true
        run: scenet check --format text comics/issue-01.scene.yaml
```

## Inspect findings locally

Run `scenet check --format sarif -o scenet.sarif comics/issue-01.scene.yaml`, then
open `scenet.sarif` with Microsoft's [SARIF Viewer for VS Code](https://github.com/microsoft/sarif-vscode-extension).

Pin the package version in CI: releases below `1.0.0` may make breaking changes in a
minor release. Update the pin deliberately when upgrading. To check documents from a Python
pipeline of your own, see [Outputs, batch and CI](../tutorial/python/outputs_batch_and_ci.md).

*Last checked with Scenet 0.13.0. The documentation test suite runs Python and bash examples,
but does not execute this GitHub Actions workflow.*
