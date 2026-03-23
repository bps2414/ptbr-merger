# Product Guidelines

## 1. Design & UX Principles
- **Silent Operation:** As a middleware tool, it should operate invisibly in the background without requiring user intervention after initial setup.
- **Fail-Safe & Non-Destructive:** Always prioritize data safety. Default to safe operations and provide dry-run capabilities to prevent accidental deletion of user media.
- **Clear Logging:** Provide comprehensive, structured logs detailing the extraction, mixing, and cleanup phases so administrators can easily troubleshoot issues.

## 2. Technical Guidelines
- **Minimal Dependencies:** Rely on native wrappers around system tools (like FFmpeg) and standard libraries whenever possible to ensure a lightweight footprint.
- **Idempotency:** Re-running the tool on the same file should safely handle existing tracks or gracefully skip without corrupting the media.
- **Configuration over Hardcoding:** Expose all tunable parameters (thresholds, API keys, paths) via a central configuration file (`config.yml`).

## 3. Communication Style
- **Administrative Tone:** Error messages and notifications should be concise, technical, and actionable.
- **Clear Status Updates:** If webhook notifications are enabled, provide a clear summary of what was mixed and any warnings encountered.