// A tiny in-memory notes model. Pure functions over an array of notes.
function addNote(notes, text) {
  const id = notes.length ? notes[notes.length - 1].id + 1 : 1;
  return [...notes, { id, text, createdAt: Date.now() }];
}

function listNotes(notes) {
  return notes.map((n) => `${n.id}\t${n.text}`).join("\n");
}

module.exports = { addNote, listNotes };
