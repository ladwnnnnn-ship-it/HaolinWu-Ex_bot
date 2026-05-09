# demosense raw source

This directory keeps the full QQ export used by `exes/demosense`.

Files:

- `demosense_2110124650_all_transcript.txt`: readable full transcript.
- `demosense_2110124650_all_raw.json.part001` to `.part004`: split raw JSON export.
- `manifest.json`: sizes and SHA-256 checksums.

Reassemble the raw JSON:

```bash
python tools/reassemble_chunks.py data/demosense/manifest.json --output data/demosense/demosense_2110124650_all_raw.json
```

Expected raw SHA-256:

```text
d1502a09a284b0edc845bfe1e244ab92e84977104fef27a5d2740ae77b81f213
```

Generation rule: when rebuilding the persona, use these files as the source of truth and do not add unsupported memory, dates, scenes, or relationship details.
