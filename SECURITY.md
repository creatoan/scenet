# Security Policy

What Scenet guarantees with input from someone you do not trust, and what you must add, is
the [security model](https://creatoan.github.io/scenet/explanation/security_model.html): each
guarantee there names the test that holds it.

## Supported versions

This project is alpha, as its package says. A security fix goes into a patch release of the
latest minor version: 0.11.1 was a security release of 0.11. `main` gets every fix first.

| Version | Supported |
|---|---|
| 0.13.x | Yes |
| Older | No: upgrade to the latest release |

## Reporting a vulnerability

Please report privately through GitHub's
[private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
on this repository, rather than opening a public issue. A document, a file or a command that
shows the fault is the most useful thing a report can hold.

What happens next:

- **Within 7 days**, the report is acknowledged, and you are told whether it is taken as a
  vulnerability.
- **Within 90 days** of the report, a fixed release is published, or you are told why it
  takes longer and when it will come.
- **Disclosure is coordinated.** The fault is kept private until the fixed release is
  published; a GitHub security advisory then describes it, with a CVE where one applies, and
  credits you unless you ask not to be named. Please keep it private until then too.

## Scope

Scenet is a compiler. It executes no code a document supplies, and the compiler itself never
reaches the network. What it reads and what it serves:

- **Documents.** Panels, scenes and comic scripts, which are YAML or YAML front matter; so are
  artwork contracts and puppet files. YAML is read as
  [Scenet YAML](https://creatoan.github.io/scenet/reference/language/yaml_profile.html), a
  strict profile built from the parts of PyYAML that `yaml.safe_load` uses, never `yaml.load`.
  It refuses every tag, so a malicious document cannot construct arbitrary Python objects, and
  every anchor and alias, so none can expand without bound; it refuses a repeated key and a
  document nested too deeply as well.
  Everything is then validated through pydantic models before it reaches the solver.
- **Files a document names**: a lettering font (read by fontTools), a PNG or JPEG picture to
  letter over (whose header Scenet reads itself, without an imaging library), its artwork
  contract, and a puppet file. Each path is read relative to the folder of the file that names
  it, and must stay inside the root: the folder `--root` or `root=` names, else the nearest
  folder above the document that holds a `scenet.toml`, else the document's own folder. An
  absolute path, a `..` that leaves the root and a symbolic link out of it are refused before
  anything outside the root is opened, and only regular files are read. To compile documents
  you did not write, pass `--root` their folder, or send their files as a mapping; a
  `scenet.toml` above their folder widens the default root. A picture's bytes reach the
  output: an SVG built with `--embed-images` carries them, and so does a PDF. Each file is read
  up to a bound (`scenet.limits`), a PNG is inflated no further than its header says, and no
  message quotes what a file the document names holds.
- **`scenet build --watch`** reads the same files again whenever they change, and nothing else.
- **`scenet mcp`**, the MCP server, an optional extra. On stdio it talks only to the client
  that launched it. Its tools take a document as text, and the files it names as base64 in
  `files`, read in memory. It opens no file but the package's own and writes none, which a
  test holds with an audit hook over every call. `--root DIR` and `--output DIR`, folders a
  stdio server will be able to read from and write new files in, are refused over HTTP, and
  are not in this version yet. On either transport each tool call runs in a worker process, stopped when it
  runs past `--timeout` (60 seconds by default) or its client cancels it, so no call occupies
  the server for longer. Over HTTP, `scenet mcp --transport streamable-http` guarantees:
  - it listens on a loopback address, `127.0.0.1` by default; any other `--host` is refused
    without `--allow-remote`;
  - it answers only a `Host` that names it and an `Origin` of its own, at its own port, and
    refuses any other with 421 or 403, so no web page reaches it by DNS rebinding;
    `--allow-origin` adds an origin for a client in a browser;
  - it refuses a request body over 16 MiB with 413, before reading it;
  - it keeps no session.

  What it does not do, and an operator who exposes it beyond the machine must add in front of
  it: **authentication**, **encryption** (TLS), and a limit on how many requests one client
  may send.
- **The playground** runs the compiler in the reader's browser, under Pyodide. It has no
  server.

The realistic risks are therefore:

- **Untrusted input.** A document, or a file it names, that makes Scenet do anything but
  compile it or refuse it with a finding — a crash in fontTools on a crafted font, a header
  that defeats the PNG or JPEG reader — is in scope.
- **Reading outside the root.** A path in a document that makes Scenet open a file outside
  its root (by `..`, a symbolic link, a junction or a device name) is in scope.
- **Reading or writing outside what the server was given.** A `files` argument or a path in a
  document that makes `scenet mcp` read a file of its own, or one outside `--root`; a call that
  writes outside `--output`, or replaces a file there.
- **Denial of service.** A crafted document could in principle drive the constraint solver,
  balloon placement or a comic script's line patterns into pathological running time; 0.11.1
  fixed patterns that backtracked. Inputs causing runaway CPU or memory use are in scope,
  over MCP above all, where one request costs the server rather than its sender: a call that
  outlives `--timeout`, or keeps its worker busy once stopped, is a bug.
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
