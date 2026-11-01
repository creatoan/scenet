/**
 * Playground glue.
 *
 * The moving parts, and this file is the only thing that knows about all of them: a
 * Monaco editor (`./scenet-monaco`), a Pyodide-hosted compiler (`./compiler`), the
 * gallery the build inlined into `examples.json` and the order it is shown in
 * (`./gallery`), a zoomable viewer (`./viewport`) and the panels laid side by side in it
 * (`./maps`), the output options (`./options`), what a screen reader announces
 * (`./outline`), the files beside the document (`./files`), downloads (`./export`), and the
 * draft and share links (`./persist`).
 *
 * No geometry, no layout, no language knowledge beyond telling one document kind from
 * another. Everything else happens in Python.
 */

import * as monaco from "monaco-editor";
import EditorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker";
import JsonWorker from "monaco-editor/esm/vs/language/json/json.worker?worker";
import YamlWorker from "monaco-yaml/yaml.worker?worker";

import {
  bootCompiler,
  type CompileFailure,
  type CompileResult,
  type CompileSuccess,
  type Compiler,
  type PanelExports,
  type Picture,
} from "./compiler";
import { exampleFiles, type DocumentFile } from "./examples";
import {
  CONDITIONING,
  conditioningFile,
  download,
  sourceFilename,
  stemFor,
  svgBlob,
  svgToPng,
  textBlob,
} from "./export";
import { fileKind, formatSize, imageType, listed } from "./files";
import { declaredPath, fontFileName } from "./fonts";
import {
  displayOrder,
  docHref,
  exampleHash,
  exampleIndex,
  exampleNameFromHash,
  grouped,
  neighbours,
  type Gallery,
} from "./gallery";
import { declaredImagePath, imageFileName, isContract } from "./images";
import { composeMaps } from "./maps";
import {
  chosenLayout,
  loadOptions,
  offeredLayouts,
  saveOptions,
  type Layout,
  type OutputOptions,
} from "./options";
import { noteRows, type Place } from "./notes";
import { outline } from "./outline";
import {
  browserStore,
  clearDraft,
  decodeSource,
  encodeSource,
  loadDraft,
  loadNumber,
  saveDraft,
  saveNumber,
  shareUrl,
  tokenFromHash,
} from "./persist";
import {
  SCENET_MARKER_OWNER,
  SCENET_THEME_DARK,
  SCENET_THEME_LIGHT,
  SEMANTIC_HIGHLIGHTING,
  detectKind,
  languageFor,
  modelUriFor,
  registerScenetLanguages,
  toMarkers,
  type ScenetDocumentKind,
} from "./scenet-monaco";
import { installSplitter } from "./splitter";
import { banner, currentVersion, fetchVersions, playgroundUrl } from "./versions";
import { Viewport } from "./viewport";
import "./style.css";

/** Long enough not to recompile mid-word, short enough to feel live. */
const COMPILE_DELAY_MS = 300;

const KIND_LABEL: Record<ScenetDocumentKind, string> = {
  panel: "panel",
  scene: "scene",
  script: "comic script",
};

interface Example {
  readonly title: string;
  readonly kind: ScenetDocumentKind;
  readonly file: string;
  readonly group: string;
  /** One sentence, shown under the editor. */
  readonly summary: string;
  /** The page of `docs/` that explains it, as the manifest writes it. */
  readonly doc: string;
  readonly source: string;
  /** Files it names beside itself, as base64: a picture it is lettered over. */
  readonly files?: Readonly<Record<string, string>>;
}

/**
 * Where the text in the editor came from, which decides what the blurb says, what
 * Reset goes back to, where Previous and Next go, and what downloads are called. `index`
 * is a gallery example, or -1 for a restored draft that did not start from one.
 */
type Origin =
  | { readonly from: "example"; readonly index: number }
  | { readonly from: "draft"; readonly index: number }
  | { readonly from: "shared" };

declare global {
  interface Window {
    MonacoEnvironment?: monaco.Environment;
  }
}

window.MonacoEnvironment = {
  getWorker(_workerId: string, label: string): Worker {
    if (label === "yaml") return new YamlWorker();
    if (label === "json") return new JsonWorker();
    return new EditorWorker();
  },
};

function element<T extends HTMLElement>(id: string): T {
  const found = document.getElementById(id);
  if (found === null) {
    throw new Error(`playground markup is missing #${id}`);
  }
  return found as T;
}

