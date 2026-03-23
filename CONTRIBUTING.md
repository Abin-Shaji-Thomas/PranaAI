# Contributing to PranaAI

Thanks for your interest in improving PranaAI.

## Ways to Contribute

- Report bugs
- Suggest enhancements
- Improve documentation
- Submit code fixes and features

## Before You Start

1. Check existing issues to avoid duplicates.
2. Open an issue for major changes before coding.
3. Keep pull requests focused and small.

## Reporting Bugs

Please include:

- Clear title and summary
- Steps to reproduce
- Expected behavior
- Actual behavior
- Logs, screenshots, or error traces if available
- Environment details (OS, Python version)

## Development Setup

1. Fork and clone the repository.
2. Create a virtual environment.
3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Run the app locally:

```bash
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload
```

5. Run tests:

```bash
python -m unittest tests/test_core_pipeline.py
```

## Pull Request Guidelines

- Use clear commit messages.
- Reference related issues (for example: `Fixes #123`).
- Add tests for behavioral changes when practical.
- Update documentation when changing functionality.
- Ensure tests pass before requesting review.

## Code Style

- Follow existing project structure and naming conventions.
- Keep changes minimal and relevant to the issue.
- Avoid unrelated refactors in the same PR.
