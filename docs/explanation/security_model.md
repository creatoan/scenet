# Security model

Scenet is a compiler. It reads documents and the files they name, and writes SVG, PDF and
JSON. It runs no code a document supplies, and the compiler never reaches the network. This
page says what can go wrong when the input comes from someone you do not trust, what Scenet
guarantees, and what whoever runs it must add. Each guarantee names the test that holds it:
a guarantee no test holds is a hope, and is not on this page.

[`SECURITY.md`](https://github.com/creatoan/scenet/blob/main/SECURITY.md) says how to report a
vulnerability.

## What is worth protecting

- **The files of the account that runs Scenet.** A document names files by path; a path that
  reached any file the account can read would let a document's author read them back,
  through a picture embedded in a PDF, a font's digest in Panel Core, or a message.
- **The machine's time and memory.** One document should not occupy a server, or a
  terminal, for longer than a document takes.
- **Whoever opens the output.** An SVG is opened in browsers; one that carried a script, an
  event handler or a link out would run it there.
- **A server's other clients**, when Scenet serves a model over MCP.

## Who the attacker is, in each use

| Use | The attacker | What Scenet guarantees | What you must add |
|---|---|---|---|
| `scenet build` or `scenet check` on a document someone sent you | Its author | It reads only inside the document's root, only regular files, each up to a bound; it runs nothing it is sent; the output is escaped | Build it in a folder of its own, with `--root` that folder; never `--root /`, and no `scenet.toml` above it |
| A program compiling documents its users send, through the Python API | Each user | The same, for files sent in a mapping or read inside `root=` | Send their files as a mapping, or pass `root=` a folder of theirs alone; bound the time and memory of the process: a compile is not yet bounded in work |
| `scenet mcp`, over stdio or HTTP | The client, and any web page in a browser on the same machine | No file system is read; each call is stopped after `--timeout`; over HTTP, only its own `Host` and `Origin` are answered and a large body is refused | Over HTTP beyond the machine: authentication, encryption and a limit on requests, in front of it |
| A playground link someone shares | Its author | The document is compiled in your browser, under a strict Content Security Policy, and a link holds at most 512 KB | Nothing; a hostile link can make the tab stop answering, and closing it ends that |

## What is guaranteed

| Guarantee | Held by |
|---|---|
| No `eval`, `exec`, `pickle`, `marshal`, `subprocess` or shell anywhere in the compiler. `scenet mcp` runs tool calls in worker processes of its own, which `multiprocessing` hands the call's arguments and the result over a pipe it made | [`tests/test_security_model.py::TestNothingRunsWhatItReads`](https://github.com/creatoan/scenet/blob/main/tests/test_security_model.py) |
| YAML is read with a strict profile of PyYAML's safe loader: no tag, so no Python object is ever built; no anchor or alias, so nothing expands without bound; no key written twice; no document nested past a fixed depth | [`tests/test_yaml_profile.py::TestRefusals`](https://github.com/creatoan/scenet/blob/main/tests/test_yaml_profile.py), [`tests/test_safe_yaml.py::TestNestingTooDeep`](https://github.com/creatoan/scenet/blob/main/tests/test_safe_yaml.py) |
| No XML is parsed: SVG is written, never read | [`tests/test_security_model.py::TestNothingRunsWhatItReads`](https://github.com/creatoan/scenet/blob/main/tests/test_security_model.py) |
| Text in an SVG is escaped, an identifier cannot open an element or an attribute, and no SVG holds a script, an event handler or a link outside itself: a picture is a relative path or a `data:` URI | [`tests/test_pipeline.py::TestIdentifiersCannotInjectMarkup`](https://github.com/creatoan/scenet/blob/main/tests/test_pipeline.py), [`tests/test_security_model.py::TestTheOutput`](https://github.com/creatoan/scenet/blob/main/tests/test_security_model.py) |
| A print PDF holds no JavaScript, no link, no action run on opening, and no external content | [`tests/test_pdf_x_checklist.py::test_x4_requirements_are_not_broken`](https://github.com/creatoan/scenet/blob/main/tests/test_pdf_x_checklist.py), [`tests/test_security_model.py::TestTheOutput`](https://github.com/creatoan/scenet/blob/main/tests/test_security_model.py) |
| Every file a document names is inside its root, `..` and symbolic links followed, and one that is not is refused before anything outside the root is opened or looked at | [`tests/test_file_reads.py::TestTheDefaultRoot`](https://github.com/creatoan/scenet/blob/main/tests/test_file_reads.py), [`tests/test_file_reads.py::TestANamedRoot`](https://github.com/creatoan/scenet/blob/main/tests/test_file_reads.py) |
| Only regular files are read, each up to its bound, and a PNG is inflated no further than its header says | [`tests/test_file_reads.py::TestOnlyRegularFiles`](https://github.com/creatoan/scenet/blob/main/tests/test_file_reads.py), [`tests/test_file_reads.py::TestABoundOnSize`](https://github.com/creatoan/scenet/blob/main/tests/test_file_reads.py), [`tests/test_file_reads.py::TestADecompressionBomb`](https://github.com/creatoan/scenet/blob/main/tests/test_file_reads.py) |
| No message quotes what a file the document names holds, when it was read from disk | [`tests/test_file_reads.py::TestNoContentQuoted`](https://github.com/creatoan/scenet/blob/main/tests/test_file_reads.py) |
| No absolute path, and no path of the machine it ran on, reaches any output | [`tests/test_golden.py::TestThePathChangesNothing`](https://github.com/creatoan/scenet/blob/main/tests/test_golden.py) |
| For any bytes, every entry point answers with findings or a `ScenetError`, in bounded time and memory, and never prints a traceback | [`tests/test_fuzz_regressions.py::test_it_passes_the_oracle`](https://github.com/creatoan/scenet/blob/main/tests/test_fuzz_regressions.py), [`tests/test_last_resort.py::TestAnUnexpectedException`](https://github.com/creatoan/scenet/blob/main/tests/test_last_resort.py) |
| `scenet mcp` opens no file but the package's own during a call, and writes none; `--root` and `--output` are refused over HTTP | [`tests/test_mcp_http.py::TestNoFileIsOpened`](https://github.com/creatoan/scenet/blob/main/tests/test_mcp_http.py), [`tests/test_mcp_http.py::TestNoFileIsRead`](https://github.com/creatoan/scenet/blob/main/tests/test_mcp_http.py), [`tests/test_mcp_http.py::TestTheFoldersAreRefused`](https://github.com/creatoan/scenet/blob/main/tests/test_mcp_http.py) |
| `scenet mcp` stops a tool call after `--timeout`, killing its worker, and goes on serving | [`tests/test_mcp_http.py::TestTheBudget`](https://github.com/creatoan/scenet/blob/main/tests/test_mcp_http.py) |
| Over HTTP, `scenet mcp` listens on this machine unless told `--allow-remote`, answers only its own `Host` (else 421) and `Origin` (else 403), refuses a body over 16 MiB (413), and keeps no session | [`tests/test_mcp_http.py::TestListening`](https://github.com/creatoan/scenet/blob/main/tests/test_mcp_http.py), [`tests/test_mcp_http.py::TestOverARealPort`](https://github.com/creatoan/scenet/blob/main/tests/test_mcp_http.py) |
| The playground's page runs no script but its own and loads no plug-in, and a shared link that inflates past 512 KB is refused | [`tests/test_security_model.py::TestThePlayground`](https://github.com/creatoan/scenet/blob/main/tests/test_security_model.py) |

## What is not guaranteed

- **Bounded work in the compiler itself.** Over MCP, each call is stopped after its time; on
  the command line and through the API, a document whose balloons hold hundreds of words can
  take minutes to place, and one that asks for a page of enormous size can take memory to
  match. Run a compile of documents you do not trust in a process with a time and a memory
  limit of its own.
- **Authentication, encryption, and rate limits** for `scenet mcp` over HTTP: put them in
  front of it.
- **A picture's contents.** A PNG or JPEG named by a document is embedded as it is, into the
  PDF and into an SVG built with `--embed-images`. Scenet reads its header and its image data,
  and checks them against each other, but does not look at what it shows.
- **A responsive playground tab.** The compiler runs on the page's own thread, so a hostile
  shared link can make the tab stop answering until it is closed.
- **The default root, for a document you did not write.** It is the document's folder, or the
  folder of a `scenet.toml` above it: a document saved below someone's project reads within
  that project. Pass `--root` a folder of the document's alone.