const workspace = element<HTMLElement>("workspace");
const editorHost = element<HTMLDivElement>("editor");
const exampleSelect = element<HTMLSelectElement>("examples");
const previousButton = element<HTMLButtonElement>("previous");
const nextButton = element<HTMLButtonElement>("next");
const summary = element<HTMLSpanElement>("summary");
const docLink = element<HTMLAnchorElement>("doc-link");
const blurb = element<HTMLSpanElement>("blurb");
const resetButton = element<HTMLButtonElement>("reset");
const shareButton = element<HTMLButtonElement>("share");
const addFontButton = element<HTMLButtonElement>("add-font");
const fontInput = element<HTMLInputElement>("font-file");
const addImageButton = element<HTMLButtonElement>("add-image");
const imageInput = element<HTMLInputElement>("image-file");
const kindLabel = element<HTMLSpanElement>("kind");
const splitter = element<HTMLDivElement>("splitter");
const outputPane = element<HTMLElement>("output-pane");
const output = element<HTMLDivElement>("output");
const stage = element<HTMLDivElement>("stage");
const coreHost = element<HTMLDivElement>("core");
const statusLine = element<HTMLParagraphElement>("status");
const notes = element<HTMLDivElement>("notes");
const errorBox = element<HTMLDivElement>("error");
const zoomControls = element<HTMLDivElement>("zoom-controls");
const zoomLevel = element<HTMLButtonElement>("zoom-level");
const downloadMenu = element<HTMLDetailsElement>("download-menu");
const optionsMenu = element<HTMLDetailsElement>("options-menu");
const liveTextOption = element<HTMLInputElement>("option-live-text");
const outlineHost = element<HTMLDivElement>("outline");
const outlineList = element<HTMLOListElement>("outline-list");
const filesHost = element<HTMLDivElement>("files");
const filesList = element<HTMLUListElement>("files-list");
const fileView = element<HTMLDivElement>("file-view");
const fullscreenButton = element<HTMLButtonElement>("fullscreen");
const versionSelect = element<HTMLSelectElement>("version-select");
const versionBanner = element<HTMLParagraphElement>("version-banner");
const tabs = {
  panel: element<HTMLButtonElement>("tab-panel"),
  debug: element<HTMLButtonElement>("tab-debug"),
  core: element<HTMLButtonElement>("tab-core"),
  ".depth.svg": element<HTMLButtonElement>("tab-depth"),
  ".mask.svg": element<HTMLButtonElement>("tab-mask"),
  ".pose.json": element<HTMLButtonElement>("tab-pose"),
  ".boxes.json": element<HTMLButtonElement>("tab-boxes"),
  ".semantics.json": element<HTMLButtonElement>("tab-semantics"),
  outline: element<HTMLButtonElement>("tab-outline"),
  files: element<HTMLButtonElement>("tab-files"),
};
const layoutOptions = {
  pages: element<HTMLInputElement>("layout-pages"),
  strip: element<HTMLInputElement>("layout-strip"),
  panels: element<HTMLInputElement>("layout-panels"),
} satisfies Record<Layout, HTMLInputElement>;

type View = keyof typeof tabs;

/** The views drawn in the zoomable viewer; the rest are text, or a list. */
const PICTURE_VIEWS: ReadonlySet<View> = new Set<View>([
  "panel",
  "debug",
  ".depth.svg",
  ".mask.svg",
  ".pose.json",
  ".boxes.json",
]);

/** The views that show an export for image models, made only while one is open. */
const EXPORT_VIEWS: ReadonlySet<View> = new Set<View>(CONDITIONING.map((exported) => exported.suffix as View));

const store = browserStore();

