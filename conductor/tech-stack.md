# Tech Stack

## Language
- **Python 3.11+**: Core programming language.

## Dependencies & Libraries
- **requests**: For making HTTP calls to Radarr and qBittorrent APIs.
- **PyYAML**: For parsing the `config.yml` configuration file.
- **loguru**: For structured, easy-to-read logging.

## External Tools & System Requirements
- **FFmpeg & FFprobe**: Required natively on the host system to extract and multiplex audio tracks efficiently without additional Python wrappers.

## Integration Targets
- **Radarr (V3/V4)**: The primary trigger and media manager.
- **qBittorrent (API v2)**: Used to download the source media containing the Portuguese audio track.