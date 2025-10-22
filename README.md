# FOSSBilling Core Modules

This repository serves as a monorepo for FOSSBilling's core modules. Each module is maintained independently in its own directory, allowing for focused development and discussion while keeping related components together.

## Repository Structure

```
core-modules/
├── modules/              # Individual module directories
│   ├── module-name-1/   # Each module in its own folder
│   ├── module-name-2/
│   └── ...
├── CONTRIBUTING.md      # Guidelines for contributing
└── README.md           # This file
```

## Purpose

This repository is designed to:

- Serve as a central location for core FOSSBilling modules
- Enable independent development of each module
- Facilitate discussion and collaboration on core functionality
- Maintain clear separation between different modules
- Allow modules to be transferred and updated one by one

## Module Structure

Each module within the `modules/` directory should:

- Be completely self-contained in its own folder
- Include its own README.md with documentation
- Have its own versioning and changelog
- Contain all necessary files (source code, tests, configuration)
- Follow FOSSBilling coding standards and conventions

## Getting Started

### For Contributors

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines on:

- Adding a new module
- Updating existing modules
- Code standards and requirements
- Testing and validation procedures

### For Users

Individual modules can be used by:

1. Navigating to the specific module directory
2. Following the module's own README for installation and usage
3. Checking the module's documentation for configuration options

## Modules

Modules will be added to this repository progressively. Each module will be transferred and updated individually to ensure quality and consistency.

Current modules:
- *(Modules will be listed here as they are added)*

## License

Each module may have its own license. Please refer to the individual module directories for specific licensing information.

## Support

For issues or questions:
- Open an issue in this repository for general monorepo questions
- Check individual module directories for module-specific issues
- Visit [FOSSBilling's main repository](https://github.com/FOSSBilling/FOSSBilling) for general FOSSBilling support