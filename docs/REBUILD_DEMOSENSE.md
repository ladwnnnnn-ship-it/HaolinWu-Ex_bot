# Rebuild demosense from source

Use this when you want to regenerate `exes/demosense` strictly from the full QQ export.

1. Reassemble the raw JSON if needed:

```bash
python tools/reassemble_chunks.py data/demosense/manifest.json --output data/demosense/demosense_2110124650_all_raw.json
```

2. Treat `data/demosense/demosense_2110124650_all_transcript.txt` and the reassembled raw JSON as the only source of truth.

3. Follow the project templates:

- `prompts/memory_analyzer.md`
- `prompts/persona_analyzer.md`
- `prompts/memory_builder.md`
- `prompts/persona_builder.md`

4. Do not add unsupported assumptions:

- no invented relationship milestones
- no invented private scenes
- no invented motives
- no personality traits without repeated evidence

5. If a detail is unclear, mark it as unknown instead of filling it in.