function prefersDark(): boolean {
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function setStatus(message: string, busy = false): void {
  statusLine.textContent = message;
  statusLine.classList.toggle("busy", busy);
}

/**
 * Say which version of Scenet this playground runs, and offer the others.
 *
 * Every version of the site has a playground, and nothing else on the page tells them
 * apart. Switching carries a share link's document along; a draft follows anyway, since
 * every version's playground shares this origin's storage.
 */
async function showVersions(): Promise<void> {
  const versions = await fetchVersions();
  const current = currentVersion(versions, location.pathname);
  if (current === undefined) return;

  for (const version of versions) {
    const option = document.createElement("option");
    option.value = version.url;
    option.textContent = version.name;
    option.selected = version === current;
    versionSelect.append(option);
  }
  versionSelect.addEventListener("change", () => {
    const chosen = versions.find((version) => version.url === versionSelect.value);
    if (chosen !== undefined && chosen !== current) {
      location.href = playgroundUrl(chosen, location.hash);
    }
  });
  versionSelect.hidden = false;

  const shown = banner(versions, current);
  if (shown === undefined) return;
  element<HTMLSpanElement>("version-banner-text").textContent = shown.text;
  const latest = element<HTMLAnchorElement>("version-latest");
  latest.href = playgroundUrl(shown.latest, "");
  // The fragment as it is when followed: an edit drops a share link from the address.
  latest.addEventListener("click", () => {
    latest.href = playgroundUrl(shown.latest, location.hash);
  });
  versionBanner.hidden = false;
}

async function main(): Promise<void> {
  void showVersions();

  const schemaBase = (name: string): string =>
    new URL(`schemas/${name}`, document.baseURI).href;

  registerScenetLanguages(monaco, {
    panelSchemaUrl: schemaBase("panel.schema.json"),
    sceneSchemaUrl: schemaBase("scene.schema.json"),
  });

  const gallery = (await (await fetch(new URL("examples.json", document.baseURI))).json()) as
    Gallery<Example>;
  const examples = gallery.examples;
  const start = Math.max(0, gallery.start);
  const order = displayOrder(gallery);

  // By theme, from the tour. An option's value stays the example's index in the
  // manifest, which is what a draft remembers.
  for (const group of grouped(gallery)) {
    const optgroup = document.createElement("optgroup");
    optgroup.label = group.name;
    for (const index of group.indices) {
      const option = document.createElement("option");
      option.value = String(index);
      option.textContent = examples[index]?.title ?? "";
      optgroup.append(option);
    }
    exampleSelect.append(optgroup);
  }

  // One model per document kind, because monaco-yaml associates a schema by matching
  // the model's URI against a filename pattern. Reusing one model would mean a scene
  // document being validated against the panel schema.
  const models = new Map<ScenetDocumentKind, monaco.editor.ITextModel>();
  const modelFor = (kind: ScenetDocumentKind): monaco.editor.ITextModel => {
    const existing = models.get(kind);
    if (existing !== undefined) return existing;
    const created = monaco.editor.createModel(
      "",
      languageFor(kind),
      monaco.Uri.parse(modelUriFor(kind)),
    );
    models.set(kind, created);
    return created;
  };
  const kindOf = (model: monaco.editor.ITextModel): ScenetDocumentKind => {
    for (const [kind, candidate] of models) {
      if (candidate === model) return kind;
    }
    return "panel";
  };

  const editor = monaco.editor.create(editorHost, {
    model: modelFor("panel"),
    theme: prefersDark() ? SCENET_THEME_DARK : SCENET_THEME_LIGHT,
    automaticLayout: true,
    minimap: { enabled: false },
    fontSize: 14,
    lineNumbers: "on",
    scrollBeyondLastLine: false,
    renderWhitespace: "none",
    tabSize: 2,
    wordWrap: "on",
    padding: { top: 12, bottom: 12 },
    ...SEMANTIC_HIGHLIGHTING,
  });

  window
    .matchMedia("(prefers-color-scheme: dark)")
    .addEventListener("change", () =>
      monaco.editor.setTheme(prefersDark() ? SCENET_THEME_DARK : SCENET_THEME_LIGHT),
    );

  const viewport = new Viewport(output, stage, (transform) => {
    zoomLevel.textContent = `${Math.round(transform.scale * 100)}%`;
  });

  installSplitter(workspace, splitter, loadNumber(store, "split", 0.5), (ratio) =>
    saveNumber(store, "split", ratio),
  );

  let compiler: Compiler | undefined;
  let lastGood: CompileSuccess | undefined;
  // What the last document that compiled looks like, as the output options draw it.
  let pictures: readonly Picture[] = [];
  let options: OutputOptions = loadOptions(store);
  // Counts documents that compiled: the exports for image models are kept for one of them.
  let book = 0;
  let exportsCache: { readonly book: number; readonly panels: readonly PanelExports[] } | undefined;
  // Each drawing takes a ticket, as each compile does, so the latest options win.
  let drawing = 0;
  // The file the Files tab shows, and the address its picture is shown from.
  let openFile: string | undefined;
  let fileUrl: string | undefined;
  let view: View = "panel";
  let origin: Origin = { from: "example", index: start };
  let edited = false;
  // True while this file, not the person typing, is changing the editor's text.
  let loading = false;
  // A `#example=` link the page was opened with that names no example: said once compiled.
  let missingExample: string | undefined;
  // Each compile takes a ticket; a result is shown only if no later compile started.
  let generation = 0;
  let timer: number | undefined;

  // --- Panel Core and the semantics, in their own read-only editor -------------------

  const coreModel = monaco.editor.createModel(
    "",
    "json",
    monaco.Uri.parse("inmemory://model/panel.core.json"),
  );
  const semanticsModel = monaco.editor.createModel(
    "",
    "json",
    monaco.Uri.parse("inmemory://model/panel.semantics.json"),
  );
  let coreEditor: monaco.editor.IStandaloneCodeEditor | undefined;
  // Where each was scrolled to and what was folded, kept across switching between them.
  const viewStates = new Map<monaco.editor.ITextModel, monaco.editor.ICodeEditorViewState>();

  /** Created on first view: a hidden editor has no size to lay out against. */
  const showJson = (model: monaco.editor.ITextModel, text: string): void => {
    coreEditor ??= monaco.editor.create(coreHost, {
      model,
      readOnly: true,
      domReadOnly: true,
      automaticLayout: true,
      minimap: { enabled: false },
      fontSize: 13,
      scrollBeyondLastLine: false,
      folding: true,
      showFoldingControls: "always",
      renderLineHighlight: "none",
      padding: { top: 8, bottom: 8 },
    });
    const current = coreEditor.getModel();
    if (current !== model) {
      const leaving = coreEditor.saveViewState();
      if (current !== null && leaving !== null) viewStates.set(current, leaving);
      coreEditor.setModel(model);
      const returning = viewStates.get(model);
      if (returning !== undefined) coreEditor.restoreViewState(returning);
    }
    if (model.getValue() === text) return;
    // Keep the scroll position and folds across recompiles, so a section folded open
    // to watch one value stays open while the source is edited.
    const state = coreEditor.saveViewState();
    model.setValue(text);
    if (state !== null) coreEditor.restoreViewState(state);
  };

  // --- Showing results ---------------------------------------------------------------

  /**
   * Show whichever view is selected, from the last successful compile.
   *
   * The SVG goes in with `innerHTML` (inside the viewport). That is safe because the
   * compiler escapes every identifier and every line of dialogue into its attribute or
   * element -- there are regression tests for exactly this, since
   * `xml.sax.saxutils.escape` does not escape quotation marks and an actor id that
   * closed its own attribute used to be a scripting vector.
   */
  const render = (): void => {
    for (const [name, button] of Object.entries(tabs)) {
      button.setAttribute("aria-selected", String(name === view));
    }
    const picture = PICTURE_VIEWS.has(view);
    output.hidden = !picture;
    zoomControls.hidden = !picture;
    coreHost.hidden = view !== "core" && view !== ".semantics.json";
    outlineHost.hidden = view !== "outline";
    filesHost.hidden = view !== "files";
    // The files are there before anything compiles: the gallery's are written at start.
    if (view === "files") {
      showFiles();
      return;
    }
    if (lastGood === undefined) return;
    if (view === "core") {
      showJson(coreModel, lastGood.core);
    } else if (view === "outline") {
      showOutline();
    } else if (EXPORT_VIEWS.has(view)) {
      void showExport(view);
    } else if (pictures.length > 0) {
      const debug = view === "debug";
      viewport.show(
        composeMaps(pictures.map((shown) => ({ name: shown.name, svg: debug ? shown.debug : shown.svg }))),
      );
    }
  };

  // --- Exports for image models ------------------------------------------------------

  /**
   * Every panel's exports, made the first time a tab or a download asks for them after a
   * compile, so typing stays as fast as it was. Undefined when a later document compiled
   * while they were being made: drawing that one asks again.
   */
  const panelExports = async (): Promise<readonly PanelExports[] | undefined> => {
    if (compiler === undefined || lastGood === undefined) return undefined;
    if (exportsCache?.book === book) return exportsCache.panels;
    const asked = book;
    const panels = await compiler.conditioning();
    if (asked !== book) return undefined;
    exportsCache = { book: asked, panels };
    return panels;
  };

  /** The semantics as one JSON document: a lone panel's own, or each panel's by its name. */
  const semanticsText = (panels: readonly PanelExports[]): string => {
    const [only] = panels;
    if (only !== undefined && panels.length === 1) return only.files[".semantics.json"] ?? "";
    const each = panels.map((panel) => [panel.panel, JSON.parse(panel.files[".semantics.json"] ?? "null")]);
    return `${JSON.stringify(Object.fromEntries(each), null, 2)}\n`;
  };

  const showExport = async (shown: View): Promise<void> => {
    const panels = await panelExports();
    if (panels === undefined || view !== shown) return;
    if (shown === ".semantics.json") {
      showJson(semanticsModel, semanticsText(panels));
      return;
    }
    // The pose and the boxes are JSON: what is shown is their picture, drawn in Python.
    viewport.show(
      composeMaps(
        panels.map((panel) => ({ name: panel.panel, svg: panel.previews[shown] ?? panel.files[shown] ?? "" })),
      ),
    );
  };

  // --- What a screen reader announces ------------------------------------------------

  const ROLE_WORD = { img: "image", group: "group" } as const;

  /** The output as a screen reader walks it, from the very markup the Panel tab shows. */
  const showOutline = (): void => {
    const parser = new DOMParser();
    const entries = pictures.flatMap((shown) =>
      outline(parser.parseFromString(shown.svg, "image/svg+xml").documentElement),
    );
    outlineList.replaceChildren(
      ...entries.map((entry) => {
        const item = document.createElement("li");
        item.style.paddingInlineStart = `${entry.depth * 1.5}rem`;
        const role = document.createElement("span");
        role.className = "role";
        role.textContent = ROLE_WORD[entry.role];
        const name = document.createElement("span");
        name.className = entry.name === undefined ? "name unnamed" : "name";
        name.textContent = entry.name ?? "no name: announced as its role alone";
        item.append(role, name);
        return item;
      }),
    );
    if (entries.length === 0) {
      const item = document.createElement("li");
      item.className = "unnamed";
      item.textContent = "Nothing: this output says nothing to a screen reader.";
      outlineList.append(item);
    }
  };

  // --- The files beside the document -------------------------------------------------

  const showFile = (file: DocumentFile | undefined): void => {
    if (fileUrl !== undefined) URL.revokeObjectURL(fileUrl);
    fileUrl = undefined;
    if (file === undefined) {
      fileView.replaceChildren();
      return;
    }
    const kind = fileKind(file.path);
    if (kind === "text") {
      const text = document.createElement("pre");
      text.textContent = new TextDecoder().decode(file.bytes);
      fileView.replaceChildren(text);
    } else if (kind === "image") {
      fileUrl = URL.createObjectURL(new Blob([file.bytes.slice()], { type: imageType(file.path) ?? "" }));
      const image = document.createElement("img");
      image.src = fileUrl;
      image.alt = file.path;
      fileView.replaceChildren(image);
    } else {
      const note = document.createElement("p");
      note.textContent =
        kind === "font"
          ? `A font. Letter in it with lettering: {font: ${file.path}}.`
          : "Shown by its name and size only.";
      fileView.replaceChildren(note);
    }
  };

  const showFiles = (): void => {
    const files = listed(compiler?.files() ?? []);
    if (!files.some((file) => file.path === openFile)) openFile = files[0]?.path;
    filesList.replaceChildren(
      ...files.map((file) => {
        const item = document.createElement("li");
        const button = document.createElement("button");
        button.type = "button";
        button.setAttribute("aria-pressed", String(file.path === openFile));
        const path = document.createElement("span");
        path.textContent = file.path;
        const size = document.createElement("span");
        size.className = "size";
        size.textContent = formatSize(file.bytes.length);
        button.append(path, size);
        button.addEventListener("click", () => {
          openFile = file.path;
          showFiles();
        });
        item.append(button);
        return item;
      }),
    );
    if (files.length === 0) {
      const item = document.createElement("li");
      item.className = "unnamed";
      item.textContent = compiler === undefined ? "Starting the compiler…" : "No files beside the document.";
      filesList.append(item);
    }
    showFile(files.find((file) => file.path === openFile));
  };

  // --- Drawing, with the output options ----------------------------------------------

  /** The layout menu: what this document offers, and what is shown. */
  const updateOptionsMenu = (offered: readonly Layout[], shown: string): void => {
    liveTextOption.checked = options.liveText;
    for (const [layout, radio] of Object.entries(layoutOptions)) {
      radio.disabled = !offered.includes(layout as Layout);
      radio.checked = layout === shown;
    }
  };

  /** Draw the last document that compiled as the options say, then show it. */
  const drawNow = async (): Promise<void> => {
    if (compiler === undefined || lastGood === undefined) return;
    const ticket = ++drawing;
    const offered = offeredLayouts({ pages: lastGood.pages, panels: lastGood.panels.length });
    const shown = chosenLayout(options.layout, offered);
    const result = await compiler.render(options.liveText, shown);
    if (ticket !== drawing) return;
    if (!result.ok) {
      setStatus(`Could not draw it: ${result.error}`);
      return;
    }
    pictures = result.pictures;
    updateOptionsMenu(offered, shown);
    render();
  };

  const setOptions = (changed: Partial<OutputOptions>): void => {
    options = { ...options, ...changed };
    saveOptions(store, options);
    void drawNow();
  };

  const clearMarkers = (): void => {
    for (const model of models.values()) {
      monaco.editor.setModelMarkers(model, SCENET_MARKER_OWNER, []);
    }
  };

  /**
   * One finding or note as a line: where it is, its rule, what it says. With a place in the
   * source, the line is a button that puts the cursor there.
   */
  const findingLine = (where: string, rule: string, message: string, at?: Place): HTMLElement => {
    const part = (className: string, text: string): HTMLSpanElement => {
      const span = document.createElement("span");
      span.className = className;
      span.textContent = text;
      return span;
    };
    const parts = [part("where", where), part("rule", rule), part("message", message)];
    if (at === undefined) {
      const line = document.createElement("div");
      line.className = "finding";
      line.append(...parts);
      return line;
    }
    const button = document.createElement("button");
    button.type = "button";
    button.className = "finding";
    button.title = "Show in the editor";
    button.append(...parts);
    button.addEventListener("click", () => {
      editor.setPosition({ lineNumber: at.line, column: at.column });
      editor.revealLineInCenterIfOutsideViewport(at.line);
      editor.focus();
    });
    return button;
  };

  /** Each finding as a line that jumps the editor to where it is. */
  const showFindings = (failure: CompileFailure): void => {
    errorBox.replaceChildren(
      ...failure.findings.map((finding) =>
        findingLine(`${finding.line}:${finding.column}`, finding.rule, finding.message, finding),
      ),
    );
    errorBox.hidden = false;
  };

  /** What the checker and the compiler note, over the picture; hidden when there is nothing. */
  const showNotes = (result: CompileSuccess): void => {
    const rows = noteRows(result.findings, result.notes);
    notes.replaceChildren(
      ...rows.map((row) => findingLine(row.where, row.rule, row.message, row.at)),
    );
    notes.hidden = rows.length === 0;
  };

  const showResult = (result: CompileResult, model: monaco.editor.ITextModel): void => {
    clearMarkers();
    if (result.ok) {
      // Notes, if any: a document that compiles has no error to show.
      monaco.editor.setModelMarkers(model, SCENET_MARKER_OWNER, toMarkers(monaco, result.findings));
      lastGood = result;
      book += 1;
      exportsCache = undefined;
      errorBox.hidden = true;
      errorBox.replaceChildren();
      showNotes(result);
      const count = result.panels.length;
      setStatus(count === 1 ? "Compiled." : `Compiled ${count} panels.`);
      updateDownloads();
      return;
    }
    // The previous panel stays on screen. Blanking it on every keystroke that leaves the
    // source momentarily invalid makes the page flicker while you type.
    monaco.editor.setModelMarkers(model, SCENET_MARKER_OWNER, toMarkers(monaco, result.findings));
    showFindings(result);
    notes.hidden = true;
    const count = result.findings.length;
    setStatus(count === 1 ? "Could not compile: 1 problem." : `Could not compile: ${count} problems.`);
  };

  // --- Compiling ---------------------------------------------------------------------

  /**
   * Put the text in the model whose kind it is.
   *
   * The compiler is told the kind by `detectKind`, but the schema the editor validates
   * against is chosen by the model. Without this, a scene pasted over a panel compiles
   * as a scene and is squiggled as a panel.
   */
  const syncModelKind = (): monaco.editor.ITextModel => {
    const current = editor.getModel() ?? modelFor("panel");
    const detected = detectKind(current.getValue());
    if (detected === kindOf(current)) return current;
    const target = modelFor(detected);
    const state = editor.saveViewState();
    loading = true;
    try {
      target.setValue(current.getValue());
    } finally {
      loading = false;
    }
    monaco.editor.setModelMarkers(current, SCENET_MARKER_OWNER, []);
    editor.setModel(target);
    if (state !== null) editor.restoreViewState(state);
    return target;
  };

  const compileNow = async (): Promise<void> => {
    window.clearTimeout(timer);
    if (compiler === undefined) return; // The boot sequence compiles once it is ready.
    const model = syncModelKind();
    const kind = kindOf(model);
    kindLabel.textContent = KIND_LABEL[kind];
    const ticket = ++generation;
    setStatus("Compiling…", true);
    const result = await compiler.compile(model.getValue(), kind);
    if (ticket !== generation) return;
    showResult(result, model);
    if (result.ok) await drawNow();
  };

  const scheduleCompile = (): void => {
    window.clearTimeout(timer);
    timer = window.setTimeout(() => {
      saveDraft(store, {
        source: editor.getValue(),
        example: origin.from === "shared" ? -1 : origin.index,
      });
      void compileNow();
    }, COMPILE_DELAY_MS);
  };

  // --- Where the text came from ------------------------------------------------------

  const originExample = (): Example | undefined =>
    origin.from === "shared" ? undefined : examples[origin.index];

  /** Previous and Next, from wherever the editor's text came from. */
  const updateWalk = (): void => {
    const { previous, next } = neighbours(order, origin.from === "shared" ? -1 : origin.index);
    for (const [button, index, word] of [
      [previousButton, previous, "Previous"],
      [nextButton, next, "Next"],
    ] as const) {
      const example = index === undefined ? undefined : examples[index];
      button.disabled = example === undefined;
      button.title = example === undefined ? `No ${word.toLowerCase()} example` : `${word}: ${example.title}`;
    }
  };

  /** Under the editor: what the example shows, where to read about it, and whose text it is. */
  const updateBlurb = (): void => {
    const example = originExample();
    summary.textContent = example?.summary ?? "";
    summary.title = example === undefined ? "" : `examples/gallery/${example.file}`;
    docLink.hidden = example === undefined;
    if (example !== undefined) docLink.href = docHref(example.doc);
    if (origin.from === "shared") {
      blurb.textContent = "Opened from a shared link";
    } else if (origin.from === "draft") {
      blurb.textContent = example ? "Your edit, restored" : "Your document, restored";
    } else {
      blurb.textContent = edited ? "Edited" : "";
    }
    resetButton.hidden = origin.from === "example" && !edited;
    resetButton.textContent = example ? "Reset to example" : "Back to the gallery";
    updateWalk();
  };

  const setSource = (text: string, kind: ScenetDocumentKind = detectKind(text)): void => {
    const model = modelFor(kind);
    loading = true;
    try {
      model.setValue(text);
    } finally {
      loading = false;
    }
    if (editor.getModel() !== model) {
      clearMarkers();
      editor.setModel(model);
    }
    kindLabel.textContent = KIND_LABEL[kind];
    // A different document opens fitted. Only edits to the same one keep the zoom.
    viewport.fit();
  };

  /**
   * A link in the address bar -- a share link, or an example's name -- is only true until
   * the first edit. Dropping it is also what lets a reload restore the draft.
   */
  const dropLink = (): void => {
    if (tokenFromHash(location.hash) !== undefined || exampleNameFromHash(location.hash) !== undefined) {
      history.replaceState(null, "", location.pathname + location.search);
    }
  };

  /** Ask before throwing away edits that only exist in this tab. */
  const mayDiscard = (): boolean =>
    !edited || window.confirm("Discard your changes to this document?");

  /**
   * Open a gallery example, and name it in the address bar so the address links to it.
   *
   * Opened from such a link as the page loads, the draft is kept, as it is for a share
   * link: the visitor never chose to discard it. The first edit replaces it anyway.
   */
  const loadExample = (index: number, { keepDraft = false } = {}): void => {
    const example = examples[index];
    if (example === undefined) return;
    setSource(example.source, example.kind);
    origin = { from: "example", index };
    edited = false;
    exampleSelect.value = String(index);
    if (!keepDraft) clearDraft(store);
    history.replaceState(null, "", location.pathname + location.search + exampleHash(example.file));
    updateBlurb();
    void compileNow();
  };

  /** Open the example a `#example=` fragment names; false if it names none the gallery has. */
  const openNamedExample = (): boolean => {
    const name = exampleNameFromHash(location.hash);
    if (name === undefined) return false;
    const index = exampleIndex(examples, name);
    if (index === undefined) {
      missingExample = name;
      setStatus(`The gallery has no example called ${name}.`);
      return false;
    }
    loadExample(index, { keepDraft: true });
    return true;
  };

  /** Previous or Next: the example beside this one, in the order the menu shows. */
  const walk = (step: "previous" | "next"): void => {
    const index = neighbours(order, origin.from === "shared" ? -1 : origin.index)[step];
    if (index !== undefined && mayDiscard()) loadExample(index);
  };

  const openSharedLink = async (): Promise<boolean> => {
    const token = tokenFromHash(location.hash);
    if (token === undefined) return false;
    try {
      setSource(await decodeSource(token));
    } catch {
      setStatus("That link could not be opened: it is damaged or incomplete.");
      return false;
    }
    origin = { from: "shared" };
    edited = false;
    exampleSelect.selectedIndex = -1;
    updateBlurb();
    void compileNow();
    return true;
  };

  // --- Downloads, sharing, full screen -----------------------------------------------

  const updateDownloads = (): void => {
    // One panel's exports are five files; a document of several has them all in one ZIP.
    const several = (lastGood?.panels.length ?? 0) > 1;
    for (const button of downloadMenu.querySelectorAll<HTMLButtonElement>("[data-download]")) {
      const what = button.dataset["download"] ?? "";
      button.disabled = what !== "source" && lastGood === undefined;
      if (CONDITIONING.some((exported) => exported.suffix === what)) button.hidden = several;
      if (what === "conditioning") button.hidden = !several;
    }
  };

  /** What the Panel or Overlay tab shows, as one document. */
  const shownSvg = (debug: boolean): string =>
    composeMaps(pictures.map((shown) => ({ name: shown.name, svg: debug ? shown.debug : shown.svg })));

  const save = async (what: string): Promise<void> => {
    const stem = stemFor(originExample()?.file);
    if (what === "source") {
      const model = editor.getModel() ?? modelFor("panel");
      download(sourceFilename(stem, kindOf(model)), textBlob(model.getValue()));
      return;
    }
    if (lastGood === undefined) {
      setStatus("Nothing has compiled yet, so there is nothing to download.");
      return;
    }
    if (what === "svg") download(`${stem}.svg`, svgBlob(shownSvg(false)));
    if (what === "debug") download(`${stem}.debug.svg`, svgBlob(shownSvg(true)));
    if (what === "core") download(`${stem}.core.json`, textBlob(lastGood.core, "application/json"));
    if (CONDITIONING.some((exported) => exported.suffix === what)) {
      const [only] = (await panelExports()) ?? [];
      const exported = only?.files[what];
      if (only === undefined || exported === undefined) return;
      const model = editor.getModel() ?? modelFor("panel");
      const panel = kindOf(model) === "panel" ? undefined : only.panel;
      const { filename, type } = conditioningFile(stem, what, panel);
      download(filename, textBlob(exported, type));
    }
    if (what === "conditioning" && compiler !== undefined) {
      const bytes = await compiler.archive(stem);
      download(`${stem}.conditioning.zip`, new Blob([bytes.slice()], { type: "application/zip" }));
    }
    if (what === "png") {
      setStatus("Rendering PNG…", true);
      try {
        download(`${stem}.png`, await svgToPng(shownSvg(false)));
        setStatus("PNG saved.");
      } catch (error: unknown) {
        setStatus(`Could not make a PNG: ${error instanceof Error ? error.message : String(error)}`);
      }
    }
  };

  const share = async (): Promise<void> => {
    const url = shareUrl(location.href, await encodeSource(editor.getValue()));
    history.replaceState(null, "", url);
    try {
      await navigator.clipboard.writeText(url);
      setStatus("Link copied. Anyone who opens it sees this document.");
    } catch {
      setStatus("The link is in the address bar, ready to copy.");
    }
  };

  const setMaximized = (on: boolean): void => {
    outputPane.classList.toggle("maximized", on);
    syncFullscreenButton(on);
  };
  const syncFullscreenButton = (on: boolean): void => {
    fullscreenButton.setAttribute("aria-pressed", String(on));
    fullscreenButton.title = on ? "Exit full screen (Esc)" : "Full screen";
  };
  const toggleFullscreen = (): void => {
    if (document.fullscreenElement !== null) {
      void document.exitFullscreen();
    } else if (outputPane.classList.contains("maximized")) {
      setMaximized(false);
    } else if (document.fullscreenEnabled) {
      // Falls back to filling the window where the request is refused, as an iframe
      // without `allowfullscreen` does.
      outputPane.requestFullscreen().catch(() => setMaximized(true));
    } else {
      setMaximized(true);
    }
  };

  // --- Wiring ------------------------------------------------------------------------

  editor.onDidChangeModelContent(() => {
    if (loading) return;
    if (!edited) {
      edited = true;
      updateBlurb();
    }
    dropLink();
    scheduleCompile();
  });

  exampleSelect.addEventListener("change", () => {
    if (!mayDiscard()) {
      // Put the selection back to what the editor actually holds.
      if (origin.from === "shared") exampleSelect.selectedIndex = -1;
      else exampleSelect.value = String(origin.index);
      return;
    }
    loadExample(Number(exampleSelect.value));
  });

  resetButton.addEventListener("click", () => {
    if (!mayDiscard()) return;
    loadExample(origin.from === "shared" || examples[origin.index] === undefined ? start : origin.index);
  });

  previousButton.addEventListener("click", () => walk("previous"));
  nextButton.addEventListener("click", () => walk("next"));

  shareButton.addEventListener("click", () => void share());

  // A font the author adds goes into the document's fonts/ folder, where
  // `lettering: {font: fonts/Name.ttf}` finds it. It is not kept across reloads, and a
  // share link does not carry it: say both, since neither is visible otherwise.
  const addFonts = async (): Promise<void> => {
    if (compiler === undefined) return;
    const added: string[] = [];
    for (const file of Array.from(fontInput.files ?? [])) {
      const name = fontFileName(file.name);
      if (name === null) continue;
      compiler.addFont(name, new Uint8Array(await file.arrayBuffer()));
      added.push(declaredPath(name));
    }
    fontInput.value = "";
    if (added.length === 0) {
      setStatus("A font must be a .ttf or .otf file.");
      return;
    }
    await compileNow();
    if (view === "files") render();
    setStatus(
      `Added ${added.join(", ")}. Letter in it with lettering: {font: ${added[0]}}. ` +
        "Fonts stay in this tab only: a reload or a share link does not keep them.",
    );
  };
  addFontButton.addEventListener("click", () => fontInput.click());
  fontInput.addEventListener("change", () => void addFonts());

  // A picture the author adds goes into the document's art/ folder, where
  // `setting: {image: art/Name.png}` finds it. Like a font, it is not kept across reloads
  // and a share link does not carry it; the preview and the downloads embed it.
  const addImages = async (): Promise<void> => {
    if (compiler === undefined) return;
    const added: string[] = [];
    for (const file of Array.from(imageInput.files ?? [])) {
      const name = imageFileName(file.name);
      if (name === null) continue;
      const path = declaredImagePath(name);
      compiler.addFile(path, new Uint8Array(await file.arrayBuffer()));
      added.push(path);
    }
    imageInput.value = "";
    if (added.length === 0) {
      setStatus("A picture must be a .png or .jpg file, and its artwork contract a .art.yaml.");
      return;
    }
    await compileNow();
    if (view === "files") render();
    const picture = added.find((path) => !isContract(path));
    const contract = added.find((path) => isContract(path));
    const how =
      picture !== undefined
        ? `Letter over it with setting: {image: ${picture}}.`
        : `Its picture goes beside it, named after it; cast its figures with figure:.`;
    setStatus(
      `Added ${added.join(", ")}. ${how}` +
        (picture !== undefined && contract !== undefined ? " Cast its figures with figure:." : "") +
        " Pictures stay in this tab only: a reload or a share link does not keep them.",
    );
  };
  addImageButton.addEventListener("click", () => imageInput.click());
  imageInput.addEventListener("change", () => void addImages());

  for (const [name, button] of Object.entries(tabs)) {
    button.addEventListener("click", () => {
      view = name as View;
      render();
    });
  }

  element<HTMLButtonElement>("zoom-in").addEventListener("click", () => viewport.zoomIn());
  element<HTMLButtonElement>("zoom-out").addEventListener("click", () => viewport.zoomOut());
  element<HTMLButtonElement>("zoom-fit").addEventListener("click", () => viewport.fit());
  zoomLevel.addEventListener("click", () => viewport.actualSize());

  downloadMenu.addEventListener("click", (event) => {
    const button = (event.target as HTMLElement).closest<HTMLButtonElement>("[data-download]");
    if (button === null) return;
    downloadMenu.open = false;
    void save(button.dataset["download"] ?? "");
  });
  liveTextOption.addEventListener("change", () => setOptions({ liveText: liveTextOption.checked }));
  for (const [layout, radio] of Object.entries(layoutOptions)) {
    radio.addEventListener("change", () => {
      if (radio.checked) setOptions({ layout: layout as Layout });
    });
  }
  const menus = [downloadMenu, optionsMenu];
  document.addEventListener("click", (event) => {
    for (const menu of menus) {
      if (menu.open && !menu.contains(event.target as Node)) menu.open = false;
    }
  });

  fullscreenButton.addEventListener("click", toggleFullscreen);
  document.addEventListener("fullscreenchange", () =>
    syncFullscreenButton(document.fullscreenElement === outputPane),
  );

  window.addEventListener(
    "keydown",
    (event) => {
      // Ctrl/Cmd+S saves the source rather than the page, which would save the editor.
      if ((event.ctrlKey || event.metaKey) && !event.altKey && event.key.toLowerCase() === "s") {
        event.preventDefault();
        void save("source");
      } else if (event.key === "Escape") {
        for (const menu of menus) menu.open = false;
        if (outputPane.classList.contains("maximized")) setMaximized(false);
      }
    },
    { capture: true },
  );

  // A link pasted into this tab's address bar changes only the fragment.
  window.addEventListener("hashchange", () => {
    if (tokenFromHash(location.hash) !== undefined) {
      if (mayDiscard()) void openSharedLink();
    } else if (exampleNameFromHash(location.hash) !== undefined) {
      if (mayDiscard()) openNamedExample();
    }
  });

  // --- Start -------------------------------------------------------------------------
  //
  // The document goes into the editor first; the compiler boots behind it. Booting
  // takes ten to twenty seconds on a first visit, and an empty editor for that long
  // reads as a broken page.

  // A share link first, then an example named in the address, then the draft, and
  // otherwise the gallery's opening example.
  updateDownloads();
  if (!(await openSharedLink()) && !openNamedExample()) {
    const draft = loadDraft(store);
    if (draft !== undefined && draft.source.trim() !== "") {
      setSource(draft.source);
      origin = { from: "draft", index: draft.example };
      edited = true;
      if (examples[draft.example] === undefined) exampleSelect.selectedIndex = -1;
      else exampleSelect.value = String(draft.example);
      updateBlurb();
    } else {
      loadExample(start);
    }
  }
  render();

  setStatus("Starting the compiler…", true);
  try {
    compiler = await bootCompiler((message) => setStatus(message, true));
  } catch (error: unknown) {
    setStatus("Failed to start.");
    errorBox.hidden = false;
    errorBox.textContent = error instanceof Error ? error.message : String(error);
    return;
  }

  document.title = `Scenet ${compiler.version} playground`;
  // Every picture an example is lettered over, beside the document, before the first
  // compile: a restored draft or a shared link may name one as well as the example does.
  for (const file of exampleFiles(examples)) compiler.addFile(file.path, file.bytes);
  await compileNow();
  if (missingExample !== undefined) {
    setStatus(`The gallery has no example called ${missingExample}, so this opened instead.`);
  }
}

void main();
