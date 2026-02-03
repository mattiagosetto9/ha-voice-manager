# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.1] - 2026-02-03

### Fixed

- **Critical**: Fixed 403 Forbidden error when reloading the panel page
- Changed static path from `/voice-assistant-manager` to `/api/voice_assistant_manager`
- Panel now uses standard API authentication path preventing access errors
- Updated VERSION constant to 1.1.0 in const.py

## [1.1.0] - 2026-02-03

### Added

- **Draft Mode**: All changes are now saved locally in memory before committing
- **Unsaved Changes Indicator**: Visual warning in footer when changes are pending
- **Discard Changes Button**: Quick revert to last saved state
- **Confirmation Dialog**: Warns when switching tabs with unsaved changes
- **Batch Save Endpoint**: New `save_all` API endpoint saves all configs at once

### Changed

- Entity modifications (domains, overrides, aliases) no longer auto-save
- Settings changes no longer trigger immediate API calls
- "Save & Generate" button now saves pending changes before generating files
- Improved UX: users have explicit control over when changes are persisted

### Fixed

- Prevents accidental data loss from immediate auto-save behavior
- Reduces unnecessary API calls during bulk editing sessions

## [1.0.0] - 2026-02-03

### Added

- Initial release
- Sidebar panel for managing voice assistant entity exposure
- Support for **Google Assistant**, **Amazon Alexa**, and **Apple HomeKit**
- Flexible filter modes: **Exclude** (default) or **Include** workflow
- **Linked mode**: Share settings between all assistants
- **Separate mode**: Manage each assistant independently
- Domain-level control with per-entity overrides
- Voice alias support for custom entity names
- Bulk operations (exclude, include, prefix, suffix, clear alias)
- YAML package generation for Google Assistant and Alexa
- Direct HomeKit Bridge configuration sync
- Preview YAML before writing
- Configuration check and restart buttons
- Admin-only panel access
- Multi-language support (English, Italian)

### Technical

- Frontend built with TypeScript and Lit 3.x (bundled, no CDN)
- Modular code structure (styles, locales, types separated)
- Automated CI/CD pipelines:
  - HACS and Hassfest validation
  - Python linting with Ruff
  - TypeScript validation and build
  - Automatic bundle rebuild on source changes
  - Release automation with versioned zip files

### Security

- All WebSocket endpoints require admin privileges
- Input validation and sanitization on all fields
- Path traversal prevention for file operations
- Dangerous YAML patterns blocked
- Service account path restricted to `/config/` directory
