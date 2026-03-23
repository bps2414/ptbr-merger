# Initial Concept
PTBRMerger is a middleware tool designed to intercept 4K video imports in Radarr. It automatically searches for and downloads 1080p dual-audio sources via qBittorrent, extracts the Portuguese audio track using FFmpeg, and merges it into the 4K release, creating a clean, synchronized file for media centers.

## Target Audience
Home media enthusiasts and homelab administrators who use Radarr to manage their 4K movie collections but require high-quality dubbed Portuguese audio tracks without manual intervention.

## Core Features
- **Radarr Integration:** Acts as a custom script triggered on Radarr import events.
- **Automated Searching:** Interfaces with Radarr to trigger searches for 1080p dual-audio releases using a specific profile and tag.
- **Download Management:** Monitors qBittorrent for the completion of the 1080p source file.
- **Audio Extraction & Smart Merging:** Uses FFmpeg to extract Portuguese audio and merge it into the 4K file. It optimizes playback for Smart TVs by stripping irrelevant language streams (keeping only Portuguese, English, and Japanese/Original) and enforcing perfect stream interleaving.
- **Dry-Run Mode:** Supports a safe simulation mode for testing infrastructure without modifying files or deleting torrents.
- **Notifications:** Optional Discord webhook integration to alert users upon successful processing.

## Use Cases
- A user downloads a pristine 4K video release (which only contains English audio).
- PTBRMerger intercepts the Radarr completion event.
- It finds a 1080p WEB-DL with a Brazilian Portuguese track.
- It mixes the PT-BR track into the 4K file seamlessly, deleting the 1080p source afterwards.