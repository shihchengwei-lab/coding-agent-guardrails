/// A tiny in-memory notes model. Fixture for the dependency gate — there is no
/// Dart toolchain here, so this is read/edited, not executed.
class Note {
  final int id;
  final String text;
  final DateTime createdAt;
  Note(this.id, this.text, this.createdAt);
}

class Notes {
  final List<Note> _notes = [];

  Note add(String text) {
    final id = _notes.isEmpty ? 1 : _notes.last.id + 1;
    final note = Note(id, text, DateTime.now());
    _notes.add(note);
    return note;
  }

  List<Note> list() => List.unmodifiable(_notes);
}
