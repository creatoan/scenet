import assert from "node:assert/strict";
import { test } from "node:test";

import { PUPPET_FOLDER, PUPPET_SUFFIX, declaredPuppetPath, puppetFileName } from "./puppets.ts";

test("a puppet keeps its own name, so the document can name it as the author sees it", () => {
  assert.equal(puppetFileName("pip.puppet.yaml"), "pip.puppet.yaml");
  assert.equal(puppetFileName("Old-Tom.puppet.yaml"), "Old-Tom.puppet.yaml");
  // The suffix in lower case, since that is what a reference names a file by.
  assert.equal(puppetFileName("PIP.PUPPET.YAML"), `PIP${PUPPET_SUFFIX}`);
});

test("only the file's own name is kept, never a folder it came from", () => {
  assert.equal(puppetFileName("C:\\Users\\me\\Puppets\\pip.puppet.yaml"), "pip.puppet.yaml");
  assert.equal(puppetFileName("../../etc/pip.puppet.yaml"), "pip.puppet.yaml");
});

test("characters a path, a link or a YAML value would trip on become hyphens", () => {
  assert.equal(puppetFileName("pip (1).puppet.yaml"), "pip--1-.puppet.yaml");
  assert.equal(puppetFileName("my kid: #2.puppet.yaml"), "my-kid---2.puppet.yaml");
});

test("a file that is not a puppet is refused", () => {
  assert.equal(puppetFileName("pip.yaml"), null);
  assert.equal(puppetFileName("street.art.yaml"), null);
  assert.equal(puppetFileName("one.panel.yaml"), null);
  assert.equal(puppetFileName("pip.puppet.yml"), null);
  assert.equal(puppetFileName(".puppet.yaml"), null);
  assert.equal(puppetFileName(""), null);
});

test("an added puppet is named relative to the document, as one beside it would be", () => {
  assert.equal(PUPPET_FOLDER, "puppets");
  assert.equal(declaredPuppetPath("pip.puppet.yaml"), "puppets/pip.puppet.yaml");
});
