---
name: github-actions-multiplatform-release
description: Set up GitHub Actions workflows for multiplatform builds (Linux, macOS, Windows) that publish artifacts to GitHub Releases. Use when asked to create a CI/CD release pipeline, cross-platform deployment, publish binaries to Releases, automate multiplatform builds, or generate release assets on tag push.
---

# GitHub Actions Multiplatform Release

Build and publish release artifacts for Linux, macOS, and Windows using a single GitHub Actions workflow triggered by tag pushes. The workflow builds in parallel via a matrix strategy and uploads binaries to the GitHub Releases page.

## Workflow overview

1. **Trigger**: push of a tag (e.g. `v1.0.0`).
2. **Matrix build**: run in parallel on `ubuntu-latest`, `macos-latest`, `windows-latest`.
3. **Build**: compile or package the project per platform. Use conditional `runner.os` checks for OS-specific commands.
4. **Upload artifact**: use `actions/upload-artifact` to preserve the built binary from each matrix job.
5. **Create release + publish**: a separate job (gated on all matrix jobs finishing) creates a GitHub Release and attaches all artifacts as downloadable assets.

## Building the workflow

### 1. Trigger on tags

```yaml
on:
  push:
    tags: ['v*']
```

### 2. Matrix strategy

```yaml
strategy:
  matrix:
    os: [ubuntu-latest, macos-latest, windows-latest]
  fail-fast: false
```

`fail-fast: false` ensures one platform failing does not cancel the others.

### 3. Conditional build commands

Use `if: runner.os == 'Linux'` (or `macOS` / `Windows`) to run OS-specific logic. Common patterns:

```yaml
- name: Build (Linux)
  if: runner.os == 'Linux'
  run: make build-linux

- name: Build (macOS)
  if: runner.os == 'macOS'
  run: make build-macos

- name: Build (Windows)
  if: runner.os == 'Windows'
  run: make build-windows
```

For cross-compilation languages (Go, Rust), you can often use a single step with environment variables:

```yaml
- name: Build Go binary
  run: |
    GOOS=${{ matrix.os == 'ubuntu-latest' && 'linux' || matrix.os == 'macos-latest' && 'darwin' || 'windows' }} \
    GOARCH=amd64 \
    go build -o dist/myapp${{ runner.os == 'Windows' && '.exe' || '' }} .
  shell: bash
```

### 4. Upload per-platform artifact

Name the artifact uniquely per OS so the release job can distinguish them:

```yaml
- uses: actions/upload-artifact@v4
  with:
    name: myapp-${{ runner.os }}
    path: dist/*
```

### 5. Create GitHub Release and attach assets

Use a dedicated job that runs after all matrix builds complete:

```yaml
release:
  needs: build
  runs-on: ubuntu-latest
  permissions:
    contents: write
  steps:
    - uses: actions/download-artifact@v4
    - run: ls -R   # inspect downloaded artifact folders
    - uses: softprops/action-gh-release@v2
      with:
        files: myapp-*/myapp*
        generate_release_notes: true
      env:
        GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

Key points:
- `needs: build` ensures matrix jobs finish first.
- `permissions.contents: write` is required to create the release.
- `softprops/action-gh-release@v2` handles both draft release creation and asset upload. Use `generate_release_notes: true` to auto-populate changelog. A v3 of the action exists (requires a Node 24-compatible Actions runtime); stick with v2 (last line: v2.6.2) if you need Node 20 compatibility, otherwise v3 is fine.
- `files` accepts a glob; adjust to match your artifact names.

## Multiplatform edge cases

### Linux

- **Musl vs glibc**: If your binary depends on glibc, use `ubuntu-latest` directly. For wider compatibility (e.g. Alpine), cross-compile with musl or build in an Alpine container.
- **File permissions**: Bash scripts and binaries lose the execute bit in artifact uploads. Add a post-download step: `chmod +x myapp-linux/myapp`.

### macOS

- **Universal vs arch-specific binaries**: `macos-latest` currently runs on Apple Silicon (arm64). If you need x86_64 binaries, add `macos-13` to your matrix. Note: GitHub has announced that Intel (x86_64) macOS runner images are being phased out and will stop being supported once the macOS 15 image retires (currently slated for Fall 2027) — treat `macos-13` as a shrinking option and plan to drop x86_64 macOS builds eventually.
- **Code signing & notarization**: Binaries downloaded from GitHub Releases will trigger Gatekeeper warnings unless signed and notarized. This is optional but recommended for distribution to non-technical users. Use `apple-actions/import-codesign-certs` and `xcrun notarytool` for notarization.
- **Quarantine attribute**: Downloaded macOS binaries get the `com.apple.quarantine` extended attribute. Users must run `xattr -d com.apple.quarantine myapp` or right-click > Open to bypass. Signing eliminates this.

### Windows

- **File extension**: Always add `.exe` to Windows binaries. Use `${{ runner.os == 'Windows' && '.exe' || '' }}` in your build step.
- **Shell selection**: Set `shell: bash` explicitly on Windows steps that use POSIX syntax (conditionals, variable expansion). The default is PowerShell.
- **Path separators**: Use forward slashes in cross-platform YAML; GitHub Actions normalizes them. Avoid hardcoding `\`.
- **Defender / AV**: First-time downloads may trigger SmartScreen warnings. Signing with an EV code signing certificate mitigates this.

### Cross-cutting

- **Asset naming convention**: Use a consistent pattern: `myapp-<version>-<os>-<arch>.{tar.gz,zip}`. Example: `myapp-v1.0.0-linux-amd64.tar.gz`.
- **Archive format**: Linux/macOS users expect `.tar.gz`, Windows users expect `.zip`. Archive before uploading to the release.
- **GoReleaser alternative**: For Go projects, `goreleaser/goreleaser-action` handles all of the above (cross-compilation, archiving, release upload) in one step. Prefer it over a manual workflow when the project is in Go. Use `goreleaser/goreleaser-action@v7` (current latest major) and always pair it with `actions/checkout@v4` using `fetch-depth: 0` — a shallow checkout breaks GoReleaser's changelog generation.
- **Testing artifacts**: Run a smoke test on each platform after the build step before uploading the artifact.

## Full workflow templates

Complete copy-pasteable YAML workflows for various language ecosystems are in `references/workflow-templates.md`. Load that file when the user needs a ready-to-use template for Go, Rust, Python, Node.js, or a generic Makefile-based project.
