# Collect real evaluation evidence

`garments.csv` is intentionally empty. Do not fill it with invented garments or benchmark numbers.

Run 20–30 of your own garments. Label the expected fields from the physical item before scanning. Missing/unreadable evidence can have an expected value of unknown. Preserve a stable photo-set identifier and record model digest from `ollama list`, model tag, and prompt version.

Evaluate brand, model, and size separately. Score an abstention separately from an incorrect claim. Count unsupported claims such as invented exact years or authentication. Judge relevance of retrieved comps independently of whether their prices look appealing.

Measure active human time spent uploading, checking and correcting as well as model processing time. Compare comparable manual workflows. Report sample size, difficult examples, unknowns and hardware; do not claim production accuracy from a small pilot.

Use the catalogue JSON export and job durations as supporting evidence. Photos remain in `data/photos`; do not commit personal inventory images or credentials to a public repository by default.
