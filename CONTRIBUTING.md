# Contributing to PiMon

Contributions are welcome. Please follow these guidelines to keep the project consistent and maintainable.

## Getting Started

1. Fork the repository and clone your fork.
2. Create a virtual environment and install dependencies:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and configure for your development environment.

## Development Workflow

1. Create a feature branch from `main`:
   ```bash
   git checkout -b feat/my-feature
   ```
2. Make your changes, committing each logical unit separately.
3. Ensure all existing functionality still works.
4. Push your branch and open a pull request.

## Commit Messages

Follow conventional commit format with scope:

```
feat(scope): short description

Longer body explaining what was done and why.
List specifics where helpful.
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`

## Code Style

- Python 3.11+ type hints throughout.
- British English in all documentation, comments, and user-facing text.
- No emojis anywhere in the codebase.
- Keep functions focused and well-documented with docstrings.
- Comments should explain *why*, not *what* (the code should be self-explanatory).

## Documentation

- Update the README if your change adds, modifies, or removes any feature.
- Update `.env.example` if you add new configuration options.
- Update the CLI `--help` text if you add or change commands.

## Security

- Never commit credentials, tokens, or secrets.
- Report security vulnerabilities privately (see SECURITY.md).
- Use placeholder values in examples (e.g. `your-email@example.com`).

## Licence

By contributing, you agree that your contributions will be licensed under the MIT Licence.
