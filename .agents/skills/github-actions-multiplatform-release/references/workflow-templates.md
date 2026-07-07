# GitHub Actions Multiplatform Release — Workflow Templates

Each template below is a complete, copy-pasteable `.github/workflows/release.yml` file.

## Generic (Makefile / script-based)

```yaml
name: Release

on:
  push:
    tags: ['v*']

permissions:
  contents: write

jobs:
  build:
    name: Build (${{ matrix.os }})
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
      fail-fast: false

    steps:
      - uses: actions/checkout@v4

      - name: Build
        shell: bash
        run: |
          mkdir -p dist
          if [ "${{ runner.os }}" = "Linux" ]; then
            make build-linux
            cp build/myapp dist/myapp-linux
          elif [ "${{ runner.os }}" = "macOS" ]; then
            make build-macos
            cp build/myapp dist/myapp-macos
          else
            make build-windows
            cp build/myapp.exe dist/myapp-windows.exe
          fi

      - uses: actions/upload-artifact@v4
        with:
          name: myapp-${{ runner.os }}
          path: dist/*

  release:
    name: Create Release
    needs: build
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/download-artifact@v4

      - name: Set executable permissions
        run: |
          chmod +x myapp-Linux/myapp-linux
          chmod +x myapp-macOS/myapp-macos

      - uses: softprops/action-gh-release@v2
        with:
          files: |
            myapp-Linux/myapp-linux
            myapp-macOS/myapp-macos
            myapp-Windows/myapp-windows.exe
          generate_release_notes: true
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

## Go

```yaml
name: Release

on:
  push:
    tags: ['v*']

permissions:
  contents: write

jobs:
  build:
    name: Build (${{ matrix.os }})
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
      fail-fast: false

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with:
          go-version: '1.22'

      - name: Build
        shell: bash
        run: |
          GOOS=${{ matrix.os == 'ubuntu-latest' && 'linux' || matrix.os == 'macos-latest' && 'darwin' || 'windows' }}
          EXT=${{ runner.os == 'Windows' && '.exe' || '' }}
          mkdir -p dist
          GOOS=$GOOS GOARCH=amd64 CGO_ENABLED=0 go build -ldflags="-s -w" -o dist/myapp-$GOOS-amd64$EXT .

      - uses: actions/upload-artifact@v4
        with:
          name: artifact-${{ runner.os }}
          path: dist/*

  release:
    name: Create Release
    needs: build
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/download-artifact@v4

      - name: Set executable permissions
        run: |
          chmod +x artifact-Linux/*
          chmod +x artifact-macOS/*

      - uses: softprops/action-gh-release@v2
        with:
          files: artifact-*/*
          generate_release_notes: true
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

## Rust

```yaml
name: Release

on:
  push:
    tags: ['v*']

permissions:
  contents: write

jobs:
  build:
    name: Build (${{ matrix.target }})
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        include:
          - os: ubuntu-latest
            target: x86_64-unknown-linux-gnu
          - os: macos-latest
            target: aarch64-apple-darwin
          - os: macos-13
            target: x86_64-apple-darwin
          - os: windows-latest
            target: x86_64-pc-windows-msvc
      fail-fast: false

    steps:
      - uses: actions/checkout@v4
      - uses: dtolnay/rust-toolchain@stable
        with:
          targets: ${{ matrix.target }}

      - name: Build
        run: cargo build --release --target ${{ matrix.target }}

      - name: Package (Unix)
        if: runner.os != 'Windows'
        shell: bash
        run: |
          mkdir -p dist
          cp target/${{ matrix.target }}/release/myapp dist/
          tar -czf dist/myapp-${{ matrix.target }}.tar.gz -C dist myapp

      - name: Package (Windows)
        if: runner.os == 'Windows'
        shell: bash
        run: |
          mkdir -p dist
          cp target/${{ matrix.target }}/release/myapp.exe dist/
          7z a dist/myapp-${{ matrix.target }}.zip ./dist/myapp.exe

      - uses: actions/upload-artifact@v4
        with:
          name: artifact-${{ matrix.target }}
          path: |
            dist/*.tar.gz
            dist/*.zip

  release:
    name: Create Release
    needs: build
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/download-artifact@v4
      - uses: softprops/action-gh-release@v2
        with:
          files: artifact-*/*
          generate_release_notes: true
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

## Python (PyInstaller)

```yaml
name: Release

on:
  push:
    tags: ['v*']

permissions:
  contents: write

jobs:
  build:
    name: Build (${{ matrix.os }})
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
      fail-fast: false

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install pyinstaller
          pip install -r requirements.txt

      - name: Build with PyInstaller
        shell: bash
        run: |
          pyinstaller --onefile --name myapp main.py
          mkdir -p dist/release
          if [ "${{ runner.os }}" = "Windows" ]; then
            mv dist/myapp.exe dist/release/
          else
            mv dist/myapp dist/release/
          fi

      - uses: actions/upload-artifact@v4
        with:
          name: myapp-${{ runner.os }}
          path: dist/release/*

  release:
    name: Create Release
    needs: build
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/download-artifact@v4

      - name: Set executable permissions
        run: |
          chmod +x myapp-Linux/* || true
          chmod +x myapp-macOS/* || true

      - uses: softprops/action-gh-release@v2
        with:
          files: myapp-*/*
          generate_release_notes: true
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

## Node.js (pkg / nexe)

```yaml
name: Release

on:
  push:
    tags: ['v*']

permissions:
  contents: write

jobs:
  build:
    name: Build (${{ matrix.os }})
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
      fail-fast: false

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'

      - name: Install dependencies
        run: npm ci

      - name: Build with pkg
        shell: bash
        run: |
          npx pkg . --targets node20-${{ matrix.os == 'ubuntu-latest' && 'linux-x64' || matrix.os == 'macos-latest' && 'macos-x64' || 'win-x64' }} --output dist/myapp${{ runner.os == 'Windows' && '.exe' || '' }}

      - uses: actions/upload-artifact@v4
        with:
          name: myapp-${{ runner.os }}
          path: dist/*

  release:
    name: Create Release
    needs: build
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/download-artifact@v4

      - name: Set executable permissions
        run: |
          chmod +x myapp-Linux/* || true
          chmod +x myapp-macOS/* || true

      - uses: softprops/action-gh-release@v2
        with:
          files: myapp-*/*
          generate_release_notes: true
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

## GoReleaser (minimal)

For Go projects, `goreleaser` is the idiomatic choice and drastically reduces boilerplate. Initialize with `goreleaser init` and use this workflow:

```yaml
name: Release

on:
  push:
    tags: ['v*']

permissions:
  contents: write

jobs:
  goreleaser:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # required — a shallow checkout breaks changelog generation
      - uses: actions/setup-go@v5
        with:
          go-version: '1.22'
      - uses: goreleaser/goreleaser-action@v7
        with:
          distribution: goreleaser
          version: '~> v2'
          args: release --clean
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

Note: You must commit a `.goreleaser.yaml` configuration file. The default handles Linux/macOS/Windows binaries, archives, checksums, and a Homebrew formula automatically.
