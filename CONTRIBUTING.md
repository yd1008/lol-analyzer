# Contributing to LoL Performance Analyzer

Thank you for your interest in contributing to LoL Performance Analyzer! We welcome contributions from the community.

## How to Contribute

### Reporting Issues
- Search existing issues before creating a new one
- Use a clear, descriptive title
- Provide detailed steps to reproduce the issue
- Include expected vs actual behavior
- Add screenshots or error messages if applicable

### Feature Requests
- Explain the feature and its benefits
- Provide use cases and examples
- Consider potential implementation challenges

### Pull Requests
- Fork the repository
- Create a feature branch: `git checkout -b feature/amazing-feature`
- Make your changes
- Run tests and ensure code quality
- Submit a clear pull request with detailed description

## Development Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/yd1008/lol-analyzer.git
   cd lol-analyzer
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up configuration**
   - Copy `.env.example` to `.env`
   - Add your API keys and environment settings

4. **Run tests**
   ```bash
   python -m pytest
   ```

5. **Local CI checks (recommended)**
   ```bash
   python -m pytest tests/
   ```
   - Keep PRs small and rerun checks locally before opening or updating a PR.

## Code Style

- Follow PEP 8 guidelines
- Add comments for complex logic
- Update documentation for new features
- Write meaningful commit messages

## Code of Conduct

- Be respectful and inclusive
- Provide constructive feedback
- Focus on the issue, not the person

## Questions?

- Open an issue for discussion
- Check existing documentation
- Reach out via GitHub Issues

Thank you for contributing! 🎮
