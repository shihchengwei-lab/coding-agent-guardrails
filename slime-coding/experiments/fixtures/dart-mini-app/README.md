# fixture: dart-mini-app

Minimal Dart-shaped fixture whose only purpose is to exercise the Slime Coding
**dependency gate**, which parses `pubspec.yaml`. There is no Dart toolchain in
CI/this environment, so the code is read and edited but not executed; the
dependency gate works purely on the `pubspec.yaml` diff vs HEAD.

`reset.sh` restores the committed baseline.
