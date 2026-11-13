# Security Policy

## Supported versions

This project is alpha. Fixes go into a patch release of the latest minor version: 0.11.1
was a security release of 0.11. `main` gets every fix first.

| Version | Supported |
|---|---|
| 0.13.x | Yes |
| Older | No: upgrade to the latest release |

## Reporting a vulnerability

Please report privately through GitHub's
[private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
on this repository, rather than opening a public issue.

## Scope

Scenet is a compiler. It executes no code a document supplies, and the compiler itself never
reaches the network. What it reads and what it serves:

- **Documents.** Panels, scenes and comic scripts, which are YAML or YAML front matter; so are
  artwork contracts and puppet files. YAML is parsed as `yaml.safe_load` parses it — a
  `SafeLoader`, never `yaml.load` — that also refuses a repeated key and a document nested too
  deeply, so a malicious document cannot construct arbitrary Python objects. Everything is then
  validated through pydantic models before it reaches the solver.
- **Files a document names**: a lettering font, read by fontTools; a PNG or JPEG picture to
  letter over, whose header Scenet reads itself, without an imaging library; the picture's
  artwork contract; a puppet file. Each path is read relative to the document's folder, and an
  absolute one is refused. A path may still climb out of that folder with `..`, so compiling
  a document you do not trust lets it name any font, picture or YAML file your account can
  read. A picture's bytes reach the output: an SVG built with `--embed-images` carries them,
  and so does a PDF.
- **`scenet build --watch`** reads the same files again whenever they change, and nothing else.
- **`scenet mcp`**, the MCP server, an optional extra. On stdio it talks only to the client
  that launched it. `scenet mcp --transport streamable-http` listens on the network: on
  `127.0.0.1` by default, or on whatever `--host` names, **with no authentication**. Put it
  behind something that provides authentication before exposing it beyond the machine. Its
  tools take a document as text, and the files it names as base64 in `files`; they read
  those in memory and never read or write a folder of the server's.
- **The playground** runs the compiler in the reader's browser, under Pyodide. It has no
  server.

The realistic risks are therefore:

- **Untrusted input.** A document, or a file it names, that makes Scenet do anything but
  compile it or refuse it with a finding — a crash in fontTools on a crafted font, a header
  that defeats the PNG or JPEG reader — is in scope.
- **Reading outside what was sent.** A `files` argument, or a path in a document sent to
  `scenet mcp`, that makes the server read a file of its own is in scope.
- **Denial of service.** A crafted document could in principle drive the constraint solver,
  balloon placement or a comic script's line patterns into pathological running time; 0.11.1
  fixed patterns that backtracked. Inputs causing runaway CPU or memory use are in scope,
  over MCP above all, where one request costs the server rather than its sender.
- **Output injection.** Dialogue text is escaped before it is emitted into SVG. An input that
  escapes its context and injects markup or script into a generated SVG, or into a PDF, is a
  real vulnerability, since SVG files are frequently opened in browsers.

## How dependencies and code are watched

All of this is GitHub's own tooling, configured in this repository; there is nothing to host.

- **Dependabot alerts** watch the
  [dependency graph](https://github.com/creatoan/scenet/network/dependencies), which GitHub
  builds from `uv.lock` and both `package-lock.json` files, transitive dependencies included.
  **Dependabot security updates** open a pull request for an alert when a fixed version
  can be installed, crossing a major version if it has to. When the packages that pull the
  vulnerable one in do not admit the fix, no pull request comes and the alert stays open;
  the maintainer looks at open alerts every week
  ([what then](https://github.com/creatoan/scenet/blob/main/docs/maintainer/dependencies.md)). Version updates are separate, grouped
  and limited to minor and patch releases in `.github/dependabot.yml`.
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
