const test = require("node:test");
const assert = require("node:assert");
const { addNote, listNotes } = require("../src/notes");

test("add then list (insertion order)", () => {
  let notes = [];
  notes = addNote(notes, "hello");
  notes = addNote(notes, "world");
  assert.equal(notes.length, 2);
  const out = listNotes(notes);
  assert.ok(out.includes("hello") && out.includes("world"));
  assert.ok(out.indexOf("hello") < out.indexOf("world"));
});

test("list empty", () => {
  assert.equal(listNotes([]), "");
});
