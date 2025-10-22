# Contributing to FOSSBilling Core Modules

Thank you for your interest in contributing to FOSSBilling Core Modules! This document provides guidelines for adding and maintaining modules in this monorepo.

## Table of Contents

- [Adding a New Module](#adding-a-new-module)
- [Module Structure Requirements](#module-structure-requirements)
- [Code Standards](#code-standards)
- [Testing Requirements](#testing-requirements)
- [Submitting Changes](#submitting-changes)

## Adding a New Module

To add a new module to this repository:

1. **Create a new directory** under `modules/` with a descriptive name:
   ```
   modules/your-module-name/
   ```

2. **Use lowercase with hyphens** for directory names (e.g., `payment-gateway`, `email-service`)

3. **Ensure the module is self-contained** - all dependencies, configuration, and documentation should be within the module directory

4. **Follow the module structure requirements** outlined below

## Module Structure Requirements

> **Tip:** You can use the templates in `.github/` as a starting point:
> - [MODULE_TEMPLATE.md](.github/MODULE_TEMPLATE.md) for README.md
> - [CHANGELOG_TEMPLATE.md](.github/CHANGELOG_TEMPLATE.md) for CHANGELOG.md

Each module directory must include:

### Required Files

- **README.md** - Comprehensive documentation including:
  - Module description and purpose
  - Installation instructions
  - Configuration options
  - Usage examples
  - API documentation (if applicable)
  - Troubleshooting guide

- **LICENSE** - License information for the module
  - Preferably use an open-source license compatible with FOSSBilling
  - Clearly state any third-party dependencies and their licenses

- **CHANGELOG.md** - Version history and changes
  - Follow [Keep a Changelog](https://keepachangelog.com/) format
  - Use semantic versioning

### Recommended Files

- **composer.json** (for PHP modules) - Dependency management
- **package.json** (for JavaScript modules) - Dependency management
- **.gitignore** - Module-specific ignored files
- **tests/** - Directory containing module tests
- **docs/** - Additional documentation (if needed)

### Example Module Structure

```
modules/example-module/
├── README.md           # Module documentation
├── LICENSE            # License file
├── CHANGELOG.md       # Version history
├── composer.json      # PHP dependencies (if applicable)
├── .gitignore         # Module-specific ignores
├── src/               # Source code
│   └── ...
├── tests/             # Test files
│   └── ...
└── docs/              # Additional documentation
    └── ...
```

## Code Standards

### General Guidelines

- **Code Quality**: Write clean, maintainable, and well-documented code
- **Naming Conventions**: Use clear, descriptive names for files, classes, and functions
- **Comments**: Add comments for complex logic, but prefer self-documenting code
- **Dependencies**: Minimize external dependencies; document all required dependencies

### PHP Modules

- Follow [PSR-12](https://www.php-fig.org/psr/psr-12/) coding standards
- Use proper namespacing
- Include type hints where applicable
- Follow FOSSBilling's existing patterns and conventions

### JavaScript Modules

- Use modern JavaScript (ES6+)
- Follow consistent formatting (consider using Prettier)
- Include JSDoc comments for public APIs

## Testing Requirements

- **Unit Tests**: Include unit tests for core functionality
- **Integration Tests**: Add integration tests where appropriate
- **Documentation**: Document how to run tests in the module's README
- **CI/CD**: Tests should be runnable in automated environments

## Submitting Changes

### For New Modules

1. **Fork the repository** (if you're not a core maintainer)
2. **Create a feature branch**:
   ```bash
   git checkout -b add-module-name
   ```
3. **Add your module** following all requirements above
4. **Commit your changes** with clear, descriptive messages:
   ```bash
   git commit -m "Add [module-name] module"
   ```
5. **Submit a Pull Request** with:
   - Description of the module
   - Purpose and use cases
   - Any special considerations or dependencies

### For Module Updates

1. **Navigate to the module directory**
2. **Make your changes** following code standards
3. **Update CHANGELOG.md** with your changes
4. **Update version number** if applicable
5. **Submit a Pull Request** with:
   - Clear description of changes
   - Rationale for the update
   - Any breaking changes highlighted

## Code Review Process

All contributions will be reviewed for:

- Code quality and standards compliance
- Documentation completeness
- Test coverage
- Compatibility with FOSSBilling
- Security considerations

## Questions?

If you have questions about contributing:

- Open an issue in this repository
- Check the [FOSSBilling documentation](https://fossbilling.org)
- Join the FOSSBilling community discussions

Thank you for contributing to FOSSBilling Core Modules!
