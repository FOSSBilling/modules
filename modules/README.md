# Modules Directory

This directory contains all FOSSBilling core modules. Each module is maintained independently in its own subdirectory.

## Current Modules

Modules will be added here progressively as they are transferred from the main FOSSBilling repository or developed specifically for this monorepo.

*No modules have been added yet. This is the initial setup.*

## Adding a Module

When adding a module to this directory:

1. Create a new directory with a descriptive, lowercase, hyphenated name
2. Ensure the module follows the structure outlined in [CONTRIBUTING.md](../CONTRIBUTING.md)
3. Include all required files (README.md, LICENSE, CHANGELOG.md)
4. Update the main README.md to list the new module

## Module Guidelines

Each module should:

- Be completely self-contained
- Have clear documentation
- Include tests where applicable
- Follow FOSSBilling coding standards
- Use semantic versioning

For detailed guidelines, see [CONTRIBUTING.md](../CONTRIBUTING.md).

## Module Template

For a quick start, refer to the module structure requirements in CONTRIBUTING.md:

```
module-name/
├── README.md           # Module documentation
├── LICENSE            # License information
├── CHANGELOG.md       # Version history
├── composer.json      # Dependencies (PHP)
├── .gitignore         # Module-specific ignores
├── src/               # Source code
├── tests/             # Tests
└── docs/              # Additional documentation
```

## Questions?

For questions about adding or maintaining modules, please:

- Review [CONTRIBUTING.md](../CONTRIBUTING.md)
- Open an issue in this repository
- Refer to the main [FOSSBilling documentation](https://fossbilling.org)
