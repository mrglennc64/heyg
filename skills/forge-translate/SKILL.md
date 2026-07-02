---
name: forge-translate
description: Localize an avatar video into another language on a self-hosted AvatarForge stack — same face, same cloned voice, re-dubbed and re-lip-synced. Use when the user wants to translate, dub, or localize an existing avatar video.
---

# forge-translate — one twin, many languages

Re-renders an existing scene graph in a new language. The cloned voice
carries over (XTTS v2 is multilingual from one reference), and lip-sync is
regenerated per language (MuseTalk consumes audio features, not text).

Supported languages (XTTS v2): en, es, fr, de, it, pt, pl, tr, ru, nl, cs,
ar, zh, ja, hu, ko, hi.

## Workflow

1. **Translate the script text first.** The `input_text` in each scene must
   already be in the target language — translate it yourself (you are a
   language model) and write a copy of the scene graph, e.g. `video.es.json`.
   Keep sentence count and approximate length similar to the original so
   scene pacing survives.

2. **Re-dub:**

```bash
forge video translate --file ./video.es.json --language es --keep-text \
  --test -o ./preview_es.mp4
```

`--keep-text` asserts the text is already translated. The command stamps
`voice.language` on every scene and re-renders end-to-end.

3. **Verify, then final render** without `--test`.

## Translation quality rules

- Localize idioms, don't transliterate them.
- Numbers, dates, units: convert to target-locale conventions.
- Keep proper nouns and product names in the original.
- Long German/Finnish compounds can outrun a scene — if the translated text
  is >25% longer than the source, tighten it or bump `voice.speed` to 1.05.
- Re-time overlay `start_sec`/`end_sec` if the dubbed scene runs longer.
