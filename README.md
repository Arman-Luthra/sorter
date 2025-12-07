# [sorter]

A fast PDF sorting tool. Load PDFs from a source folder, preview them as scrollable grayscale images, and sort them into one of two destination folders using keyboard shortcuts. Sorted files are tracked with color-coded indicators.

## Requirements

- Python 3.8+
- pip

## Installation

```
pip install -r requirements.txt
```

## Running

```
python -m uvicorn main:app --port 8000
```

Then open http://localhost:8000 in your browser.

## Usage

1. Click Browse to select source folder (containing PDFs)
2. Click Browse to select destination folder 1
3. Click Browse to select destination folder 2
4. Click Load to scan PDFs
5. Use keyboard shortcuts to sort

## Keyboard shortcuts

| Key | Action |
|-----|--------|
| Left arrow | Sort to folder 1 |
| Right arrow | Sort to folder 2 |
| Up arrow | Previous file |
| Down arrow | Next file |
| Z | Undo last sort |

## Platform support

Works on macOS, Windows, and Linux.

